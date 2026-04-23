"""Management command: add_hard_neg_pairs

Reads a JSONL file of hard-negative candidates (output of mine_hard_negatives.py)
and inserts them into PairQueue for LLM labeling.

Safety guarantees:
  - Never touches HumanLabel, LabelingBatch, or any LABELED PairQueue rows
  - Skips pairs that already exist in PairQueue (unique_together constraint)
  - LabelingCV / LabelingJob must already exist — no upsert of labeling metadata
  - Only clears PENDING pairs when --clear-pending is explicitly passed

Usage:
    python manage.py add_hard_neg_pairs
    python manage.py add_hard_neg_pairs --input data/hard_neg_candidates.jsonl
    python manage.py add_hard_neg_pairs --dry-run
    python manage.py add_hard_neg_pairs --clear-pending   # delete existing PENDING first
"""

import json
import random
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Insert hard-negative candidates into PairQueue for LLM labeling"

    def add_arguments(self, parser):
        parser.add_argument(
            "--input", default="data/hard_neg_candidates.jsonl",
            help="JSONL file produced by mine_hard_negatives.py",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Print what would be inserted without writing to DB",
        )
        parser.add_argument(
            "--clear-pending", action="store_true",
            help="Delete existing PENDING PairQueue rows before inserting (does NOT touch LABELED rows)",
        )
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **options):
        from apps.labeling.models import (
            LabelingCV, LabelingJob, PairQueue,
            PairStatus, SelectionReason, REASON_PRIORITY,
        )

        random.seed(options["seed"])

        inp = Path(options["input"])
        if not inp.exists():
            self.stderr.write(f"Input file not found: {inp}")
            self.stderr.write("Run mine_hard_negatives.py first.")
            return

        # --- Optionally clear PENDING rows (never touches LABELED) ---
        if options["clear_pending"]:
            count, _ = PairQueue.objects.filter(status=PairStatus.PENDING).delete()
            self.stdout.write(f"Cleared {count} PENDING PairQueue rows")

        # --- Load candidates ---
        candidates = []
        with open(inp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    candidates.append(json.loads(line))

        self.stdout.write(f"Loaded {len(candidates)} candidates from {inp}")

        # --- Build lookup maps (cv_id → LabelingCV, job_id → LabelingJob) ---
        cv_ids = {c["cv_id"] for c in candidates}
        job_ids = {c["job_id"] for c in candidates}

        cv_map = {obj.cv_id: obj for obj in LabelingCV.objects.filter(cv_id__in=cv_ids)}
        job_map = {obj.job_id: obj for obj in LabelingJob.objects.filter(job_id__in=job_ids)}

        self.stdout.write(f"Found {len(cv_map)}/{len(cv_ids)} CVs in LabelingCV")
        self.stdout.write(f"Found {len(job_map)}/{len(job_ids)} Jobs in LabelingJob")

        missing_cv = cv_ids - set(cv_map)
        missing_job = job_ids - set(job_map)
        if missing_cv:
            self.stderr.write(f"Warning: {len(missing_cv)} CV IDs not in LabelingCV (will skip)")
        if missing_job:
            self.stderr.write(f"Warning: {len(missing_job)} Job IDs not in LabelingJob (will skip)")

        # --- Filter against existing pairs ---
        existing = set(PairQueue.objects.values_list("cv__cv_id", "job__job_id"))
        self.stdout.write(f"Existing PairQueue entries: {len(existing)}")

        to_create = []
        skipped_missing = 0
        skipped_existing = 0

        for c in candidates:
            cv_id, job_id = c["cv_id"], c["job_id"]

            if cv_id not in cv_map or job_id not in job_map:
                skipped_missing += 1
                continue
            if (cv_id, job_id) in existing:
                skipped_existing += 1
                continue

            r = random.random()
            split = "train" if r < 0.70 else ("val" if r < 0.85 else "test")

            to_create.append(PairQueue(
                cv=cv_map[cv_id],
                job=job_map[job_id],
                skill_overlap_score=c.get("skill_overlap", 0.0),
                bm25_score=c.get("stage1_score", 0.0),
                selection_reason=SelectionReason.HARD_NEGATIVE,
                priority=REASON_PRIORITY[SelectionReason.HARD_NEGATIVE],
                split=split,
            ))

        self.stdout.write(
            f"To insert: {len(to_create)}  "
            f"(skipped missing={skipped_missing}, already_exists={skipped_existing})"
        )

        if options["dry_run"]:
            self.stdout.write("(dry-run — nothing written)")
            return

        PairQueue.objects.bulk_create(to_create, ignore_conflicts=True)

        total = PairQueue.objects.count()
        pending = PairQueue.objects.filter(status=PairStatus.PENDING).count()
        self.stdout.write(self.style.SUCCESS(
            f"Done! Inserted {len(to_create)} hard-negative pairs. "
            f"PairQueue: {total} total, {pending} pending"
        ))
