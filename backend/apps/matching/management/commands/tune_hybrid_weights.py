"""Tune the hybrid score weights (alpha/beta/gamma) by grid-search (feature 019).

score = alpha*GNN + beta*skill + gamma*seniority. We sweep the weight simplex on
a fixed grid over a held-out split of the labeled match/no_match pairs, pick the
AUC-maximizing combo, print + write an ablation table, and (optionally) persist
the winner to the checkpoint metadata.json — the single source of truth the
engine then loads. Offline, deterministic.

    python manage.py tune_hybrid_weights              # analyze + write ablation.md
    python manage.py tune_hybrid_weights --write      # also persist winner to metadata.json
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

LEGACY = (0.55, 0.30, 0.15)


class Command(BaseCommand):
    help = "Grid-search the hybrid weights (alpha/beta/gamma) on labeled pairs; emit an ablation table."

    def add_arguments(self, parser):
        parser.add_argument("--grid", type=float, default=0.05, help="Weight lattice step (default 0.05).")
        parser.add_argument("--val-frac", type=float, default=0.2, help="Validation fraction (default 0.2).")
        parser.add_argument("--seed", type=int, default=42, help="Split seed (default 42).")
        parser.add_argument("--write", action="store_true", help="Persist the winner to checkpoint metadata.json.")
        parser.add_argument(
            "--out", default="specs/019-match-weight-calibration/ablation.md",
            help="Ablation table output path (repo-relative).",
        )

    def handle(self, *args, **opts):
        import numpy as np

        engine = self._load_pure_checkpoint_engine()
        self.stdout.write("Extracting labeled pair components…")
        comp = engine.labeled_pair_components()
        if not comp:
            raise CommandError("No labeled match/no_match edges in the checkpoint graph.")

        cv_idx = np.array([c[0] for c in comp])
        label = np.array([c[2] for c in comp], dtype=np.int64)
        gnn = np.array([c[3] for c in comp], dtype=np.float64)
        skill = np.array([c[4] for c in comp], dtype=np.float64)
        sen = np.array([c[5] for c in comp], dtype=np.float64)

        n_pos, n_neg = int((label == 1).sum()), int((label == 0).sum())
        self.stdout.write(f"  pairs={len(label)} (match {n_pos} / no_match {n_neg})")
        if n_pos == 0 or n_neg == 0:
            raise CommandError("Validation needs BOTH match and no_match pairs (AUC undefined).")

        # Deterministic split
        rng = np.random.RandomState(opts["seed"])
        perm = rng.permutation(len(label))
        n_val = max(1, int(len(label) * opts["val_frac"]))
        vi = perm[:n_val]
        vL, vG, vS, vSen = label[vi], gnn[vi], skill[vi], sen[vi]
        vCV = cv_idx[vi]
        if vL.min() == vL.max():
            raise CommandError("Validation split ended up single-class; adjust --seed/--val-frac.")
        self.stdout.write(f"  validation pairs={n_val}")

        auc_fn = self._auc_fn()

        # Sweep the simplex on the grid
        step = opts["grid"]
        combos = self._simplex(step)
        rows = []
        for a, b, g in combos:
            score = a * vG + b * vS + g * vSen
            rows.append((a, b, g, float(auc_fn(vL, score))))
        rows.sort(key=lambda r: -r[3])

        # Tie-break: among the top AUC, prefer the combo closest to LEGACY
        top_auc = rows[0][3]
        best = min(
            [r for r in rows if abs(r[3] - top_auc) < 1e-9],
            key=lambda r: (r[0] - LEGACY[0]) ** 2 + (r[1] - LEGACY[1]) ** 2 + (r[2] - LEGACY[2]) ** 2,
        )
        legacy_auc = float(auc_fn(vL, LEGACY[0] * vG + LEGACY[1] * vS + LEGACY[2] * vSen))

        # Secondary metrics for winner + legacy only
        bw = best[:3]
        ndcg_best, p_best = self._ranking_metrics(vCV, vL, bw[0] * vG + bw[1] * vS + bw[2] * vSen)
        ndcg_leg, p_leg = self._ranking_metrics(vCV, vL, LEGACY[0] * vG + LEGACY[1] * vS + LEGACY[2] * vSen)

        self.stdout.write(self.style.SUCCESS(
            f"Best: α={best[0]:.2f} β={best[1]:.2f} γ={best[2]:.2f}  AUC={best[3]:.4f}"
            f"  (legacy {LEGACY[0]}/{LEGACY[1]}/{LEGACY[2]} AUC={legacy_auc:.4f})"
        ))

        self._write_ablation(
            Path(settings.BASE_DIR).parent / opts["out"],
            rows, best, legacy_auc, (n_pos, n_neg, n_val),
            (ndcg_best, p_best), (ndcg_leg, p_leg), opts,
        )
        self.stdout.write(f"Ablation → {opts['out']}")

        if opts["write"]:
            self._persist(best, opts["grid"])
            self.stdout.write(self.style.SUCCESS("metadata.json updated with tuned hybrid_weights."))
        else:
            self.stdout.write("Dry run — pass --write to persist the winner.")

    # ------------------------------------------------------------------
    def _load_pure_checkpoint_engine(self):
        from ml_service.data.skill_normalization import SkillNormalizer
        from ml_service.embedding import get_provider
        from ml_service.inference import InferenceEngine

        self.stdout.write("Loading engine (checkpoint pool, no live snapshot)…")
        normalizer = SkillNormalizer(settings.ML_SKILL_ALIAS_PATH)
        provider = get_provider()
        # job_pool_dir to an absent path → labels' training jobs stay in self._jobs
        return InferenceEngine.from_checkpoint(
            settings.ML_CHECKPOINT_DIR, normalizer=normalizer,
            embedding_provider=provider, job_pool_dir="/nonexistent/job_pool",
        )

    @staticmethod
    def _simplex(step: float):
        import numpy as np
        n = int(round(1.0 / step))
        out = []
        for i in range(n + 1):
            for j in range(n + 1 - i):
                a, b = round(i * step, 4), round(j * step, 4)
                g = round(1.0 - a - b, 4)
                if g >= -1e-9:
                    out.append((a, b, max(0.0, g)))
        return out

    @staticmethod
    def _auc_fn():
        try:
            from sklearn.metrics import roc_auc_score
            return roc_auc_score
        except Exception:  # noqa: BLE001
            import numpy as np

            def _auc(y, s):  # rank-based AUC fallback
                y = np.asarray(y); s = np.asarray(s)
                order = np.argsort(s, kind="mergesort")
                ranks = np.empty_like(order, dtype=np.float64)
                ranks[order] = np.arange(1, len(s) + 1)
                pos = y == 1
                n_pos, n_neg = pos.sum(), (~pos).sum()
                if n_pos == 0 or n_neg == 0:
                    return 0.5
                return (ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
            return _auc

    @staticmethod
    def _ranking_metrics(cv_idx, label, score, k: int = 10):
        """Mean NDCG@k + precision@k grouped by CV (CVs with >=1 positive)."""
        import numpy as np
        ndcgs, precs = [], []
        for cv in np.unique(cv_idx):
            m = cv_idx == cv
            y, s = label[m], score[m]
            if y.sum() == 0:
                continue
            order = np.argsort(-s, kind="mergesort")[:k]
            gains = y[order]
            dcg = np.sum(gains / np.log2(np.arange(2, len(gains) + 2)))
            ideal = np.sort(y)[::-1][:k]
            idcg = np.sum(ideal / np.log2(np.arange(2, len(ideal) + 2)))
            ndcgs.append(dcg / idcg if idcg > 0 else 0.0)
            precs.append(gains.mean() if len(gains) else 0.0)
        return (float(np.mean(ndcgs)) if ndcgs else 0.0, float(np.mean(precs)) if precs else 0.0)

    def _write_ablation(self, path: Path, rows, best, legacy_auc, counts, best_sec, leg_sec, opts):
        path.parent.mkdir(parents=True, exist_ok=True)
        n_pos, n_neg, n_val = counts
        lines = [
            "# Hybrid-weight ablation (feature 019)",
            "",
            f"Labeled pairs: {n_pos + n_neg} (match {n_pos} / no_match {n_neg}) · "
            f"validation {n_val} · grid {opts['grid']} · seed {opts['seed']} · metric AUC.",
            "",
            "| rank | α | β | γ | AUC | note |",
            "|---|---|---|---|-----|------|",
        ]
        for i, (a, b, g, auc) in enumerate(rows[:15], 1):
            note = "**← chosen**" if (a, b, g) == tuple(best[:3]) else ""
            lines.append(f"| {i} | {a:.2f} | {b:.2f} | {g:.2f} | {auc:.4f} | {note} |")
        lines += [
            "",
            f"**Chosen**: α={best[0]:.2f} β={best[1]:.2f} γ={best[2]:.2f} · "
            f"AUC={best[3]:.4f} · NDCG@10={best_sec[0]:.4f} · P@10={best_sec[1]:.4f}",
            f"**Legacy (0.55/0.30/0.15)**: AUC={legacy_auc:.4f} · "
            f"NDCG@10={leg_sec[0]:.4f} · P@10={leg_sec[1]:.4f}",
            "",
            f"Δ AUC vs legacy: {best[3] - legacy_auc:+.4f} (≥ 0 by construction — the grid includes legacy).",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _persist(best, grid):
        meta_path = Path(settings.ML_CHECKPOINT_DIR) / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        meta["hybrid_weights"] = {"alpha": round(best[0], 4), "beta": round(best[1], 4), "gamma": round(best[2], 4)}
        meta["hybrid_weights_meta"] = {"metric": "auc", "auc": round(best[3], 4), "grid_step": grid}
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
