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
        self._threshold = threshold
        self._checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else Path("checkpoints/latest")
        self._inductive_lock = threading.Lock()  # FIX 3: serialize inductive encodes

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
        if (self._checkpoint_dir / "calibration.json").exists():
            self._calibrator.load(self._checkpoint_dir)

        logger.info(
            "InferenceEngine ready: %d CVs, %d jobs, %d skill-pairs, reranker=%s",
            len(cvs), len(jobs), len(self._skill_similarity),
            "trained" if self._reranker.is_trained else "fallback",
        )

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_path: Path | str,
        normalizer: SkillNormalizer,
        embedding_provider: EmbeddingProvider,
        **kwargs,
    ) -> InferenceEngine:
        """Load model from checkpoint and build engine."""
        model, data, cvs, jobs, meta = load_checkpoint(checkpoint_path)
        return cls(
            model=model,
            data=data,
            cvs=cvs,
            jobs=jobs,
            normalizer=normalizer,
            embedding_provider=embedding_provider,
            checkpoint_dir=Path(checkpoint_path),  # FIX 1: pass actual path
            **kwargs,
        )

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

    def match_cv(self, cv: CVData, top_k: int = 10, retrieve_n: int = 50) -> list[JobMatchResult]:
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
            rerank_probs = self._reranker.score_batch(
                [cv] * len(cand_indices),
                self._jobs,
                list(range(len(cand_indices))),
                cand_indices,
                gnn_scores=gnn_scores_for_candidates,
            )
            # Sort by reranker score; keep reranker_score map for match_level
            reranker_score_map = {idx: float(s) for idx, s in zip(cand_indices, rerank_probs)}
            reranked = sorted(
                zip(cand_indices, rerank_probs),
                key=lambda x: -x[1],
            )
            # Preserve reranker order — do NOT re-sort by stage1 score
            scored = [(idx, stage1_score_map[idx]) for idx, _ in reranked]
        else:
            reranker_score_map = {}
            scored = candidates

        # --- Build results (reranker order preserved, no secondary sort) ---
        results: list[JobMatchResult] = []
        for job_idx, raw_score in scored[:top_k]:
            job = self._jobs[job_idx]
            job_skills = set(job.skills)
            title = job.text.split(".")[0] if job.text else ""

            display_score = float(raw_score)
            calibrated = self._calibrator.transform_single(display_score)
            eligible = calibrated >= 0.5 if self._calibrator.is_fitted else display_score >= self._threshold

            # match_level from ordinal reranker score (thresholds from eval: class2≈0.33, class1≈0.25, class0≈0.18)
            rs = reranker_score_map.get(job_idx, -1.0)
            if rs >= 0.30:
                match_level = "strong"
            elif rs >= 0.22:
                match_level = "good"
            elif rs >= 0:
                match_level = "weak"
            else:
                match_level = ""

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
                )
            )

        return results

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
    ) -> dict[str, float]:
        """Train the Stage 2 reranker on labeled pairs."""
        metrics = self._reranker.train(
            self._cvs, self._jobs, cv_indices, job_indices, labels,
            gnn_scores=gnn_scores, stage1_scores=stage1_scores,
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

        base_score = (
            self._alpha * gnn_score
            + self._beta * skill_score
            + self._gamma * seniority_score
        )

        cv_role = infer_role(cv.skills, cv.text)
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

            cv_emb = self._embed.encode([cv.text])  # (1, 384)
            cv_extra = np.array([[cv.experience_years / 20.0, float(cv.education) / 4.0]], dtype=np.float32)
            new_cv_feat = torch.from_numpy(np.concatenate([cv_emb, cv_extra], axis=1))

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

        base_score = (
            self._alpha * gnn_score
            + self._beta * skill_score
            + self._gamma * seniority_score
        )

        cv_role = infer_role(cv.skills, cv.text)
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
