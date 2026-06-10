"""Tune the hybrid score weights by grid-search (features 019 + 020).

score = α·GNN + β·skill + γ·seniority + δ·domain.  We sweep the 4-weight simplex
on a held-out split of the labeled match/no_match pairs and report TWO objectives
per combo:
  • label-AUC      — separates match/no_match (feature 019; no role labels)
  • role-NDCG@k/P@k — ranks SAME-FIELD jobs on top (feature 020; relevant =
                      infer_role(cv) == job.role_category), grouped by CV.
The winner maximizes --objective (default role_ndcg). A DUAL ablation table is
written for the thesis; --write persists the 4 weights to metadata.json. Offline,
deterministic.

    python manage.py tune_hybrid_weights              # dual ablation, dry
    python manage.py tune_hybrid_weights --write      # persist winner (4 weights)
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

LEGACY = (0.55, 0.30, 0.15, 0.0)            # pre-tuning
LABEL_AUC_WINNER = (0.20, 0.75, 0.05, 0.0)  # feature-019 label-AUC pick (β-heavy, δ=0)


class Command(BaseCommand):
    help = "Grid-search hybrid weights (α/β/γ/δ); dual ablation (label-AUC + role-aware)."

    def add_arguments(self, parser):
        parser.add_argument("--grid", type=float, default=0.05)
        parser.add_argument("--val-frac", type=float, default=0.2)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--k", type=int, default=10, help="cutoff for role NDCG/P@k.")
        parser.add_argument("--objective", default="balanced",
                            choices=["balanced", "role_ndcg", "role_p", "label_auc"])
        parser.add_argument("--min-auc-frac", type=float, default=0.85,
                            help="balanced: keep combos with label-AUC ≥ frac·max (anti-degeneracy).")
        parser.add_argument("--max-delta", type=float, default=0.40,
                            help="cap δ so domain stays a SOFT term (FR-002), not the whole score.")
        parser.add_argument("--write", action="store_true")
        parser.add_argument("--out", default="specs/020-domain-aware-ranking/ablation.md")

    def handle(self, *args, **opts):
        import numpy as np

        engine = self._load_pure_checkpoint_engine()
        self.stdout.write("Extracting labeled pair components (+domain, +roles)…")
        comp = engine.labeled_pair_components()
        if not comp:
            raise CommandError("No labeled match/no_match edges in the checkpoint graph.")

        cv_idx = np.array([c[0] for c in comp])
        label = np.array([c[2] for c in comp], dtype=np.int64)
        gnn = np.array([c[3] for c in comp], dtype=np.float64)
        skill = np.array([c[4] for c in comp], dtype=np.float64)
        sen = np.array([c[5] for c in comp], dtype=np.float64)
        dom = np.array([c[6] for c in comp], dtype=np.float64)
        # role-aware relevance: cv_role == job_role (job.role_category), both non-empty
        rel = np.array([1 if (c[7] and c[8] and c[7] == c[8]) else 0 for c in comp], dtype=np.int64)

        n_pos, n_neg = int((label == 1).sum()), int((label == 0).sum())
        self.stdout.write(f"  pairs={len(label)} (match {n_pos} / no_match {n_neg}) · "
                          f"role-relevant {int(rel.sum())}")
        if n_pos == 0 or n_neg == 0:
            raise CommandError("Validation needs BOTH match and no_match pairs.")

        rng = np.random.RandomState(opts["seed"])
        perm = rng.permutation(len(label))
        n_val = max(1, int(len(label) * opts["val_frac"]))
        vi = perm[:n_val]
        vCV, vL, vRel = cv_idx[vi], label[vi], rel[vi]
        vG, vS, vSen, vD = gnn[vi], skill[vi], sen[vi], dom[vi]
        if vL.min() == vL.max():
            raise CommandError("Validation split single-class; adjust --seed/--val-frac.")
        self.stdout.write(f"  validation pairs={n_val}")

        auc_fn = self._auc_fn()
        k = opts["k"]

        rows = []
        for a, b, g, d in self._simplex4(opts["grid"]):
            score = a * vG + b * vS + g * vSen + d * vD
            auc = float(auc_fn(vL, score))
            ndcg, prec = self._role_metrics(vCV, vRel, score, k)
            rows.append((a, b, g, d, auc, ndcg, prec))

        # Selection. Pure role_ndcg is GAMED by δ=1.0 (score == relevance signal →
        # NDCG=1 but label-AUC collapses). The default "balanced" objective avoids
        # this degeneracy: maximize role-NDCG among combos that (a) keep label-AUC
        # ≥ min_auc_frac·max (still separate match/no_match) and (b) keep δ ≤ max_delta
        # (domain stays a SOFT term, FR-002).
        max_auc = max(r[4] for r in rows)
        if opts["objective"] == "balanced":
            thr = opts["min_auc_frac"] * max_auc
            elig = [r for r in rows if r[4] >= thr and r[3] <= opts["max_delta"] + 1e-9]
            if not elig:
                elig = rows
            best = max(elig, key=lambda r: r[5])  # role-NDCG among eligible
            rows.sort(key=lambda r: -r[5])         # display by role-NDCG (shows δ=1.0 degeneracy on top)
        else:
            key_idx = {"role_ndcg": 5, "role_p": 6, "label_auc": 4}[opts["objective"]]
            rows.sort(key=lambda r: -r[key_idx])
            best = rows[0]

        def metrics_for(w):
            s = w[0] * vG + w[1] * vS + w[2] * vSen + w[3] * vD
            nd, pr = self._role_metrics(vCV, vRel, s, k)
            return (float(auc_fn(vL, s)), nd, pr)
        leg = metrics_for(LEGACY)
        law = metrics_for(LABEL_AUC_WINNER)

        self.stdout.write(self.style.SUCCESS(
            f"Best ({opts['objective']}): α={best[0]:.2f} β={best[1]:.2f} γ={best[2]:.2f} δ={best[3]:.2f}"
            f"  role-NDCG@{k}={best[5]:.4f} role-P@{k}={best[6]:.4f} label-AUC={best[4]:.4f}"
        ))
        self.stdout.write(
            f"  vs label-AUC-winner (0.20/0.75/0.05/0): role-NDCG@{k}={law[1]:.4f} label-AUC={law[0]:.4f}"
        )

        self._write_ablation(
            Path(settings.BASE_DIR).parent / opts["out"], rows, best,
            (n_pos, n_neg, n_val, int(rel.sum())), leg, law, opts, k,
        )
        self.stdout.write(f"Dual ablation → {opts['out']}")

        if opts["write"]:
            self._persist(best, opts["grid"], opts["objective"], k)
            self.stdout.write(self.style.SUCCESS("metadata.json updated with 4 hybrid_weights."))
        else:
            self.stdout.write("Dry run — pass --write to persist.")

    # ------------------------------------------------------------------
    def _load_pure_checkpoint_engine(self):
        from ml_service.data.skill_normalization import SkillNormalizer
        from ml_service.embedding import get_provider
        from ml_service.inference import InferenceEngine

        self.stdout.write("Loading engine (checkpoint pool, no live snapshot)…")
        normalizer = SkillNormalizer(settings.ML_SKILL_ALIAS_PATH)
        provider = get_provider()
        return InferenceEngine.from_checkpoint(
            settings.ML_CHECKPOINT_DIR, normalizer=normalizer,
            embedding_provider=provider, job_pool_dir="/nonexistent/job_pool",
        )

    @staticmethod
    def _simplex4(step: float):
        n = int(round(1.0 / step))
        out = []
        for i in range(n + 1):
            for j in range(n + 1 - i):
                for kk in range(n + 1 - i - j):
                    a, b, c = round(i * step, 4), round(j * step, 4), round(kk * step, 4)
                    d = round(1.0 - a - b - c, 4)
                    if d >= -1e-9:
                        out.append((a, b, c, max(0.0, d)))
        return out

    @staticmethod
    def _role_metrics(cv_idx, rel, score, k):
        """Mean role-aware NDCG@k + precision@k grouped by CV (CVs with ≥1 relevant
        AND ≥2 jobs in the split)."""
        import numpy as np
        ndcgs, precs = [], []
        for cv in np.unique(cv_idx):
            m = cv_idx == cv
            y, s = rel[m], score[m]
            if y.sum() == 0 or len(y) < 2:
                continue
            order = np.argsort(-s, kind="mergesort")[:k]
            gains = y[order]
            dcg = float(np.sum(gains / np.log2(np.arange(2, len(gains) + 2))))
            ideal = np.sort(y)[::-1][:k]
            idcg = float(np.sum(ideal / np.log2(np.arange(2, len(ideal) + 2))))
            ndcgs.append(dcg / idcg if idcg > 0 else 0.0)
            precs.append(float(gains.mean()))
        return (float(np.mean(ndcgs)) if ndcgs else 0.0,
                float(np.mean(precs)) if precs else 0.0)

    @staticmethod
    def _auc_fn():
        try:
            from sklearn.metrics import roc_auc_score
            return roc_auc_score
        except Exception:  # noqa: BLE001
            import numpy as np

            def _auc(y, s):
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

    def _write_ablation(self, path, rows, best, counts, leg, law, opts, k):
        path.parent.mkdir(parents=True, exist_ok=True)
        n_pos, n_neg, n_val, n_rel = counts
        lines = [
            "# Dual-metric hybrid-weight ablation (feature 020)",
            "",
            f"Labeled pairs: {n_pos + n_neg} (match {n_pos} / no_match {n_neg}, role-relevant {n_rel}) · "
            f"validation {n_val} · grid {opts['grid']} · seed {opts['seed']} · objective {opts['objective']} · k={k}.",
            "",
            f"| rank | α | β | γ | δ | label-AUC | role-NDCG@{k} | role-P@{k} | note |",
            "|---|---|---|---|---|-----------|------|------|------|",
        ]
        for i, (a, b, g, d, auc, nd, pr) in enumerate(rows[:18], 1):
            note = "**← chosen**" if (a, b, g, d) == tuple(best[:4]) else ""
            lines.append(f"| {i} | {a:.2f} | {b:.2f} | {g:.2f} | {d:.2f} | {auc:.4f} | {nd:.4f} | {pr:.4f} | {note} |")
        lines += [
            "",
            f"**Chosen** (max {opts['objective']}): α={best[0]:.2f} β={best[1]:.2f} γ={best[2]:.2f} δ={best[3]:.2f} "
            f"· role-NDCG@{k}={best[5]:.4f} · role-P@{k}={best[6]:.4f} · label-AUC={best[4]:.4f}",
            f"**Label-AUC winner** (feature 019: 0.20/0.75/0.05/0): "
            f"label-AUC={law[0]:.4f} · role-NDCG@{k}={law[1]:.4f} · role-P@{k}={law[2]:.4f}",
            f"**Legacy** (0.55/0.30/0.15/0): "
            f"label-AUC={leg[0]:.4f} · role-NDCG@{k}={leg[1]:.4f} · role-P@{k}={leg[2]:.4f}",
            "",
            "The two objectives favour different weights: optimizing label-AUC alone gives the "
            "β-heavy δ=0 row (high label-AUC, low role-NDCG → domain-mismatched top results); the "
            "role-aware objective restores α (GNN) + δ (domain) and lifts role-NDCG.",
            "",
            "NOTE — circularity guard: a PURE role-NDCG objective is degenerate (δ=1.0 makes the "
            "score equal the relevance signal → role-NDCG=1.0 but label-AUC collapses to ~0.62, "
            "useless). The chosen row uses the **balanced** objective: max role-NDCG subject to "
            f"label-AUC ≥ {opts['min_auc_frac']}·max and δ ≤ {opts['max_delta']} (domain stays a soft term).",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _persist(best, grid, objective, k):
        meta_path = Path(settings.ML_CHECKPOINT_DIR) / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        meta["hybrid_weights"] = {
            "alpha": round(best[0], 4), "beta": round(best[1], 4),
            "gamma": round(best[2], 4), "delta": round(best[3], 4),
        }
        meta["hybrid_weights_meta"] = {
            "objective": f"{objective}@{k}", "label_auc": round(best[4], 4),
            "role_ndcg": round(best[5], 4), "role_p": round(best[6], 4), "grid_step": grid,
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
