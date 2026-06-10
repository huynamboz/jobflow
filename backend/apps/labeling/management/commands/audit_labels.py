"""Per-bucket label-distribution audit (feature 022 pilot gate + final report).

    python manage.py audit_labels --batch 11
    python manage.py audit_labels            # all claude-labeled labels
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

EXPECTED = {  # research R2 audit contracts
    "cross_domain_hard_neg":  "≥95% overall=0",
    "related_skill_positive": "đa số overall ≥1",
    "seniority_hard_neg":     "0 nếu job>CV 2+ bậc; ≤1 nếu CV>job; không có 2",
    "missing_must_have":      "trộn 0/1",
    "boundary_medium":        "trộn",
    "high_overlap":           "đa số ≥1",
    "random":                 "≈100% overall=0",
}


class Command(BaseCommand):
    help = "Label distribution per bucket vs expectations (pilot gate)."

    def add_arguments(self, parser):
        parser.add_argument("--batch", type=int, default=0, help="Limit to one LabelingBatch id.")
        parser.add_argument("--all", action="store_true",
                            help="Include legacy (non-claude) labels too.")

    def handle(self, *args, **opts):
        from apps.labeling.models import HumanLabel

        qs = HumanLabel.objects.select_related("pair")
        if opts["batch"]:
            qs = qs.filter(batch_id=opts["batch"])
        elif not opts["all"]:
            qs = qs.filter(note="claude-labeled")

        dist: dict[str, list[int]] = {}
        for hl in qs:
            bucket = hl.pair.selection_reason
            dist.setdefault(bucket, [0, 0, 0])[hl.overall] += 1

        if not dist:
            self.stdout.write(self.style.WARNING("No labels matched."))
            return

        self.stdout.write(f"{'bucket':26} {'n':>5} {'%0':>6} {'%1':>6} {'%2':>6}  expected")
        for bucket in sorted(dist):
            c = dist[bucket]
            n = sum(c)
            pct = [100 * x / n for x in c]
            self.stdout.write(
                f"{bucket:26} {n:>5} {pct[0]:>5.1f}% {pct[1]:>5.1f}% {pct[2]:>5.1f}%  "
                f"{EXPECTED.get(bucket, '-')}"
            )
