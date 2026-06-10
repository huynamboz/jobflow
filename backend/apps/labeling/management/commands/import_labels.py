"""Import agent-produced labels from JSONL (feature 022).

Validates every row BEFORE writing anything (atomic). Creates one LabelingBatch
per import (workers=0 marks an agent batch) and HumanLabel rows tagged
note='claude-labeled'. Idempotent within the import: duplicate pair_ids in the
input are skipped after the first.

    python manage.py import_labels --in /tmp/labeling-022/pilot-labels/ [--dry-run]
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

REQUIRED = ("pair_id", "skill_fit", "seniority_fit", "experience_fit", "domain_fit", "overall")


class Command(BaseCommand):
    help = "Validate + import agent labels (JSONL file or directory of .jsonl)."

    def add_arguments(self, parser):
        parser.add_argument("--in", dest="inp", required=True, help="JSONL file or directory.")
        parser.add_argument("--dry-run", action="store_true", help="Validate only.")

    def handle(self, *args, **opts):
        from apps.labeling.models import HumanLabel, LabelingBatch, PairQueue

        path = Path(opts["inp"])
        files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
        if not files:
            raise CommandError(f"No .jsonl files under {path}")

        rows, errors = [], []
        for f in files:
            for ln, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError as e:
                    errors.append(f"{f.name}:{ln} bad JSON: {e}")
                    continue
                missing = [k for k in REQUIRED if k not in r]
                if missing:
                    errors.append(f"{f.name}:{ln} missing {missing}")
                    continue
                bad = [k for k in REQUIRED[1:] if not isinstance(r[k], int) or r[k] not in (0, 1, 2)]
                if bad:
                    errors.append(f"{f.name}:{ln} pair {r.get('pair_id')}: invalid scores {bad}")
                    continue
                rows.append(r)

        # dedup within this import (first wins)
        seen: set[int] = set()
        deduped, skipped_dup = [], 0
        for r in rows:
            if r["pair_id"] in seen:
                skipped_dup += 1
                continue
            seen.add(r["pair_id"])
            deduped.append(r)

        pair_ids = [r["pair_id"] for r in deduped]
        existing = set(PairQueue.objects.filter(id__in=pair_ids).values_list("id", flat=True))
        unknown = [pid for pid in pair_ids if pid not in existing]
        if unknown:
            errors.append(f"{len(unknown)} unknown pair_ids (first 10: {unknown[:10]})")

        if errors:
            for e in errors[:20]:
                self.stdout.write(self.style.ERROR(f"  {e}"))
            raise CommandError(f"{len(errors)} validation errors — nothing imported.")

        self.stdout.write(f"Validated {len(deduped)} labels ({skipped_dup} in-file duplicates skipped).")
        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("--dry-run: nothing written."))
            return

        with transaction.atomic():
            batch = LabelingBatch.objects.create(
                status=LabelingBatch.STATUS_DONE, total=len(deduped),
                done_count=len(deduped), workers=0,  # workers=0 ⇒ agent batch
            )
            labels = [
                # note marks provenance; labeled_by=None + workers=0 batch = Claude agents
                dict(pair_id=r["pair_id"], batch=batch, note="claude-labeled",
                     skill_fit=r["skill_fit"], seniority_fit=r["seniority_fit"],
                     experience_fit=r["experience_fit"], domain_fit=r["domain_fit"],
                     overall=r["overall"])
                for r in deduped
            ]
            from apps.labeling.models import HumanLabel as HL
            HL.objects.bulk_create([HL(**kw) for kw in labels], batch_size=500)
            PairQueue.objects.filter(id__in=pair_ids, status="pending").update(status="labeled")

        self.stdout.write(self.style.SUCCESS(
            f"Imported {len(deduped)} labels into batch {batch.id} "
            f"(pairs marked labeled; already-labeled pairs kept their status)."))
