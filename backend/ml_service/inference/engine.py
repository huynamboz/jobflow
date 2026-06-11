"""Two-stage inference engine for CV-Job matching.

Stage 1 (Retrieve): Fast scoring via text similarity → top N candidates
Stage 2 (Rerank):   XGBoost on rich feature vectors → final top K

If reranker is not trained, falls back to hybrid scoring (v3).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch_geometric.data import HeteroData

from ml_service.baselines.skill_overlap import SkillOverlapScorer
from ml_service.data.skill_extractor import SkillExtractor
from ml_service.data.skill_graph import build_skill_cooccurrence
from ml_service.data.skill_normalization import SkillNormalizer
from ml_service.embedding.base import EmbeddingProvider
from ml_service.graph.schema import CVData, JobData, SeniorityLevel
from ml_service.inference.checkpoint import load_checkpoint
from ml_service.inference.role_classifier import infer_role, role_match_penalty
from ml_service.models.gnn import HeteroGraphSAGE, prepare_data_for_gnn
from ml_service.reranker.calibration import PlattCalibrator
from ml_service.reranker.features import FeatureExtractor
from ml_service.reranker.ranker import Reranker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MatchResult:
    """Single CV match result (JD → CVs)."""

    cv_id: int
    score: float
    eligible: bool
    matched_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
    seniority_match: bool


@dataclass(frozen=True)
class JobMatchResult:
    """Single Job match result (CV → Jobs)."""

    job_id: int
    score: float
    eligible: bool
    matched_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
    seniority_match: bool
    title: str = ""
    company: str = ""
    match_level: str = ""  # "strong" | "good" | "weak"
    dim_scores: dict = None  # skill_fit/experience_fit/seniority_fit/domain_fit → numeric fit [0,1]

    def __post_init__(self):
        # dataclass frozen=True — default mutable arg workaround
        object.__setattr__(self, "dim_scores", self.dim_scores if self.dim_scores is not None else {})


@dataclass(frozen=True)
class RebuildReport:
    """Outcome of rebuilding the job pool from a fresh job set."""

    num_jobs: int
    skill_skipped_edges: int
    encode_seconds: float


class InferenceEngine:
    """Precompute CV embeddings once, score new JDs against all CVs.

    Usage:
        engine = InferenceEngine.from_checkpoint("checkpoints/latest", normalizer, provider)
        results = engine.match("Senior Python developer with Django and AWS experience", top_k=10)
    """

    def __init__(
        self,
        model: HeteroGraphSAGE,
        data: HeteroData,
        cvs: list[CVData],
        jobs: list[JobData],
        normalizer: SkillNormalizer,
        embedding_provider: EmbeddingProvider,
        *,
        checkpoint_dir: Path | str | None = None,  # FIX 1: replaces hardcoded path
        alpha: float = 0.55,
        beta: float = 0.30,
        gamma: float = 0.15,
        delta: float = 0.0,  # feature 020: domain (role-match) weight
        threshold: float = 0.65,
    ) -> None:
        self._model = model
        self._data = data
        self._cvs = cvs
        self._jobs = jobs
        self._normalizer = normalizer
        self._embed = embedding_provider
        self._extractor = SkillExtractor(normalizer)
        self._skill_scorer = SkillOverlapScorer()
        self._alpha = alpha
        self._beta = beta
        self._gamma = gamma
        self._delta = delta
        self._threshold = threshold
        self._checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else Path("checkpoints/latest")
        self._inductive_lock = threading.Lock()  # FIX 3: serialize inductive encodes
        # Feature 018: live job-pool snapshot (set by from_checkpoint / reload).
        self._job_pool_dir: Path | None = None
        self._job_pool_snapshot_mtime: float = 0.0

        # Precompute GNN embeddings (cv + job nodes in graph)
        self._cv_embeddings, self._job_embeddings, self._z_dict = self._precompute_embeddings()

        # FIX 2: Precompute job text embeddings once at startup
        logger.info("Precomputing text embeddings for %d jobs...", len(jobs))
        self._job_text_vecs: np.ndarray = embedding_provider.encode([j.text for j in jobs])

        # Build skill similarity lookup from co-occurrence graph
        self._skill_similarity = self._build_skill_similarity(cvs, jobs)

        # Feature extractor + reranker (Stage 2)
        self._feature_extractor = FeatureExtractor(
            embedding_provider=embedding_provider,
            skill_similarity=self._skill_similarity,
            skill_categories={s: int(c) for s, c in normalizer.skill_catalog.items()},
        )
        self._reranker = Reranker(self._feature_extractor)

        # Score calibration (Platt scaling)
        self._calibrator = PlattCalibrator()

        # FIX 1: Load reranker + calibration from correct checkpoint dir
        if (self._checkpoint_dir / "reranker.pt").exists():
            self._reranker.load(self._checkpoint_dir)
            self._warn_if_reranker_weights_stale()  # 023/3.6 (A14 guard)
        if (self._checkpoint_dir / "calibration.json").exists():
            self._calibrator.load(self._checkpoint_dir)

        # 024: boot-time self-check — the per-request CV encoder has a broad
        # fallback to text-cosine (line ~977) that is correct for a single
        # malformed CV but would SILENTLY mask a systematic train/serve skew
        # (e.g. the 386↔397 dim bug that passed 4 eval suites unnoticed). Probe
        # the inductive path once at startup so any systematic break fails LOUD
        # here instead of degrading every request in production.
        self._selftest_inductive_cv_encoder()

        logger.info(
            "InferenceEngine ready: %d CVs, %d jobs, %d skill-pairs, reranker=%s",
            len(cvs), len(jobs), len(self._skill_similarity),
            "trained" if self._reranker.is_trained else "fallback",
        )

    def _selftest_inductive_cv_encoder(self) -> None:
        """Fail loudly at boot if the serving CV encoder can't reproduce the
        trained embedding (systematic skew). A genuine per-CV transient still
        falls back per-request; this only catches the systematic case."""
        from ml_service.graph.schema import CVData, SeniorityLevel, EducationLevel

        if self._job_embeddings is None:  # no GNN to skew against
            return
        probe = CVData(
            cv_id=-(10**9), seniority=SeniorityLevel(2), experience_years=3.0,
            education=EducationLevel(2), skills=tuple(sorted(self._normalizer.skill_catalog)[:3]),
            skill_proficiencies=(3, 3, 3), text="self-test backend developer python",
        )
        emb = self._inductive_gnn_encode_cv(probe)
        if emb is None:
            raise RuntimeError(
                "Inductive CV encoder fell back at startup — serving CV node "
                "features are out of sync with the checkpoint (train/serve skew). "
                "Every uploaded CV would silently lose the GNN signal. Fix the "
                "CV feature layout in _inductive_gnn_encode_cv before serving."
            )

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_path: Path | str,
        normalizer: SkillNormalizer,
        embedding_provider: EmbeddingProvider,
        **kwargs,
    ) -> InferenceEngine:
        """Load model from checkpoint and build engine.

        Feature 018: if a live job-pool snapshot exists under
        ``job_pool_dir`` (default ``checkpoints/job_pool``) AND was built against
        this model, it OVERRIDES the frozen checkpoint job pool so the engine
        ranks against the live catalog. Absent/incompatible → frozen pool."""
        job_pool_dir = kwargs.pop("job_pool_dir", None)
        model, data, cvs, jobs, meta = load_checkpoint(checkpoint_path)

        # Feature 019: tuned hybrid weights live in metadata.json (single source of
        # truth). Load them here; fall back to the documented defaults if absent.
        hw = meta.get("hybrid_weights") if isinstance(meta, dict) else None
        if hw:
            kwargs.setdefault("alpha", float(hw.get("alpha", 0.55)))
            kwargs.setdefault("beta", float(hw.get("beta", 0.30)))
            kwargs.setdefault("gamma", float(hw.get("gamma", 0.15)))
            kwargs.setdefault("delta", float(hw.get("delta", 0.0)))  # feature 020
            logger.info("Hybrid weights from metadata: a=%.2f b=%.2f g=%.2f d=%.2f",
                        kwargs["alpha"], kwargs["beta"], kwargs["gamma"], kwargs["delta"])
        else:
            logger.warning("No hybrid_weights in metadata — using defaults 0.55/0.30/0.15.")

        engine = cls(
            model=model,
            data=data,
            cvs=cvs,
            jobs=jobs,
            normalizer=normalizer,
            embedding_provider=embedding_provider,
            checkpoint_dir=Path(checkpoint_path),  # FIX 1: pass actual path
            **kwargs,
        )

        from ml_service.inference import job_pool_snapshot

        snap_dir = Path(job_pool_dir) if job_pool_dir else job_pool_snapshot.DEFAULT_DIR
        engine._job_pool_dir = snap_dir
        loaded = job_pool_snapshot.load(snap_dir, engine.model_signature)
        if loaded is not None:
            engine.set_job_pool(*loaded)
            engine._job_pool_snapshot_mtime = job_pool_snapshot.mtime(snap_dir)
            logger.info("Loaded live job pool from snapshot: %d jobs", engine.num_jobs)
        return engine

    def maybe_reload_job_pool(self) -> bool:
        """Hot-reload the job pool if the on-disk snapshot is newer than the one
        currently loaded. Cheap (an mtime stat) when nothing changed. Returns True
        if a reload happened. Enables realtime catalog updates on the live server
        without a restart."""
        if not self._job_pool_dir:
            return False
        from ml_service.inference import job_pool_snapshot

        m = job_pool_snapshot.mtime(self._job_pool_dir)
        if m <= self._job_pool_snapshot_mtime:
            return False
        loaded = job_pool_snapshot.load(self._job_pool_dir, self.model_signature)
        if loaded is None:
            return False
        self.set_job_pool(*loaded)
        self._job_pool_snapshot_mtime = m
        logger.info("Hot-reloaded job pool from snapshot: %d jobs", self.num_jobs)
        return True

    def labeled_pair_components(self) -> list[tuple[int, int, int, float, float, float]]:
        """For offline hybrid-weight tuning (feature 019): extract labeled pairs
        from the graph's match/no_match edges and return, per pair, the THREE
        components the hybrid score blends (feature 020 adds domain + roles):
            (cv_idx, job_idx, label, gnn, skill, seniority, domain, cv_role, job_role)
        where gnn = sigmoid(model.decode), skill = semantic overlap, seniority =
        max(0, 1-|Δsen|·0.4). Load the engine WITHOUT a live job-pool snapshot
        (job_pool_dir=<absent>) so self._jobs == the checkpoint training jobs the
        labels refer to."""
        pairs: list[tuple[int, int, int]] = []
        for et, label in ((("cv", "match", "job"), 1), (("cv", "no_match", "job"), 0)):
            if et not in self._data.edge_types:
                continue
            ei = self._data[et].edge_index
            for k in range(ei.shape[1]):
                pairs.append((int(ei[0, k]), int(ei[1, k]), label))
        if not pairs:
            return []

        cv_idx_t = torch.tensor([p[0] for p in pairs], dtype=torch.long)
        job_idx_t = torch.tensor([p[1] for p in pairs], dtype=torch.long)
        self._model.eval()
        with torch.no_grad():
            logits = self._model.decode(self._z_dict, cv_idx_t, job_idx_t)
            gnn_scores = torch.sigmoid(logits).reshape(-1).tolist()

        out: list[tuple] = []
        for (ci, ji, lab), g in zip(pairs, gnn_scores):
            cv = self._cvs[ci]
            job = self._jobs[ji]
            skill = float(self._semantic_skill_overlap(cv, job))
            sen = max(0.0, 1.0 - abs(int(cv.seniority) - int(job.seniority)) * 0.4)
            # feature 020: domain component + roles for the role-aware metric
            cv_role = infer_role(cv.skills, cv.text)
            domain = self._role_domain_fit(cv_role, job)
            out.append((ci, ji, lab, float(g), skill, sen, domain, cv_role, job.role_category or ""))
        return out

    # 023/3.5: mirror of the labeling rubric's related-domain table — related
    # fields are a partial match (rubric: domain=1 → can still be overall≥1).
    _RELATED_DOMAINS = {
        ("fullstack", "backend"), ("backend", "fullstack"),
        ("fullstack", "frontend"), ("frontend", "fullstack"),
        ("data_ml", "data_eng"), ("data_eng", "data_ml"),
        ("mobile", "frontend"), ("frontend", "mobile"),
    }

    @staticmethod
    def _reranker_weights_in_sync(serving: dict | None, trained_with: dict | None,
                                  tol: float = 1e-6) -> bool:
        """023/3.6 (A14): the reranker's stage1_score feature was computed with
        the weights active at TRAIN time — serving with different weights feeds
        it a distribution it never learned. None trained_with (old checkpoints)
        → unknown, treated as out-of-sync (warn)."""
        if not trained_with or not serving:
            return False
        keys = ("alpha", "beta", "gamma", "delta")
        return all(abs(float(serving.get(k, 0)) - float(trained_with.get(k, 0))) <= tol
                   for k in keys)

    def _warn_if_reranker_weights_stale(self) -> None:
        import json as _json
        meta_p = self._checkpoint_dir / "metadata.json"
        rmeta_p = self._checkpoint_dir / "reranker_meta.json"
        if not (meta_p.exists() and rmeta_p.exists()):
            return
        try:
            serving = _json.loads(meta_p.read_text()).get("hybrid_weights")
            trained_with = _json.loads(rmeta_p.read_text()).get("trained_with_weights")
        except Exception:  # noqa: BLE001
            return
        if not self._reranker_weights_in_sync(serving, trained_with):
            logger.warning(
                "RERANKER WEIGHT SKEW (A14): reranker was trained with hybrid "
                "weights %s but serving uses %s — its stage1_score feature is "
                "off-distribution. Retrain the reranker after tuning weights "
                "(train_reranker.py, ~5 min on the GPU server).",
                trained_with, serving,
            )

    @staticmethod
    def _role_domain_fit(cv_role: str, job: JobData) -> float:
        """Domain (role) fit: 1.0 same field · 0.7 related (rubric table) ·
        0.5 job role unknown · 0.0 mismatch. Shared by the δ·domain term, the
        ordering domain gate (fires only at 0.0), and the dim display."""
        if job.role_category:
            if cv_role == job.role_category:
                return 1.0
            if (cv_role, job.role_category) in InferenceEngine._RELATED_DOMAINS:
                return 0.7
            return 0.0
        return 0.5

    @staticmethod
    def _dimension_scores(cv: CVData, job: JobData, matched: set[str]) -> dict[str, float]:
        """Transparent, hand-reproducible per-dimension fit (feature 019), each
        in [0,1]. No learned component — every number is a documented function of
        the match's own data:

        - skill_fit:      importance-weighted matched / total required importance
        - experience_fit: 1 − deficit/job.experience_min (under-qual penalized; ≥0)
        - seniority_fit:  max(0, 1 − |Δseniority|·0.3)
        - domain_fit:     1.0 same role · 0.5 unknown · 0.0 mismatch"""
        job_imp = dict(zip(job.skills, job.skill_importances))
        total_imp = sum(job_imp.values())
        skill_fit = (sum(job_imp.get(s, 0) for s in matched) / total_imp) if total_imp > 0 else 1.0

        if job.experience_min and job.experience_min > 0:
            deficit = max(0.0, float(job.experience_min) - float(cv.experience_years))
            experience_fit = max(0.0, min(1.0, 1.0 - deficit / float(job.experience_min)))
        else:
            experience_fit = 1.0

        seniority_fit = max(0.0, 1.0 - abs(int(cv.seniority) - int(job.seniority)) * 0.3)

        domain_fit = InferenceEngine._role_domain_fit(infer_role(cv.skills, cv.text), job)

        return {
            "skill_fit": round(float(skill_fit), 3),
            "experience_fit": round(float(experience_fit), 3),
            "seniority_fit": round(float(seniority_fit), 3),
            "domain_fit": round(float(domain_fit), 3),
        }

    def match(self, jd_text: str, top_k: int = 10) -> list[MatchResult]:
        """Match a JD text against all CVs. Returns Top K ranked results."""
        from ml_service.crawler.base import RawJob

        raw = RawJob(
            source="query",
            source_url="",
            title="",
            company="",
            location="",
            description=jd_text,
        )
        job_data = self._extractor.extract(raw, job_id=-1)

        if not job_data.skills:
            logger.warning("No skills extracted from JD text")
            return []

        results: list[MatchResult] = []
        for cv in self._cvs:
            score = self._score_pair(cv, job_data)
            cv_skills = set(cv.skills)
            job_skills = set(job_data.skills)
            matched = tuple(sorted(cv_skills & job_skills))
            missing = tuple(sorted(job_skills - cv_skills))
            sen_match = abs(int(cv.seniority) - int(job_data.seniority)) <= 1

            results.append(
                MatchResult(
                    cv_id=cv.cv_id,
                    score=round(score, 4),
                    eligible=score >= self._threshold,
                    matched_skills=matched,
                    missing_skills=missing,
                    seniority_match=sen_match,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def match_job_data(self, job: JobData, top_k: int = 10) -> list[MatchResult]:
        """Match a pre-parsed JobData against all CVs."""
        results: list[MatchResult] = []
        for cv in self._cvs:
            score = self._score_pair(cv, job)
            cv_skills = set(cv.skills)
            job_skills = set(job.skills)

            results.append(
                MatchResult(
                    cv_id=cv.cv_id,
                    score=round(score, 4),
                    eligible=score >= self._threshold,
                    matched_skills=tuple(sorted(cv_skills & job_skills)),
                    missing_skills=tuple(sorted(job_skills - cv_skills)),
                    seniority_match=abs(int(cv.seniority) - int(job.seniority)) <= 1,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def match_cv(self, cv: CVData, top_k: int = 10, retrieve_n: int = 200) -> list[JobMatchResult]:
        """Two-stage matching: CV against all Jobs.

        Stage 1 (Retrieve): Fast hybrid scoring → top N candidates
        Stage 2 (Rerank):   XGBoost on feature vectors → final top K
        If reranker not trained, Stage 1 scores are final.
        """
        cv_skills = set(cv.skills)

        # FIX 2: Encode CV text once for the entire request
        cv_text_vec: np.ndarray = self._embed.encode([cv.text])[0]

        # FIX 2+3: Get GNN embedding once (thread-safe, no per-request self cache)
        cv_gnn_emb: torch.Tensor | None = self._get_cv_gnn_embedding(cv)

        # --- Stage 1: Fast retrieve top N (no re-encoding) ---
        stage1_scores: list[tuple[int, float]] = []
        for i, job in enumerate(self._jobs):
            score = self._score_pair_fast(cv, job, i, cv_text_vec, cv_gnn_emb)
            stage1_scores.append((i, score))

        stage1_scores.sort(key=lambda x: -x[1])
        candidates = stage1_scores[:retrieve_n]

        # --- Stage 2: Rerank determines ORDER, Stage 1 keeps SCORE ---
        if self._reranker.is_trained:
            cand_indices = [idx for idx, _ in candidates]
            stage1_score_map = {idx: s for idx, s in candidates}
            self._feature_extractor.set_stage1_context(
                [(self._jobs[idx].job_id, s) for idx, s in candidates]
            )
            # FIX 2: Reuse precomputed vecs for Stage 2 GNN scores (50 candidates)
            gnn_scores_for_candidates = [
                self._gnn_score_fast(cv, self._jobs[idx], idx, cv_text_vec, cv_gnn_emb)
                for idx in cand_indices
            ]
            rerank_probs, dim_levels_list = self._reranker.score_batch_with_dims(
                [cv] * len(cand_indices),
                self._jobs,
                list(range(len(cand_indices))),
                cand_indices,
                gnn_scores=gnn_scores_for_candidates,
            )
            reranker_score_map = {idx: float(s) for idx, s in zip(cand_indices, rerank_probs)}
            dim_levels_map = {idx: d for idx, d in zip(cand_indices, dim_levels_list)}
            reranked = sorted(
                zip(cand_indices, rerank_probs),
                key=lambda x: -x[1],
            )
            # Preserve reranker order — do NOT re-sort by stage1 score
            scored = [(idx, stage1_score_map[idx]) for idx, _ in reranked]
        else:
            reranker_score_map = {}
            dim_levels_map = {}
            scored = candidates

        # --- Build results: apply all penalties to ALL candidates, then final sort ---
        _EXP_PENALTY_THRESHOLD = 0.80   # cv_exp < 80% of job_exp_min → penalize
        _EXP_PENALTY_FACTOR    = 0.40   # experience mismatch multiplier
        _SEN_PENALTY_FACTOR    = 0.70   # seniority mismatch multiplier

        results: list[JobMatchResult] = []
        rank_scores: list[float] = []  # 021/A3: reranker-driven final order
        _cv_role = infer_role(cv.skills, cv.text)
        _DOMAIN_GATE_FACTOR = 0.40  # mirrors the labeling rule: domain=0 → not a match
        for job_idx, raw_score in scored:   # iterate ALL retrieve_n, sort after
            job = self._jobs[job_idx]
            job_skills = set(job.skills)
            title = job.text.split(".")[0] if job.text else ""

            # 021/A3: collect the gate factors as an explicit penalty product so
            # they demote BOTH the displayed score and the reranker-driven order.
            penalty = 1.0

            # Domain gate (022): the ground truth defines cross-field as not a
            # match (rubric hard rule domain=0 → overall=0). Ordering must honor
            # it — catalog jobs with degenerate skill profiles (e.g. VFX jobs
            # whose niche skills were dropped by the catalog) otherwise look like
            # perfect skill matches to the reranker features. Soft gate, no removal.
            if self._role_domain_fit(_cv_role, job) == 0.0:
                penalty *= _DOMAIN_GATE_FACTOR

            # Experience gate
            _EXP_OVERQUAL_GAP    = 3.0   # cv_exp - job_exp_min > 3yr → overqualified
            _EXP_OVERQUAL_FACTOR = 0.85  # mild overqual penalty
            _exp_weak = False
            if job.experience_min and job.experience_min > 0:
                gap = cv.experience_years - job.experience_min
                if gap < 0:                        # underqualified → heavy penalty
                    penalty *= _EXP_PENALTY_FACTOR
                    _exp_weak = True
                elif gap > _EXP_OVERQUAL_GAP:      # overqualified → mild penalty
                    penalty *= _EXP_OVERQUAL_FACTOR
                    _exp_weak = True

            # Seniority gate: senior/lead roles for junior/mid CVs.
            _sen_weak = False
            sen_gap = int(job.seniority) - int(cv.seniority)
            if sen_gap >= 2 or (sen_gap >= 1 and int(job.seniority) >= 3 and int(cv.seniority) <= 2):
                penalty *= _SEN_PENALTY_FACTOR
                _sen_weak = True

            # Overqualification: CV is 2+ seniority levels above job (e.g. senior → intern).
            _OVERQUAL_PENALTY = 0.75
            overqual_gap = int(cv.seniority) - int(job.seniority)
            if overqual_gap >= 2:
                penalty *= _OVERQUAL_PENALTY
                _sen_weak = True

            display_score = float(raw_score) * penalty
            eligible = display_score >= 0.45  # placeholder; overwritten below

            # match_level from ordinal reranker score (thresholds from eval)
            rs = reranker_score_map.get(job_idx, -1.0)
            if rs >= 0.30:
                match_level = "strong"
            elif rs >= 0.22:
                match_level = "good"
            elif rs >= 0:
                match_level = "weak"
            else:
                match_level = ""

            # Feature 019: transparent, hand-reproducible per-dimension fit
            # (replaces the learned aux heads of unknown label provenance).
            dim_scores = self._dimension_scores(cv, job, cv_skills & job_skills)
            if _exp_weak:  # hard experience gate → cap the fit
                dim_scores["experience_fit"] = min(dim_scores["experience_fit"], 0.15)
            if _sen_weak:  # hard seniority gate → cap the fit
                dim_scores["seniority_fit"] = min(dim_scores["seniority_fit"], 0.15)

            results.append(
                JobMatchResult(
                    job_id=job.job_id,
                    score=round(display_score, 4),
                    eligible=eligible,
                    matched_skills=tuple(sorted(cv_skills & job_skills)),
                    missing_skills=tuple(sorted(job_skills - cv_skills)),
                    seniority_match=abs(int(cv.seniority) - int(job.seniority)) <= 1,
                    title=title,
                    match_level=match_level,
                    dim_scores=dim_scores,
                )
            )
            # 021/A3: final order = stage-2 reranker score × penalty product
            # (falls back to the penalized stage-1 score when the reranker did
            # not score this candidate / is untrained — previous behavior).
            rank_scores.append((rs if rs >= 0 else float(raw_score)) * penalty)

        return self._finalize_results(results, rank_scores, top_k,
                                      remap=bool(reranker_score_map))

    @staticmethod
    def _finalize_results(results: list[JobMatchResult], rank_scores: list[float],
                          top_k: int, *, remap: bool) -> list[JobMatchResult]:
        """021/A3: final order = rank_score (reranker × penalties) desc; displayed
        score remapped to be MONOTONIC with that order (per-request min-max of
        rank scores onto this result set's display range). ``remap=False`` (no
        reranker) keeps the legacy stage-1 display values — order == score there
        by construction."""
        order = sorted(range(len(results)), key=lambda i: rank_scores[i], reverse=True)
        final_idx = order[:top_k]
        final = [results[i] for i in final_idx]
        if final and remap:
            d_vals = [r.score for r in final]
            r_vals = [rank_scores[i] for i in final_idx]
            d_lo, d_hi = min(d_vals), max(d_vals)
            r_lo, r_hi = min(r_vals), max(r_vals)
            span = (r_hi - r_lo) or 1.0
            for r, rv in zip(final, r_vals):
                mapped = d_lo + (rv - r_lo) / span * (d_hi - d_lo)
                object.__setattr__(r, "score", round(mapped, 4))
        if final:
            thr = final[0].score * 0.65
            for r in final:
                object.__setattr__(r, "eligible", r.score >= thr)
        return final

    def match_cv_text(self, cv_text: str, top_k: int = 10) -> list[JobMatchResult]:
        """Match raw CV text against all Jobs."""
        from ml_service.cv_parser import CVParser

        parser = CVParser(self._normalizer)
        cv = parser.parse_text(cv_text, cv_id=-1)

        if not cv.skills:
            logger.warning("No skills extracted from CV text")
            return []

        return self.match_cv(cv, top_k=top_k)

    def calibrate(
        self, scores: list[float], labels: list[int],
    ) -> None:
        """Fit Platt calibration on validation scores + labels."""
        self._calibrator.fit(np.array(scores), np.array(labels))
        if self._calibrator.is_fitted:
            self._calibrator.save(self._checkpoint_dir)  # FIX 1

    def train_reranker(
        self,
        cv_indices: list[int],
        job_indices: list[int],
        labels: list[int],
        *,
        gnn_scores: list[float] | None = None,
        stage1_scores: list[float] | None = None,
        dim_labels: list[dict] | None = None,
        epochs: int = 150,
        aux_weight: float = 0.3,
    ) -> dict[str, float]:
        """Train the Stage 2 reranker on labeled pairs."""
        metrics = self._reranker.train(
            self._cvs, self._jobs, cv_indices, job_indices, labels,
            gnn_scores=gnn_scores, stage1_scores=stage1_scores,
            dim_labels=dim_labels, epochs=epochs, aux_weight=aux_weight,
        )
        if self._reranker.is_trained:
            self._reranker.save(self._checkpoint_dir)
        return metrics

    @property
    def reranker(self) -> Reranker:
        return self._reranker

    @property
    def feature_extractor(self) -> FeatureExtractor:
        return self._feature_extractor

    @property
    def num_cvs(self) -> int:
        return len(self._cvs)

    @property
    def num_jobs(self) -> int:
        return len(self._jobs)

    @property
    def cv_pool(self) -> list[CVData]:
        return list(self._cvs)

    def replace_job_skills(self, new_jobs: list[JobData]) -> None:
        """Replace the job pool with updated JobData (e.g. refreshed DB skills).

        GNN embeddings and text vectors are unchanged — only skill-based scoring
        (semantic overlap, must-have penalty, role classification) is affected.
        The new_jobs list must have the same job_ids in the same order as job_pool.
        """
        if len(new_jobs) != len(self._jobs):
            raise ValueError(
                f"new_jobs length {len(new_jobs)} != current pool {len(self._jobs)}"
            )
        self._jobs = list(new_jobs)

    @property
    def job_pool(self) -> list[JobData]:
        return list(self._jobs)

    @property
    def model_signature(self) -> str:
        """Stable fingerprint of the loaded model (+ CV feature dim). A job-pool
        snapshot built against a different signature must not be trusted, since
        its job embeddings live in a different latent space than the CV embeddings
        this engine computes."""
        import hashlib

        h = hashlib.sha1()
        for k, v in sorted(self._model.state_dict().items()):
            h.update(k.encode())
            h.update(str(tuple(v.shape)).encode())
            flat = v.detach().cpu().reshape(-1)
            if flat.numel():
                step = max(1, flat.numel() // 64)
                h.update(flat[::step].numpy().tobytes())
        h.update(str(int(self._data["cv"].x.shape[1])).encode())
        return h.hexdigest()[:16]

    def set_job_pool(
        self,
        jobs: list[JobData],
        embeddings: torch.Tensor,
        text_vecs: np.ndarray,
    ) -> None:
        """Atomically install a pre-computed job pool (e.g. loaded from a snapshot)
        without re-encoding. Thread-safe vs in-flight match_cv."""
        if not (len(jobs) == embeddings.shape[0] == text_vecs.shape[0]):
            raise ValueError("set_job_pool: length mismatch between jobs/embeddings/text_vecs")
        with self._inductive_lock:
            self._jobs = list(jobs)
            self._job_embeddings = embeddings
            self._job_text_vecs = text_vecs

    def rebuild_job_pool(self, jobs: list[JobData]) -> RebuildReport:
        """Replace the job pool with `jobs`, encoding their GNN embeddings
        inductively in one forward pass onto the frozen CV/skill/seniority graph.
        No retraining; model weights + non-job nodes are untouched.

        Returns a RebuildReport. Raises on an empty set or a dimension mismatch
        (fail loud rather than serve a corrupt pool)."""
        import time

        if not jobs:
            raise ValueError("rebuild_job_pool: empty job list")

        t0 = time.time()
        # Embed job texts ONCE and reuse for both the GNN node features and the
        # Stage-1 text vectors (was embedded twice → ~halves rebuild time).
        text_vecs = self._embed.encode([j.text for j in jobs])
        job_emb, skipped = self._inductive_gnn_encode_jobs(jobs, text_emb=text_vecs)
        if not (job_emb.shape[0] == text_vecs.shape[0] == len(jobs)):
            raise RuntimeError("rebuild_job_pool: post-encode length mismatch")

        self.set_job_pool(jobs, job_emb, text_vecs)
        return RebuildReport(
            num_jobs=len(jobs),
            skill_skipped_edges=int(skipped),
            encode_seconds=round(time.time() - t0, 2),
        )

    def snapshot_job_pool(self, directory: Path | str, *, skill_skipped_edges: int = 0) -> Path:
        """Persist the current job pool to a shareable on-disk snapshot."""
        from ml_service.inference import job_pool_snapshot

        path = job_pool_snapshot.save(
            directory, self._jobs, self._job_embeddings, self._job_text_vecs,
            self.model_signature, skill_skipped_edges=skill_skipped_edges,
        )
        # We just wrote it — adopt it as current so maybe_reload doesn't re-load it.
        self._job_pool_dir = Path(directory)
        self._job_pool_snapshot_mtime = job_pool_snapshot.mtime(directory)
        return path

    def _inductive_gnn_encode_jobs(
        self, jobs: list[JobData], *, text_emb: np.ndarray | None = None,
    ) -> tuple[torch.Tensor, int]:
        """Encode a fresh job set inductively: rebuild the `job` nodes + their
        requires_skill / requires_seniority edges onto a copy of the frozen graph,
        run one model.encode(), return (job_embeddings[N, H], skipped_skill_edges).
        Mirrors `_inductive_gnn_encode_cv` but for the whole job side.

        ``text_emb`` (pre-computed [N, 384]) is reused for the node features."""
        from ml_service.data.skill_graph import build_job_similarity_edges
        from ml_service.graph.builder import build_job_node_features
        from ml_service.training.trainer import _strip_label_edges

        data = _strip_label_edges(self._data)

        skill_names = sorted(self._normalizer.skill_catalog.keys())
        skill_to_idx = {s: i for i, s in enumerate(skill_names)}
        n_jobs = len(jobs)

        # Replace ALL job nodes with the new pool (full rebuild). CV/skill/seniority
        # nodes + their edges stay frozen. We OVERWRITE the three job-touching edge
        # types (never delete — the model's metadata is fixed and expects them);
        # reverse edges are regenerated by prepare_data_for_gnn (ToUndirected).
        data["job"].x = torch.from_numpy(build_job_node_features(jobs, self._embed, text_emb=text_emb))

        def _edge(src: list[int], dst: list[int]) -> torch.Tensor:
            if src:
                return torch.tensor([src, dst], dtype=torch.long)
            return torch.zeros((2, 0), dtype=torch.long)

        # job -> skill (requires_skill), weighted by importance
        rs_src, rs_dst, rs_attr, skipped = [], [], [], 0
        for j_idx, job in enumerate(jobs):
            for skill, imp in zip(job.skills, job.skill_importances):
                si = skill_to_idx.get(skill)
                if si is None:
                    skipped += 1
                    continue
                rs_src.append(j_idx)
                rs_dst.append(si)
                rs_attr.append(float(imp))
        data["job", "requires_skill", "skill"].edge_index = _edge(rs_src, rs_dst)
        data["job", "requires_skill", "skill"].edge_attr = torch.tensor(rs_attr, dtype=torch.float)

        # job -> seniority (requires_seniority)
        data["job", "requires_seniority", "seniority"].edge_index = _edge(
            list(range(n_jobs)), [int(job.seniority) for job in jobs]
        )

        # job -> job (similar_to), rebuilt for the new pool
        jj_index, jj_attr = build_job_similarity_edges(jobs)
        data["job", "similar_to", "job"].edge_index = _edge(jj_index[0], jj_index[1])
        data["job", "similar_to", "job"].edge_attr = torch.tensor(jj_attr, dtype=torch.float)

        data = prepare_data_for_gnn(data)
        self._model.eval()
        with torch.no_grad():
            z_dict = self._model.encode(data)
        return z_dict["job"][:n_jobs].contiguous(), skipped

    # ------------------------------------------------------------------
    # Internal — fast path (match_cv uses these, no re-encoding)
    # ------------------------------------------------------------------

    def _get_cv_gnn_embedding(self, cv: CVData) -> torch.Tensor | None:
        """Get GNN embedding for CV — precomputed if in graph, else inductive.

        FIX 3: Thread-safe via lock. Result is returned to caller (no self cache).
        """
        cv_idx = next((i for i, c in enumerate(self._cvs) if c.cv_id == cv.cv_id), None)
        if cv_idx is not None:
            return self._cv_embeddings[cv_idx]

        with self._inductive_lock:
            return self._inductive_gnn_encode_cv(cv)

    def _score_pair_fast(
        self,
        cv: CVData,
        job: JobData,
        job_idx: int,
        cv_text_vec: np.ndarray,
        cv_gnn_emb: torch.Tensor | None,
    ) -> float:
        """Hybrid score using precomputed CV vectors — no text re-encoding."""
        gnn_score = self._gnn_score_fast(cv, job, job_idx, cv_text_vec, cv_gnn_emb)
        skill_score = self._semantic_skill_overlap(cv, job)
        dist = abs(int(cv.seniority) - int(job.seniority))
        seniority_score = max(0.0, 1.0 - dist * 0.4)

        cv_role = infer_role(cv.skills, cv.text)
        domain_fit = self._role_domain_fit(cv_role, job)  # feature 020: role match vs job.role_category
        base_score = (
            self._alpha * gnn_score
            + self._beta * skill_score
            + self._gamma * seniority_score
            + self._delta * domain_fit
        )

        job_role = infer_role(job.skills, job.text)
        penalty = role_match_penalty(cv_role, job_role)

        score = base_score * penalty
        score = self._apply_must_have_penalty(score, cv, job)
        score = self._apply_edge_case_penalties(score, cv, job)
        return score

    def _gnn_score_fast(
        self,
        cv: CVData,
        job: JobData,
        job_idx: int,
        cv_text_vec: np.ndarray,
        cv_gnn_emb: torch.Tensor | None,
    ) -> float:
        """GNN + text score using precomputed job text embeddings (no embed calls)."""
        # FIX 2: use precomputed job text vector
        job_text_vec = self._job_text_vecs[job_idx]
        text_sim = self._cosine(cv_text_vec, job_text_vec)

        if cv_gnn_emb is None or self._job_embeddings is None:
            return text_sim

        job_emb = self._job_embeddings[job_idx]
        with torch.no_grad():
            gnn_raw = self._model.decoder(cv_gnn_emb.unsqueeze(0), job_emb.unsqueeze(0)).item()
        gnn_norm = 1.0 / (1.0 + np.exp(-gnn_raw))
        return 0.6 * gnn_norm + 0.4 * text_sim

    # ------------------------------------------------------------------
    # Internal — legacy path (match / match_job_data, JD→CVs direction)
    # ------------------------------------------------------------------

    def _precompute_embeddings(self) -> tuple[torch.Tensor, torch.Tensor, dict]:
        """Run GNN encode once on the full graph."""
        self._model.eval()
        from ml_service.training.trainer import _strip_label_edges

        data_clean = _strip_label_edges(self._data)
        data_clean = prepare_data_for_gnn(data_clean)

        with torch.no_grad():
            z_dict = self._model.encode(data_clean)
        return z_dict["cv"], z_dict["job"], z_dict

    def _inductive_gnn_encode_cv(self, cv: CVData) -> torch.Tensor | None:
        """Add new CV as temporary node → GNN encode → return embedding.

        FIX 3: Works on a local copy of the graph — never mutates self._data.
        Call under self._inductive_lock to avoid wasted parallel work.
        """
        from ml_service.training.trainer import _strip_label_edges

        try:
            # Local copy — attribute assignments below don't touch self._data
            data = _strip_label_edges(self._data)

            num_cvs = data["cv"].x.shape[0]
            skill_names = sorted(self._normalizer.skill_catalog.keys())
            skill_to_idx = {s: i for i, s in enumerate(skill_names)}

            # 024 fix: CV node features MUST match the trained layout. GNN v2
            # added role one-hot (11) to CV nodes at train time (builder.py →
            # 397-dim); the serving inductive encoder must mirror it or torch.cat
            # below fails (Expected 397 got 386) and every uploaded CV silently
            # falls back to text similarity — a train/serve skew.
            from ml_service.graph.builder import ROLE_CATEGORIES
            cv_emb = self._embed.encode([cv.text])  # (1, 384)
            cv_extra = np.array([[cv.experience_years / 20.0, float(cv.education) / 4.0]], dtype=np.float32)
            expected_dim = data["cv"].x.shape[1]
            parts = [cv_emb, cv_extra]
            if expected_dim >= 384 + 2 + len(ROLE_CATEGORIES):
                role_onehot = np.zeros((1, len(ROLE_CATEGORIES)), dtype=np.float32)
                cv_role = infer_role(cv.skills, cv.text)
                role_onehot[0, ROLE_CATEGORIES.index(cv_role) if cv_role in ROLE_CATEGORIES else 0] = 1.0
                parts.append(role_onehot)
            new_cv_feat = torch.from_numpy(np.concatenate(parts, axis=1))
            if new_cv_feat.shape[1] != expected_dim:
                raise ValueError(
                    f"CV feature dim {new_cv_feat.shape[1]} != trained {expected_dim} "
                    f"— serving CV encoder out of sync with the checkpoint."
                )

            data["cv"].x = torch.cat([data["cv"].x, new_cv_feat], dim=0)
            new_cv_idx = num_cvs

            new_hs_src, new_hs_dst, new_hs_attr = [], [], []
            for skill in cv.skills:
                if skill in skill_to_idx:
                    new_hs_src.append(new_cv_idx)
                    new_hs_dst.append(skill_to_idx[skill])
                    new_hs_attr.append(3.0)

            if new_hs_src:
                old_ei = data["cv", "has_skill", "skill"].edge_index
                old_attr = data["cv", "has_skill", "skill"].edge_attr
                new_ei = torch.tensor([new_hs_src, new_hs_dst], dtype=torch.long)
                new_attr = torch.tensor(new_hs_attr, dtype=torch.float)
                data["cv", "has_skill", "skill"].edge_index = torch.cat([old_ei, new_ei], dim=1)
                data["cv", "has_skill", "skill"].edge_attr = torch.cat([old_attr, new_attr])

            old_sen_ei = data["cv", "has_seniority", "seniority"].edge_index
            new_sen_ei = torch.tensor([[new_cv_idx], [int(cv.seniority)]], dtype=torch.long)
            data["cv", "has_seniority", "seniority"].edge_index = torch.cat([old_sen_ei, new_sen_ei], dim=1)

            if ("cv", "similar_profile", "cv") in data.edge_types:
                cv_skills = set(cv.skills)
                sim_src, sim_dst, sim_attr = [], [], []
                for i, existing_cv in enumerate(self._cvs):
                    existing_skills = set(existing_cv.skills)
                    union = cv_skills | existing_skills
                    if union:
                        overlap = len(cv_skills & existing_skills) / len(union)
                        if overlap >= 0.3:
                            sim_src.extend([new_cv_idx, i])
                            sim_dst.extend([i, new_cv_idx])
                            sim_attr.extend([overlap, overlap])
                if sim_src:
                    old_sp_ei = data["cv", "similar_profile", "cv"].edge_index
                    old_sp_attr = data["cv", "similar_profile", "cv"].edge_attr
                    new_sp_ei = torch.tensor([sim_src, sim_dst], dtype=torch.long)
                    new_sp_attr = torch.tensor(sim_attr, dtype=torch.float)
                    data["cv", "similar_profile", "cv"].edge_index = torch.cat([old_sp_ei, new_sp_ei], dim=1)
                    data["cv", "similar_profile", "cv"].edge_attr = torch.cat([old_sp_attr, new_sp_attr])

            data = prepare_data_for_gnn(data)
            self._model.eval()
            with torch.no_grad():
                z_dict = self._model.encode(data)

            return z_dict["cv"][new_cv_idx]

        except Exception as e:
            logger.warning("Inductive GNN encode failed: %s, falling back to text similarity", e)
            return None

    def _gnn_score_for_job(self, cv: CVData, job: JobData) -> float:
        """GNN score used by the JD→CVs match() path (legacy, may re-encode text)."""
        job_idx = next(
            (i for i, j in enumerate(self._jobs) if j.job_id == job.job_id),
            None,
        )
        if job_idx is None or self._job_embeddings is None:
            return self._text_similarity(cv, job)

        cv_idx = next(
            (i for i, c in enumerate(self._cvs) if c.cv_id == cv.cv_id),
            None,
        )

        if cv_idx is not None:
            cv_idx_t = torch.tensor([cv_idx], dtype=torch.long)
            job_idx_t = torch.tensor([job_idx], dtype=torch.long)
            with torch.no_grad():
                gnn_raw = self._model.decode(self._z_dict, cv_idx_t, job_idx_t).item()
            gnn_norm = 1.0 / (1.0 + np.exp(-gnn_raw))
            # Use precomputed job text vec to avoid re-encoding job text
            cv_text_vec = self._embed.encode([cv.text])[0]
            job_text_vec = self._job_text_vecs[job_idx]
            text_sim = self._cosine(cv_text_vec, job_text_vec)
            return 0.6 * gnn_norm + 0.4 * text_sim

        # New CV in legacy path: inductive encode without caching on self
        with self._inductive_lock:
            cv_emb = self._inductive_gnn_encode_cv(cv)

        if cv_emb is not None:
            job_emb = self._job_embeddings[job_idx]
            with torch.no_grad():
                gnn_raw = self._model.decoder(cv_emb.unsqueeze(0), job_emb.unsqueeze(0)).item()
            gnn_norm = 1.0 / (1.0 + np.exp(-gnn_raw))
            cv_text_vec = self._embed.encode([cv.text])[0]
            job_text_vec = self._job_text_vecs[job_idx]
            text_sim = self._cosine(cv_text_vec, job_text_vec)
            return 0.6 * gnn_norm + 0.4 * text_sim

        return self._text_similarity(cv, job)

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float((np.dot(a, b) / (na * nb) + 1.0) / 2.0)

    def _score_pair(self, cv: CVData, job: JobData) -> float:
        """Hybrid score — used by legacy JD→CVs match() path."""
        gnn_score = self._gnn_score_for_job(cv, job)
        skill_score = self._semantic_skill_overlap(cv, job)
        dist = abs(int(cv.seniority) - int(job.seniority))
        seniority_score = max(0.0, 1.0 - dist * 0.4)

        cv_role = infer_role(cv.skills, cv.text)
        domain_fit = self._role_domain_fit(cv_role, job)  # feature 020
        base_score = (
            self._alpha * gnn_score
            + self._beta * skill_score
            + self._gamma * seniority_score
            + self._delta * domain_fit
        )

        job_role = infer_role(job.skills, job.text)
        penalty = role_match_penalty(cv_role, job_role)

        score = base_score * penalty
        score = self._apply_must_have_penalty(score, cv, job)
        score = self._apply_edge_case_penalties(score, cv, job)
        return score

    def _semantic_skill_overlap(self, cv: CVData, job: JobData) -> float:
        """Skill overlap with semantic matching via skill graph."""
        if not job.skills:
            return 0.0

        cv_set = set(cv.skills)
        total_weight = 0.0
        matched_weight = 0.0

        for skill, importance in zip(job.skills, job.skill_importances):
            total_weight += importance

            if skill in cv_set:
                matched_weight += importance
            else:
                best_sim = 0.0
                for cv_skill in cv_set:
                    pair = (min(skill, cv_skill), max(skill, cv_skill))
                    sim = self._skill_similarity.get(pair, 0.0)
                    best_sim = max(best_sim, sim)
                if best_sim > 0:
                    matched_weight += importance * best_sim * 0.6

        if total_weight == 0:
            return 0.0
        return min(matched_weight / total_weight, 1.0)

    @staticmethod
    def _apply_must_have_penalty(score: float, cv: CVData, job: JobData) -> float:
        """Penalize score if CV is missing high-importance (required) skills."""
        if not job.skills:
            return score

        cv_set = set(cv.skills)
        missing_required = 0
        for skill, importance in zip(job.skills, job.skill_importances):
            if importance >= 4 and skill not in cv_set:
                missing_required += 1

        if missing_required >= 3:
            score *= 0.6
        elif missing_required == 2:
            score *= 0.75
        elif missing_required == 1:
            score *= 0.9
        return score

    @staticmethod
    def _apply_edge_case_penalties(score: float, cv: CVData, job: JobData) -> float:
        """Apply penalties for generic CV, overqualification, tool-only match, sparse job skills."""
        cv_set = set(cv.skills)
        job_set = set(job.skills)
        intersection = cv_set & job_set

        if len(cv_set) < 4:
            score *= 0.85

        cv_level = int(cv.seniority)
        job_level = int(job.seniority)
        if cv_level >= 3 and job_level <= 1:
            score *= 0.8

        # Sparse job: < 3 skills → skill_overlap is noise, can't trust the signal
        if len(job_set) < 3:
            score *= 0.8

        if intersection:
            _TOOL_SKILLS = {
                "git", "jira", "confluence", "docker", "jenkins",
                "ci_cd", "npm", "vite", "webpack",
            }
            tool_matches = intersection & _TOOL_SKILLS
            core_matches = intersection - _TOOL_SKILLS
            if len(tool_matches) > 0 and len(core_matches) == 0:
                score *= 0.75

        return score

    @staticmethod
    def _build_skill_similarity(
        cvs: list[CVData], jobs: list[JobData],
    ) -> dict[tuple[str, str], float]:
        """Build skill-pair similarity lookup from co-occurrence PMI."""
        cooccurrence = build_skill_cooccurrence(cvs, jobs)
        if not cooccurrence:
            return {}

        max_pmi = max(cooccurrence.values())
        min_pmi = min(cooccurrence.values())
        rng = max_pmi - min_pmi if max_pmi > min_pmi else 1.0

        return {
            pair: (pmi - min_pmi) / rng
            for pair, pmi in cooccurrence.items()
        }

    def _text_similarity(self, cv: CVData, job: JobData) -> float:
        """Cosine similarity between CV and JD text embeddings (re-encodes both)."""
        vecs = self._embed.encode([cv.text, job.text])
        cv_vec, job_vec = vecs[0], vecs[1]
        return self._cosine(cv_vec, job_vec)
