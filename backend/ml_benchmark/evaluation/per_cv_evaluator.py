"""Per-CV evaluation: each CV ranks ALL jobs, metrics computed per-CV then averaged.

Protocol follows LightGCN (He et al., SIGIR 2020) and RecBole full-ranking mode:
  1. For each test CV, score ALL jobs
  2. Exclude jobs seen in training (avoid trivial recommendations)
  3. Rank by score descending
  4. Compare against held-out test positives
  5. Compute metrics per CV, then macro-average

Reference: Krichene & Rendle (KDD 2020) proved sampled metrics are inconsistent
with exact full-ranking metrics — this implementation uses full ranking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from ml_benchmark.baselines.base import Scorer
from ml_benchmark.evaluation.metrics import (
    hit_rate_at_k,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from ml_benchmark.graph.schema import CVData, DatasetSplit, JobData, LabeledPair

logger = logging.getLogger(__name__)


@dataclass
class PerCVResult:
    """Results from per-CV evaluation."""

    # Macro-averaged metrics across all evaluated CVs
    avg_metrics: dict[str, float] = field(default_factory=dict)

    # Per-CV breakdown: cv_id -> {metric_name: value}
    per_cv_metrics: dict[int, dict[str, float]] = field(default_factory=dict)

    # Summary stats
    num_cvs_evaluated: int = 0
    num_cvs_with_test_positives: int = 0
    avg_test_positives_per_cv: float = 0.0

    # Edge case analysis
    worst_cvs: list[int] = field(default_factory=list)
    best_cvs: list[int] = field(default_factory=list)


def _build_cv_job_sets(
    pairs: list[LabeledPair],
) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    """Build per-CV sets of positive and all job IDs from labeled pairs."""
    cv_positive_jobs: dict[int, set[int]] = {}
    cv_all_jobs: dict[int, set[int]] = {}
    for p in pairs:
        cv_all_jobs.setdefault(p.cv_id, set()).add(p.job_id)
        if p.label == 1:
            cv_positive_jobs.setdefault(p.cv_id, set()).add(p.job_id)
    return cv_positive_jobs, cv_all_jobs


class PerCVEvaluator:
    """Evaluate a scorer using per-CV full-ranking protocol."""

    def __init__(
        self,
        cvs: list[CVData],
        jobs: list[JobData],
        dataset: DatasetSplit,
        *,
        min_test_positives: int = 1,
    ) -> None:
        self._cvs = cvs
        self._jobs = jobs
        self._cv_map = {c.cv_id: c for c in cvs}
        self._job_map = {j.job_id: j for j in jobs}
        self._dataset = dataset
        self._min_test_positives = min_test_positives

        # Build per-CV ground truth from test split
        self._test_positives, _ = _build_cv_job_sets(dataset.test)

        # Build training exclusion set (jobs CV interacted with during training)
        self._train_jobs: dict[int, set[int]] = {}
        for p in dataset.train:
            self._train_jobs.setdefault(p.cv_id, set()).add(p.job_id)
        # Also exclude val jobs
        for p in dataset.val:
            self._train_jobs.setdefault(p.cv_id, set()).add(p.job_id)

    def evaluate(
        self,
        scorer: Scorer,
        ks: tuple[int, ...] = (5, 10, 20, 50),
    ) -> PerCVResult:
        """Run per-CV full-ranking evaluation for a baseline scorer.

        For each test CV:
          1. Score ALL jobs using scorer.score(cv, job)
          2. Exclude jobs seen in training/val
          3. Rank remaining jobs by score
          4. Compute metrics against test positives
        """
        return self._run_evaluation(
            score_fn=lambda cv, job: scorer.score(cv, job),
            ks=ks,
        )

    def evaluate_with_score_fn(
        self,
        score_fn,
        ks: tuple[int, ...] = (5, 10, 20, 50),
    ) -> PerCVResult:
        """Run per-CV evaluation with a custom scoring function.

        Args:
            score_fn: Callable(cv: CVData, job: JobData) -> float
            ks: Tuple of K values for top-K metrics.
        """
        return self._run_evaluation(score_fn=score_fn, ks=ks)

    def _run_evaluation(
        self,
        score_fn,
        ks: tuple[int, ...],
        batch_score_fn=None,
    ) -> PerCVResult:
        """Core evaluation loop."""
        result = PerCVResult()
        all_cv_metrics: list[dict[str, float]] = []
        total_test_positives = 0

        # Get test CVs that have enough positives
        eligible_cvs = {
            cv_id: positives
            for cv_id, positives in self._test_positives.items()
            if len(positives) >= self._min_test_positives
            and cv_id in self._cv_map
        }

        result.num_cvs_with_test_positives = len(self._test_positives)
        result.num_cvs_evaluated = len(eligible_cvs)

        if not eligible_cvs:
            logger.warning("No CVs with >= %d test positives", self._min_test_positives)
            return result

        logger.info(
            "Per-CV evaluation: %d CVs (of %d with test positives, min_positives=%d)",
            len(eligible_cvs),
            len(self._test_positives),
            self._min_test_positives,
        )

        log_every = max(1, len(eligible_cvs) // 10)
        for i, (cv_id, relevant_jobs) in enumerate(eligible_cvs.items()):
            cv_data = self._cv_map[cv_id]
            exclude_jobs = self._train_jobs.get(cv_id, set())
            total_test_positives += len(relevant_jobs)

            cv_metrics = self._evaluate_single_cv(
                cv_data=cv_data,
                relevant_job_ids=relevant_jobs,
                exclude_job_ids=exclude_jobs,
                score_fn=score_fn,
                batch_score_fn=batch_score_fn,
                ks=ks,
            )
            result.per_cv_metrics[cv_id] = cv_metrics
            all_cv_metrics.append(cv_metrics)

            if (i + 1) % log_every == 0:
                logger.info("  Progress: %d/%d CVs done", i + 1, len(eligible_cvs))

        # Macro-average across CVs
        if all_cv_metrics:
            all_keys = all_cv_metrics[0].keys()
            result.avg_metrics = {
                key: float(np.mean([m[key] for m in all_cv_metrics]))
                for key in all_keys
            }
            result.avg_test_positives_per_cv = total_test_positives / len(eligible_cvs)

            # Find best/worst CVs by NDCG@10 (or first available K)
            sort_key = f"ndcg@{ks[1]}" if len(ks) > 1 else f"ndcg@{ks[0]}"
            if sort_key not in all_cv_metrics[0]:
                sort_key = next(iter(all_keys))

            sorted_cvs = sorted(
                result.per_cv_metrics.items(),
                key=lambda x: x[1].get(sort_key, 0.0),
            )
            result.worst_cvs = [cv_id for cv_id, _ in sorted_cvs[:5]]
            result.best_cvs = [cv_id for cv_id, _ in sorted_cvs[-5:]]

        logger.info("Per-CV avg metrics: %s", result.avg_metrics)
        return result

    def evaluate_from_matrix(
        self,
        score_matrix: np.ndarray,
        cv_index: list[int],
        ks: tuple[int, ...] = (5, 10, 20, 50),
    ) -> PerCVResult:
        """Full-ranking evaluation using precomputed score matrix[i_cv, i_job].

        score_matrix: ndarray[n_cvs, n_jobs] — row order matches cv_index, col order matches self._jobs
        cv_index: list of cv_ids, mapping row i → cv_id
        """
        result = PerCVResult()
        all_cv_metrics: list[dict[str, float]] = []
        total_test_positives = 0

        eligible_cvs = {
            cv_id: positives
            for cv_id, positives in self._test_positives.items()
            if len(positives) >= self._min_test_positives and cv_id in self._cv_map
        }
        result.num_cvs_with_test_positives = len(self._test_positives)
        result.num_cvs_evaluated = len(eligible_cvs)

        if not eligible_cvs:
            return result

        cv_row = {cv_id: i for i, cv_id in enumerate(cv_index)}
        log_every = max(1, len(eligible_cvs) // 10)
        logger.info("Matrix full-ranking eval: %d CVs × %d jobs", len(eligible_cvs), len(self._jobs))

        for i, (cv_id, relevant_jobs) in enumerate(eligible_cvs.items()):
            exclude_jobs = self._train_jobs.get(cv_id, set())
            total_test_positives += len(relevant_jobs)

            row_scores = score_matrix[cv_row[cv_id]].copy()
            candidate_mask = np.array([j.job_id not in exclude_jobs for j in self._jobs])
            candidate_scores = row_scores[candidate_mask]
            y_true = np.array(
                [1 if j.job_id in relevant_jobs else 0
                 for j in self._jobs if j.job_id not in exclude_jobs]
            )

            metrics: dict[str, float] = {}
            for k in ks:
                metrics[f"recall@{k}"] = recall_at_k(y_true, candidate_scores, k)
                metrics[f"precision@{k}"] = precision_at_k(y_true, candidate_scores, k)
                metrics[f"ndcg@{k}"] = ndcg_at_k(y_true, candidate_scores, k)
                metrics[f"hit_rate@{k}"] = hit_rate_at_k(y_true, candidate_scores, k)
            metrics["mrr"] = mrr(y_true, candidate_scores)

            result.per_cv_metrics[cv_id] = metrics
            all_cv_metrics.append(metrics)

            if (i + 1) % log_every == 0:
                logger.info("  Progress: %d/%d CVs done", i + 1, len(eligible_cvs))

        if all_cv_metrics:
            all_keys = all_cv_metrics[0].keys()
            result.avg_metrics = {
                key: float(np.mean([m[key] for m in all_cv_metrics]))
                for key in all_keys
            }
            result.avg_test_positives_per_cv = total_test_positives / len(eligible_cvs)
            sort_key = f"ndcg@{ks[1]}" if len(ks) > 1 else f"ndcg@{ks[0]}"
            sorted_cvs = sorted(result.per_cv_metrics.items(), key=lambda x: x[1].get(sort_key, 0.0))
            result.worst_cvs = [cv_id for cv_id, _ in sorted_cvs[:5]]
            result.best_cvs = [cv_id for cv_id, _ in sorted_cvs[-5:]]

        logger.info("Matrix eval avg: %s", result.avg_metrics)
        return result

    def evaluate_twostage_matrix(
        self,
        stage1_matrix: np.ndarray,
        cv_index: list[int],
        stage2_batch_fn,
        retrieve_n: int = 100,
        ks: tuple[int, ...] = (5, 10, 20, 50),
    ) -> PerCVResult:
        """2-stage evaluation using a precomputed Stage 1 score matrix.

        stage1_matrix: ndarray[n_cvs, n_jobs] — precomputed by SkillOverlapScorer.build_matrix()
        cv_index: list mapping row i → cv_id (same order as cvs passed to build_matrix)
        """
        result = PerCVResult()
        all_cv_metrics: list[dict[str, float]] = []
        total_test_positives = 0
        stage1_hits = 0

        eligible_cvs = {
            cv_id: positives
            for cv_id, positives in self._test_positives.items()
            if len(positives) >= self._min_test_positives
            and cv_id in self._cv_map
        }

        result.num_cvs_with_test_positives = len(self._test_positives)
        result.num_cvs_evaluated = len(eligible_cvs)

        if not eligible_cvs:
            return result

        logger.info("2-stage eval (matrix): %d CVs, retrieve_n=%d", len(eligible_cvs), retrieve_n)
        cv_row = {cv_id: i for i, cv_id in enumerate(cv_index)}
        log_every = max(1, len(eligible_cvs) // 10)

        for i, (cv_id, relevant_jobs) in enumerate(eligible_cvs.items()):
            cv_data = self._cv_map[cv_id]
            exclude_jobs = self._train_jobs.get(cv_id, set())
            total_test_positives += len(relevant_jobs)

            # Use precomputed Stage 1 row, zero out excluded jobs
            row_idx = cv_row[cv_id]
            s1_row = stage1_matrix[row_idx].copy()
            candidate_jobs = self._jobs
            for j_idx, job in enumerate(candidate_jobs):
                if job.job_id in exclude_jobs:
                    s1_row[j_idx] = -1.0

            top_n_idx = np.argsort(s1_row)[::-1][:retrieve_n]
            stage1_candidates = [candidate_jobs[j] for j in top_n_idx if s1_row[j] >= 0]

            retrieved_ids = {j.job_id for j in stage1_candidates}
            stage1_hits += len(relevant_jobs & retrieved_ids)

            s2_scores = stage2_batch_fn(cv_data, stage1_candidates)
            y_true = np.array([1 if j.job_id in relevant_jobs else 0 for j in stage1_candidates])

            metrics: dict[str, float] = {}
            for k in ks:
                metrics[f"recall@{k}"] = recall_at_k(y_true, s2_scores, k)
                metrics[f"precision@{k}"] = precision_at_k(y_true, s2_scores, k)
                metrics[f"ndcg@{k}"] = ndcg_at_k(y_true, s2_scores, k)
                metrics[f"hit_rate@{k}"] = hit_rate_at_k(y_true, s2_scores, k)
            metrics["mrr"] = mrr(y_true, s2_scores)

            result.per_cv_metrics[cv_id] = metrics
            all_cv_metrics.append(metrics)

            if (i + 1) % log_every == 0:
                logger.info("  Progress: %d/%d CVs done", i + 1, len(eligible_cvs))

        if all_cv_metrics:
            all_keys = all_cv_metrics[0].keys()
            result.avg_metrics = {
                key: float(np.mean([m[key] for m in all_cv_metrics]))
                for key in all_keys
            }
            result.avg_test_positives_per_cv = total_test_positives / len(eligible_cvs)
            sort_key = f"ndcg@{ks[1]}" if len(ks) > 1 else f"ndcg@{ks[0]}"
            sorted_cvs = sorted(result.per_cv_metrics.items(), key=lambda x: x[1].get(sort_key, 0.0))
            result.worst_cvs = [cv_id for cv_id, _ in sorted_cvs[:5]]
            result.best_cvs = [cv_id for cv_id, _ in sorted_cvs[-5:]]

        stage1_recall = stage1_hits / max(total_test_positives, 1)
        logger.info("Stage1 recall@%d = %.4f | avg: %s", retrieve_n, stage1_recall, result.avg_metrics)
        return result

    def evaluate_twostage(
        self,
        stage1_scorer: Scorer,
        stage2_batch_fn,
        retrieve_n: int = 100,
        ks: tuple[int, ...] = (5, 10, 20, 50),
    ) -> PerCVResult:
        """2-stage evaluation: Stage 1 retrieves top-N, Stage 2 re-ranks.

        Reflects the real production pipeline:
          Stage 1 (fast): Skill Overlap scores all jobs → top-retrieve_n candidates
          Stage 2 (GNN):  re-ranks retrieve_n candidates → final top-K

        Stage 1 recall@retrieve_n is logged as the ceiling for Stage 2.
        If Stage 1 misses a relevant job, Stage 2 cannot recover it.
        """
        result = PerCVResult()
        all_cv_metrics: list[dict[str, float]] = []
        total_test_positives = 0
        stage1_hits = 0

        eligible_cvs = {
            cv_id: positives
            for cv_id, positives in self._test_positives.items()
            if len(positives) >= self._min_test_positives
            and cv_id in self._cv_map
        }

        result.num_cvs_with_test_positives = len(self._test_positives)
        result.num_cvs_evaluated = len(eligible_cvs)

        if not eligible_cvs:
            logger.warning("No CVs with >= %d test positives", self._min_test_positives)
            return result

        logger.info(
            "2-stage eval: %d CVs, Stage1 retrieve_n=%d", len(eligible_cvs), retrieve_n
        )
        log_every = max(1, len(eligible_cvs) // 10)

        for i, (cv_id, relevant_jobs) in enumerate(eligible_cvs.items()):
            cv_data = self._cv_map[cv_id]
            exclude_jobs = self._train_jobs.get(cv_id, set())
            total_test_positives += len(relevant_jobs)

            # Stage 1: score all jobs with fast scorer, take top retrieve_n
            candidate_jobs = [j for j in self._jobs if j.job_id not in exclude_jobs]
            s1_scores = np.array([stage1_scorer.score(cv_data, j) for j in candidate_jobs])
            top_n_idx = np.argsort(s1_scores)[::-1][:retrieve_n]
            stage1_candidates = [candidate_jobs[i] for i in top_n_idx]

            # Track Stage 1 coverage (ceiling for Stage 2)
            retrieved_ids = {j.job_id for j in stage1_candidates}
            stage1_hits += len(relevant_jobs & retrieved_ids)

            # Stage 2: GNN re-ranks Stage 1 candidates
            s2_scores = stage2_batch_fn(cv_data, stage1_candidates)
            y_true = np.array(
                [1 if j.job_id in relevant_jobs else 0 for j in stage1_candidates]
            )

            metrics: dict[str, float] = {}
            for k in ks:
                metrics[f"recall@{k}"] = recall_at_k(y_true, s2_scores, k)
                metrics[f"precision@{k}"] = precision_at_k(y_true, s2_scores, k)
                metrics[f"ndcg@{k}"] = ndcg_at_k(y_true, s2_scores, k)
                metrics[f"hit_rate@{k}"] = hit_rate_at_k(y_true, s2_scores, k)
            metrics["mrr"] = mrr(y_true, s2_scores)

            result.per_cv_metrics[cv_id] = metrics
            all_cv_metrics.append(metrics)

            if (i + 1) % log_every == 0:
                logger.info("  Progress: %d/%d CVs done", i + 1, len(eligible_cvs))

        if all_cv_metrics:
            all_keys = all_cv_metrics[0].keys()
            result.avg_metrics = {
                key: float(np.mean([m[key] for m in all_cv_metrics]))
                for key in all_keys
            }
            result.avg_test_positives_per_cv = total_test_positives / len(eligible_cvs)

            sort_key = f"ndcg@{ks[1]}" if len(ks) > 1 else f"ndcg@{ks[0]}"
            sorted_cvs = sorted(
                result.per_cv_metrics.items(),
                key=lambda x: x[1].get(sort_key, 0.0),
            )
            result.worst_cvs = [cv_id for cv_id, _ in sorted_cvs[:5]]
            result.best_cvs = [cv_id for cv_id, _ in sorted_cvs[-5:]]

        stage1_recall = stage1_hits / max(total_test_positives, 1)
        logger.info(
            "Stage1 recall@%d = %.4f (ceiling for Stage2) | avg metrics: %s",
            retrieve_n, stage1_recall, result.avg_metrics,
        )
        return result

    def evaluate_batch(
        self,
        batch_score_fn,
        ks: tuple[int, ...] = (5, 10, 20, 50),
    ) -> PerCVResult:
        """Run per-CV evaluation with batch scoring (scores all jobs for one CV at once).

        Args:
            batch_score_fn: Callable(cv: CVData, jobs: list[JobData]) -> np.ndarray
                Returns an array of scores, one per job.
            ks: Tuple of K values for top-K metrics.
        """
        return self._run_evaluation(score_fn=None, batch_score_fn=batch_score_fn, ks=ks)

    def _evaluate_single_cv(
        self,
        cv_data: CVData,
        relevant_job_ids: set[int],
        exclude_job_ids: set[int],
        score_fn,
        batch_score_fn,
        ks: tuple[int, ...],
    ) -> dict[str, float]:
        """Score all jobs for one CV, compute ranking metrics."""
        # Score all jobs except excluded ones
        candidate_jobs = [
            j for j in self._jobs if j.job_id not in exclude_job_ids
        ]

        if not candidate_jobs:
            return {f"{m}@{k}": 0.0 for k in ks for m in ("recall", "precision", "ndcg", "hit_rate")}

        if batch_score_fn is not None:
            scores = batch_score_fn(cv_data, candidate_jobs)
        else:
            scores = np.array([score_fn(cv_data, j) for j in candidate_jobs])

        # Build binary relevance array (1 if job in test positives, 0 otherwise)
        y_true = np.array(
            [1 if j.job_id in relevant_job_ids else 0 for j in candidate_jobs]
        )

        # Compute metrics
        metrics: dict[str, float] = {}
        for k in ks:
            metrics[f"recall@{k}"] = recall_at_k(y_true, scores, k)
            metrics[f"precision@{k}"] = precision_at_k(y_true, scores, k)
            metrics[f"ndcg@{k}"] = ndcg_at_k(y_true, scores, k)
            metrics[f"hit_rate@{k}"] = hit_rate_at_k(y_true, scores, k)
        metrics["mrr"] = mrr(y_true, scores)

        return metrics


def print_per_cv_results(
    results: dict[str, PerCVResult],
    ks: tuple[int, ...] = (5, 10, 20, 50),
) -> None:
    """Print a comparison table of per-CV evaluation results."""
    metrics_order = []
    for k in ks:
        metrics_order.extend([f"recall@{k}", f"ndcg@{k}"])
    metrics_order.extend(["mrr", f"hit_rate@{ks[1] if len(ks) > 1 else ks[0]}"])

    col_w, name_w = 12, 28
    header = f"{'Method':<{name_w}}" + "".join(f"{m:>{col_w}}" for m in metrics_order)
    print("\n" + "=" * (name_w + col_w * len(metrics_order)))
    print("  Per-CV Full-Ranking Evaluation")
    print("=" * (name_w + col_w * len(metrics_order)))
    print(header)
    print("-" * (name_w + col_w * len(metrics_order)))

    # Find best per column
    best: dict[str, str] = {}
    for m in metrics_order:
        vals = [(name, r.avg_metrics.get(m, 0.0)) for name, r in results.items()]
        if vals:
            best[m] = max(vals, key=lambda x: x[1])[0]

    for name, r in results.items():
        row = f"{name:<{name_w}}"
        for m in metrics_order:
            val = r.avg_metrics.get(m, 0.0)
            marker = " *" if best.get(m) == name else "  "
            row += f"{val:>{col_w - 2}.4f}{marker}"
        print(row)

    print("=" * (name_w + col_w * len(metrics_order)))
    print("  * = best in column")

    # Print summary for first result
    first_result = next(iter(results.values()))
    print(f"\n  CVs evaluated: {first_result.num_cvs_evaluated}")
    print(f"  Avg test positives/CV: {first_result.avg_test_positives_per_cv:.1f}")
