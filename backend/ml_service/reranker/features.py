"""Extract feature vectors for (CV, Job) pairs for reranking.

Each pair produces a feature vector with interpretable components.
Used by Stage 2 reranker (XGBoost) after Stage 1 retrieval.
"""

from __future__ import annotations

import numpy as np

from ml_service.data.skill_normalization import SkillNormalizer
from ml_service.embedding.base import EmbeddingProvider
from ml_service.graph.schema import CVData, JobData
from ml_service.inference.role_classifier import infer_role, role_match_penalty


class FeatureExtractor:
    """Extract feature vector for a (CV, Job) pair."""

    FEATURE_NAMES = [
        "text_similarity",
        "skill_overlap_jaccard",
        "skill_overlap_weighted",
        "semantic_skill_overlap",
        "missing_required_count",
        "missing_required_ratio",
        "matched_skill_count",
        "total_job_skills",
        "seniority_distance",
        "seniority_score",
        "role_penalty",
        "experience_years",
        "cv_skill_count",
        "skill_specificity",
        "tool_ratio",
        # Stage 1 + GNN signals
        "stage1_score",
        "gnn_score",
        "gnn_rank",
        "must_have_cap_triggered",
        "edge_case_penalty_triggered",
        # Experience & role (new)
        "skill_coverage_ratio",
        "experience_gap",
        "role_category_match",
    ]

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        skill_similarity: dict[tuple[str, str], float] | None = None,
        skill_categories: dict[str, int] | None = None,
    ) -> None:
        self._embed = embedding_provider
        self._skill_sim = skill_similarity or {}
        self._skill_cats = skill_categories or {}
        # Injected at inference time by engine
        self._stage1_scores: dict[int, float] = {}  # job_idx → score
        self._stage1_ranks: dict[int, int] = {}  # job_idx → rank

    def set_stage1_context(
        self, scores: list[tuple[int, float]],
    ) -> None:
        """Inject Stage 1 scores/ranks for current query.

        Called by InferenceEngine before extract_batch.
        """
        self._stage1_scores = {idx: s for idx, s in scores}
        sorted_by_score = sorted(scores, key=lambda x: -x[1])
        self._stage1_ranks = {idx: rank for rank, (idx, _) in enumerate(sorted_by_score)}

    def extract(self, cv: CVData, job: JobData, *, gnn_score: float = 0.0) -> np.ndarray:
        """Extract feature vector for a single (CV, Job) pair.

        Args:
            cv, job: CV and Job data
            gnn_score: Actual GNN decode score (0-1). Default 0.0 for backward compat.
        """
        cv_set = set(cv.skills)
        job_set = set(job.skills)
        union = cv_set | job_set
        intersection = cv_set & job_set

        # 1. Text similarity (cosine)
        text_sim = self._text_similarity(cv, job)

        # 2. Jaccard skill overlap (unweighted)
        jaccard = len(intersection) / len(union) if union else 0.0

        # 3. Weighted skill overlap (by importance)
        weighted = self._weighted_overlap(cv_set, job)

        # 4. Semantic skill overlap (with graph relations)
        semantic = self._semantic_overlap(cv_set, job)

        # 5-6. Missing required skills
        missing_req = 0
        total_req = 0
        for skill, imp in zip(job.skills, job.skill_importances):
            if imp >= 4:
                total_req += 1
                if skill not in cv_set:
                    missing_req += 1
        missing_ratio = missing_req / max(total_req, 1)

        # 7-8. Matched / total skill counts
        matched_count = len(intersection)
        total_job_skills = len(job_set)

        # 9-10. Seniority
        sen_dist = abs(int(cv.seniority) - int(job.seniority))
        sen_score = max(0.0, 1.0 - sen_dist * 0.4)

        # 11. Role penalty
        cv_role = infer_role(cv.skills, cv.text)
        job_role = infer_role(job.skills, job.text)
        role_pen = role_match_penalty(cv_role, job_role)

        # 12. Experience years
        exp_years = cv.experience_years

        # 13. CV skill count
        cv_skill_count = len(cv_set)

        # 14. Skill specificity (are CV skills niche or generic?)
        # High specificity = CV has rare skills → better signal
        specificity = self._skill_specificity(cv_set)

        # 15. Tool ratio (what % of CV skills are tools vs technical)
        tool_ratio = self._tool_ratio(cv_set)

        # 16-17. Stage 1 + GNN signals
        stage1_score = self._stage1_scores.get(job.job_id, 0.5)
        gnn_rank = float(self._stage1_ranks.get(job.job_id, 50)) / 50.0  # normalize 0-1

        # 18. Must-have cap triggered (binary)
        must_have_triggered = 1.0 if missing_req >= 2 else (0.5 if missing_req == 1 else 0.0)

        # 19. Edge case penalty triggered (binary)
        edge_penalty = 0.0
        if len(cv_set) < 4:
            edge_penalty = 1.0
        cv_level = int(cv.seniority)
        job_level = int(job.seniority)
        if cv_level >= 3 and job_level <= 1:
            edge_penalty = 1.0
        _TOOL_SKILLS = {"git", "jira", "confluence", "docker", "jenkins", "ci_cd", "npm", "vite", "webpack"}
        if intersection and len(intersection - _TOOL_SKILLS) == 0:
            edge_penalty = 1.0

        # 20. Skill coverage ratio
        skill_coverage = matched_count / max(total_job_skills, 1)

        # 21. Experience gap (positive = over-qualified, negative = under-qualified)
        # Clamp to [-5, +10] then normalize to [-1, 1]
        if job.experience_min > 0:
            raw_gap = cv.experience_years - job.experience_min
            experience_gap = max(-5.0, min(10.0, raw_gap)) / 10.0
        else:
            experience_gap = 0.0  # unknown requirement → neutral

        # 22. Role category match (direct label match, more reliable than infer_role())
        if job.role_category:
            cv_role = infer_role(cv.skills, cv.text)
            role_category_match = 1.0 if cv_role == job.role_category else 0.0
        else:
            role_category_match = 0.5  # unknown → neutral

        return np.array([
            text_sim, jaccard, weighted, semantic,
            missing_req, missing_ratio,
            matched_count, total_job_skills,
            sen_dist, sen_score,
            role_pen, exp_years, cv_skill_count,
            specificity, tool_ratio,
            stage1_score, gnn_score,
            gnn_rank, must_have_triggered, edge_penalty,
            skill_coverage, experience_gap, role_category_match,
        ], dtype=np.float32)

    def extract_batch(
        self, cvs: list[CVData], jobs: list[JobData],
        cv_indices: list[int], job_indices: list[int],
        gnn_scores: list[float] | None = None,
        stage1_scores: list[float] | None = None,
    ) -> np.ndarray:
        """Extract features for multiple pairs with batched text encoding.

        Args:
            cvs, jobs: Lists of CVs and Jobs
            cv_indices, job_indices: Indices of pairs to extract
            gnn_scores: GNN decode scores per pair. Defaults to 0.0 if None.
            stage1_scores: Stage 1 hybrid scores per pair. Overrides context dict if provided.
        """
        if not cv_indices:
            return np.empty((0, len(self.FEATURE_NAMES)))

        if gnn_scores is None:
            gnn_scores = [0.0] * len(cv_indices)
        if stage1_scores is None:
            stage1_scores = [None] * len(cv_indices)

        # Pre-encode all unique texts in one batch (avoid 10K+ individual calls)
        unique_cv_idx = sorted(set(cv_indices))
        unique_job_idx = sorted(set(job_indices))
        all_texts = [cvs[i].text for i in unique_cv_idx] + [jobs[i].text for i in unique_job_idx]

        all_vecs = self._embed.encode(all_texts)
        n_cv = len(unique_cv_idx)

        # Build lookup: index → vector
        cv_vec_map = {idx: all_vecs[i] for i, idx in enumerate(unique_cv_idx)}
        job_vec_map = {idx: all_vecs[n_cv + i] for i, idx in enumerate(unique_job_idx)}

        # Extract features using cached vectors
        features = []
        for ci, ji, gs, s1 in zip(cv_indices, job_indices, gnn_scores, stage1_scores):
            f = self._extract_with_cache(
                cvs[ci], jobs[ji], cv_vec_map[ci], job_vec_map[ji],
                gnn_score=gs, stage1_score_override=s1,
            )
            features.append(f)
        return np.array(features, dtype=np.float32)

    def _extract_with_cache(
        self, cv: CVData, job: JobData,
        cv_vec: np.ndarray, job_vec: np.ndarray,
        *, gnn_score: float = 0.0,
        stage1_score_override: float | None = None,
    ) -> np.ndarray:
        """Extract features using pre-computed text vectors.

        Args:
            gnn_score: Actual GNN decode score (0-1).
            stage1_score_override: If provided, uses this instead of the context dict lookup.
        """
        cv_set = set(cv.skills)
        job_set = set(job.skills)
        union = cv_set | job_set
        intersection = cv_set & job_set

        # 1. Text similarity (from cached vectors)
        norm_cv = np.linalg.norm(cv_vec)
        norm_job = np.linalg.norm(job_vec)
        if norm_cv == 0 or norm_job == 0:
            text_sim = 0.0
        else:
            sim = float(np.dot(cv_vec, job_vec) / (norm_cv * norm_job))
            text_sim = (sim + 1.0) / 2.0

        # 2-4. Skill overlaps
        jaccard = len(intersection) / len(union) if union else 0.0
        weighted = self._weighted_overlap(cv_set, job)
        semantic = self._semantic_overlap(cv_set, job)

        # 5-6. Missing required
        missing_req, total_req = 0, 0
        for skill, imp in zip(job.skills, job.skill_importances):
            if imp >= 4:
                total_req += 1
                if skill not in cv_set:
                    missing_req += 1
        missing_ratio = missing_req / max(total_req, 1)

        # 7-10. Counts + seniority
        matched_count = len(intersection)
        total_job_skills = len(job_set)
        sen_dist = abs(int(cv.seniority) - int(job.seniority))
        sen_score = max(0.0, 1.0 - sen_dist * 0.4)

        # 11-15. Role + meta features
        cv_role = infer_role(cv.skills, cv.text)
        job_role = infer_role(job.skills, job.text)
        role_pen = role_match_penalty(cv_role, job_role)
        tool_ratio = self._tool_ratio(cv_set)

        # 16-20. Stage 1 + GNN + penalty signals
        stage1_score = stage1_score_override if stage1_score_override is not None else self._stage1_scores.get(job.job_id, 0.5)
        gnn_rank = float(self._stage1_ranks.get(job.job_id, 50)) / 50.0
        must_have_triggered = 1.0 if missing_req >= 2 else (0.5 if missing_req == 1 else 0.0)
        edge_penalty = 0.0
        if len(cv_set) < 4:
            edge_penalty = 1.0
        if int(cv.seniority) >= 3 and int(job.seniority) <= 1:
            edge_penalty = 1.0
        _TOOL_SKILLS = {"git", "jira", "confluence", "docker", "jenkins", "ci_cd", "npm", "vite", "webpack"}
        if intersection and len(intersection - _TOOL_SKILLS) == 0:
            edge_penalty = 1.0

        # 21-23. New features
        skill_coverage = matched_count / max(total_job_skills, 1)
        if job.experience_min > 0:
            raw_gap = cv.experience_years - job.experience_min
            experience_gap = max(-5.0, min(10.0, raw_gap)) / 10.0
        else:
            experience_gap = 0.0
        if job.role_category:
            role_category_match = 1.0 if cv_role == job.role_category else 0.0
        else:
            role_category_match = 0.5

        return np.array([
            text_sim, jaccard, weighted, semantic,
            missing_req, missing_ratio,
            matched_count, total_job_skills,
            sen_dist, sen_score,
            role_pen, cv.experience_years, len(cv_set),
            self._skill_specificity(cv_set), tool_ratio,
            stage1_score, gnn_score,
            gnn_rank, must_have_triggered, edge_penalty,
            skill_coverage, experience_gap, role_category_match,
        ], dtype=np.float32)

    def _text_similarity(self, cv: CVData, job: JobData) -> float:
        vecs = self._embed.encode([cv.text, job.text])
        cv_vec, job_vec = vecs[0], vecs[1]
        norm_cv = np.linalg.norm(cv_vec)
        norm_job = np.linalg.norm(job_vec)
        if norm_cv == 0 or norm_job == 0:
            return 0.0
        sim = float(np.dot(cv_vec, job_vec) / (norm_cv * norm_job))
        return (sim + 1.0) / 2.0

    @staticmethod
    def _weighted_overlap(cv_set: set[str], job: JobData) -> float:
        if not job.skills:
            return 0.0
        total_w, matched_w = 0.0, 0.0
        for skill, imp in zip(job.skills, job.skill_importances):
            total_w += imp
            if skill in cv_set:
                matched_w += imp
        return matched_w / total_w if total_w else 0.0

    def _semantic_overlap(self, cv_set: set[str], job: JobData) -> float:
        if not job.skills:
            return 0.0
        total_w, matched_w = 0.0, 0.0
        for skill, imp in zip(job.skills, job.skill_importances):
            total_w += imp
            if skill in cv_set:
                matched_w += imp
            else:
                best_sim = 0.0
                for cv_skill in cv_set:
                    pair = (min(skill, cv_skill), max(skill, cv_skill))
                    sim = self._skill_sim.get(pair, 0.0)
                    best_sim = max(best_sim, sim)
                if best_sim > 0:
                    matched_w += imp * best_sim * 0.6
        return min(matched_w / total_w, 1.0) if total_w else 0.0

    def _skill_specificity(self, cv_skills: set[str]) -> float:
        """Average rarity of CV skills. Higher = more specialized."""
        if not cv_skills or not self._skill_sim:
            return 0.5
        # Skills with fewer co-occurrence partners are more specific
        partner_counts = []
        for skill in cv_skills:
            count = sum(1 for (a, b) in self._skill_sim if a == skill or b == skill)
            partner_counts.append(count)
        if not partner_counts:
            return 0.5
        avg = sum(partner_counts) / len(partner_counts)
        # Normalize: fewer partners = higher specificity
        return max(0.0, 1.0 - avg / 20.0)

    def _tool_ratio(self, cv_skills: set[str]) -> float:
        """Fraction of CV skills that are tools (git, jira, etc.)."""
        if not cv_skills or not self._skill_cats:
            return 0.0
        tool_count = sum(1 for s in cv_skills if self._skill_cats.get(s) == 2)
        return tool_count / len(cv_skills)
