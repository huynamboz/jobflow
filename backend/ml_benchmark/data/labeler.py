from __future__ import annotations

import random as _random_mod

from ml_benchmark.data.skill_graph import build_skill_cooccurrence
from ml_benchmark.data.skill_taxonomy import cluster_coverage
from ml_benchmark.graph.schema import CVData, DatasetSplit, JobData, LabeledPair


class PairLabeler:
    """Threshold-based pair labeling with stratified train/val/test split."""

    def __init__(self, seed: int = 42) -> None:
        self._rng = _random_mod.Random(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_pairs(
        self,
        cvs: list[CVData],
        jobs: list[JobData],
        num_positive: int,
        *,
        cv_text_skills: dict[int, set[str]] | None = None,
        job_clusters: dict[int, list[str]] | None = None,
        noise_rate: float = 0.0,
        use_skill_relations: bool = False,
    ) -> list[LabeledPair]:
        """Classify all CV-Job pairs, then sample with 1:1:2 ratio.

        When use_skill_relations=True, pairs with low direct skill overlap
        but high related-skill overlap are labeled positive. This creates
        positives that skill-overlap baseline CANNOT detect, but GNN can
        via Skill→Skill edges.

        Example: CV has "Flask, Celery", JD requires "Django"
        → direct overlap = 0, but Flask relates_to Django → positive
        """
        cv_text_skills = cv_text_skills or {}
        job_clusters = job_clusters or {}

        # Build related-skill lookup if enabled
        related_skills: dict[str, set[str]] = {}
        if use_skill_relations:
            cooccurrence = build_skill_cooccurrence(cvs, jobs)
            for (a, b), pmi in cooccurrence.items():
                related_skills.setdefault(a, set()).add(b)
                related_skills.setdefault(b, set()).add(a)

        positives: list[tuple[int, int]] = []
        easy_negs: list[tuple[int, int]] = []
        hard_negs: list[tuple[int, int]] = []

        for cv in cvs:
            effective_skills = set(cv.skills) | cv_text_skills.get(cv.cv_id, set())

            # Expanded skills = effective + related skills (for labeling only)
            if related_skills:
                expanded_skills = set(effective_skills)
                for sk in list(effective_skills):
                    expanded_skills.update(related_skills.get(sk, set()))
            else:
                expanded_skills = effective_skills

            for job in jobs:
                direct_overlap = self._skill_overlap_effective(effective_skills, job)
                expanded_overlap = self._skill_overlap_effective(expanded_skills, job)
                dist = self._seniority_distance(cv, job)
                clusters = job_clusters.get(job.job_id, [])
                clust_cov = cluster_coverage(effective_skills, clusters) if clusters else 0.0

                is_positive = (
                    (direct_overlap >= 0.4 and dist <= 1)
                    or (clust_cov >= 0.6 and dist <= 1)
                    or (expanded_overlap >= 0.55 and dist <= 1 and direct_overlap < 0.4)
                )

                if is_positive:
                    positives.append((cv.cv_id, job.job_id))
                elif direct_overlap < 0.15 or dist >= 3:
                    easy_negs.append((cv.cv_id, job.job_id))
                elif 0.15 <= direct_overlap < 0.5 and dist <= 1:
                    hard_negs.append((cv.cv_id, job.job_id))
                # else: ambiguous — skip

        # Sample desired counts (cap to available)
        n_pos = min(num_positive, len(positives))
        n_easy = min(n_pos, len(easy_negs))
        n_hard = min(2 * n_pos, len(hard_negs))

        sampled_pos = self._rng.sample(positives, n_pos)
        sampled_easy = self._rng.sample(easy_negs, n_easy)
        sampled_hard = self._rng.sample(hard_negs, n_hard)

        pairs: list[LabeledPair] = []
        for cv_id, job_id in sampled_pos:
            pairs.append(LabeledPair(cv_id=cv_id, job_id=job_id, label=1))
        for cv_id, job_id in sampled_easy:
            pairs.append(LabeledPair(cv_id=cv_id, job_id=job_id, label=0))
        for cv_id, job_id in sampled_hard:
            pairs.append(LabeledPair(cv_id=cv_id, job_id=job_id, label=0))

        # Apply label noise
        if noise_rate > 0 and pairs:
            n_flip = max(1, int(len(pairs) * noise_rate))
            flip_indices = self._rng.sample(range(len(pairs)), min(n_flip, len(pairs)))
            for i in flip_indices:
                p = pairs[i]
                flipped = 0 if p.label == 1 else 1
                pairs[i] = LabeledPair(cv_id=p.cv_id, job_id=p.job_id, label=flipped)

        self._rng.shuffle(pairs)
        return pairs

    def split(self, pairs: list[LabeledPair]) -> DatasetSplit:
        """Stratified 75/15/10 split (by label)."""
        pos = [p for p in pairs if p.label == 1]
        neg = [p for p in pairs if p.label == 0]
        self._rng.shuffle(pos)
        self._rng.shuffle(neg)

        def _split_list(items: list[LabeledPair]) -> tuple[list, list, list]:
            n = len(items)
            n_train = int(n * 0.75)
            n_val = int(n * 0.15)
            train = [LabeledPair(p.cv_id, p.job_id, p.label, "train") for p in items[:n_train]]
            val = [
                LabeledPair(p.cv_id, p.job_id, p.label, "val")
                for p in items[n_train : n_train + n_val]
            ]
            test = [
                LabeledPair(p.cv_id, p.job_id, p.label, "test") for p in items[n_train + n_val :]
            ]
            return train, val, test

        pos_train, pos_val, pos_test = _split_list(pos)
        neg_train, neg_val, neg_test = _split_list(neg)

        train = pos_train + neg_train
        val = pos_val + neg_val
        test = pos_test + neg_test
        self._rng.shuffle(train)
        self._rng.shuffle(val)
        self._rng.shuffle(test)

        return DatasetSplit(train=train, val=val, test=test)

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _skill_overlap(cv: CVData, job: JobData) -> float:
        """Fraction of job-required skills present in the CV."""
        if not job.skills:
            return 0.0
        cv_set = set(cv.skills)
        job_set = set(job.skills)
        return len(cv_set & job_set) / len(job_set)

    @staticmethod
    def _skill_overlap_effective(effective_skills: set[str], job: JobData) -> float:
        """Fraction of shared skills, normalized by min set size (Sørensen-Dice).

        Uses min(|CV|, |JD|) as denominator to remove bias towards verbose JDs.
        LinkedIn JDs often list 12-20 skills; without this, well-matched CVs
        with fewer skills would score low overlap and be incorrectly labeled negative.
        """
        if not job.skills:
            return 0.0
        job_set = set(job.skills)
        intersection = len(effective_skills & job_set)
        denom = min(len(effective_skills), len(job_set))
        return intersection / denom if denom > 0 else 0.0

    @staticmethod
    def _seniority_distance(cv: CVData, job: JobData) -> int:
        """Absolute difference in seniority level indices."""
        return abs(int(cv.seniority) - int(job.seniority))
