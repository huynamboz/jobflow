"""Export pairs to JSONL work chunks for agent labeling (feature 022).

    python manage.py export_pending_pairs --out /tmp/labeling-022/full
    python manage.py export_pending_pairs --out DIR --pilot 180        # stratified sample
    python manage.py export_pending_pairs --out DIR --pair-ids ids.txt # bypass status (re-label)
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Dump pairs to chunked JSONL for Claude-agent labeling."

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True, help="Output directory.")
        parser.add_argument("--reasons", default="", help="Comma-separated bucket filter.")
        parser.add_argument("--pilot", type=int, default=0,
                            help="Stratified sample of N pairs across buckets (min 15/bucket).")
        parser.add_argument("--pair-ids", default="",
                            help="File with one pair_id per line — exports these regardless of status.")
        parser.add_argument("--chunk-size", type=int, default=22)
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **opts):
        from apps.labeling.models import PairQueue

        random.seed(opts["seed"])
        out_dir = Path(opts["out"])
        out_dir.mkdir(parents=True, exist_ok=True)

        if opts["pair_ids"]:
            ids = [int(x) for x in Path(opts["pair_ids"]).read_text().split()]
            qs = PairQueue.objects.filter(id__in=ids)
        else:
            qs = PairQueue.objects.filter(status="pending")
            if opts["reasons"]:
                qs = qs.filter(selection_reason__in=opts["reasons"].split(","))

        pairs = list(qs.select_related("cv", "job"))
        if not pairs:
            raise CommandError("No pairs matched.")

        if opts["pilot"]:
            by_bucket: dict[str, list] = {}
            for p in pairs:
                by_bucket.setdefault(p.selection_reason, []).append(p)
            n_buckets = len(by_bucket)
            base = max(15, opts["pilot"] // max(n_buckets, 1))
            sample = []
            for bucket, items in by_bucket.items():
                random.shuffle(items)
                sample.extend(items[:base])
            random.shuffle(sample)
            pairs = sample[:opts["pilot"]] if len(sample) > opts["pilot"] else sample

        if opts["limit"]:
            random.shuffle(pairs)
            pairs = pairs[:opts["limit"]]

        rows = [self._row(p) for p in pairs]
        size = opts["chunk_size"]
        chunks = [rows[i:i + size] for i in range(0, len(rows), size)]
        for idx, chunk in enumerate(chunks):
            path = out_dir / f"chunk_{idx:03d}.jsonl"
            path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in chunk) + "\n",
                            encoding="utf-8")

        buckets_count: dict[str, int] = {}
        for p in pairs:
            buckets_count[p.selection_reason] = buckets_count.get(p.selection_reason, 0) + 1
        manifest = {"num_pairs": len(rows), "num_chunks": len(chunks),
                    "chunk_size": size, "buckets": buckets_count}
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            f"Exported {len(rows)} pairs → {len(chunks)} chunks in {out_dir}"))
        for b, c in sorted(buckets_count.items()):
            self.stdout.write(f"  {b}: {c}")

    @staticmethod
    def _row(p) -> dict:
        cv, job = p.cv, p.job
        return {
            "pair_id": p.id,
            "bucket": p.selection_reason,
            "cv": {
                "role": cv.role_category, "seniority": cv.seniority,
                "experience_years": cv.experience_years,
                "skills": cv.skills,            # [{name, proficiency}]
                "text": (cv.text_summary or "")[:1200],
            },
            "job": {
                "title": job.title, "role": job.role_category,
                "seniority": job.seniority, "experience_min": job.experience_min,
                "skills": job.skills,           # [{name, importance}]
                "text": (job.text_summary or "")[:1200],
            },
        }
