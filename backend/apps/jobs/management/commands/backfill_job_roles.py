"""Backfill Job.role_category for role-less jobs via Claude-agent classification (Đợt 3.1 / A8).

34% of active jobs have role_category empty/"other", blinding the domain term +
domain gate. Export them as JSONL work chunks for agent classification, then
import the results.

    python manage.py backfill_job_roles --export --out /tmp/roles-023
    # ... agents classify each chunk ...
    python manage.py backfill_job_roles --import-dir /tmp/roles-023-labels [--dry-run]
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

VALID_ROLES = {"backend", "frontend", "fullstack", "mobile", "devops",
               "data_ml", "data_eng", "qa", "design", "ba", "other"}


class Command(BaseCommand):
    help = "Export role-less active jobs for agent classification / import results."

    def add_arguments(self, parser):
        parser.add_argument("--export", action="store_true")
        parser.add_argument("--out", default="/tmp/roles-023")
        parser.add_argument("--chunk-size", type=int, default=40)
        parser.add_argument("--import-dir", default="")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        if opts["export"]:
            self._export(Path(opts["out"]), opts["chunk_size"])
        elif opts["import_dir"]:
            self._import(Path(opts["import_dir"]), opts["dry_run"])
        else:
            raise CommandError("Pass --export or --import-dir.")

    def _export(self, out_dir: Path, size: int):
        from django.db.models import Q
        from apps.jobs.models import Job

        out_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        qs = (Job.objects.filter(is_active=True)
              .filter(Q(role_category="") | Q(role_category="other"))
              .prefetch_related("job_skills__skill"))
        for job in qs:
            skills = [js.skill.canonical_name for js in job.job_skills.all() if js.skill_id]
            rows.append({
                "job_id": job.id,
                "title": job.title,
                "skills": skills,
                "text": (job.description or "")[:900],
            })
        chunks = [rows[i:i + size] for i in range(0, len(rows), size)]
        for idx, chunk in enumerate(chunks):
            (out_dir / f"chunk_{idx:03d}.jsonl").write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in chunk) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            f"Exported {len(rows)} role-less jobs → {len(chunks)} chunks in {out_dir}"))

    def _import(self, in_dir: Path, dry: bool):
        from apps.jobs.models import Job

        files = sorted(in_dir.glob("*.jsonl")) if in_dir.is_dir() else [in_dir]
        updates, errors = {}, []
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
                role = str(r.get("role", "")).lower().strip()
                if role not in VALID_ROLES:
                    errors.append(f"{f.name}:{ln} job {r.get('job_id')}: invalid role '{role}'")
                    continue
                updates[int(r["job_id"])] = role
        if errors:
            for e in errors[:15]:
                self.stdout.write(self.style.ERROR(f"  {e}"))
            raise CommandError(f"{len(errors)} validation errors — nothing written.")

        known = set(Job.objects.filter(id__in=updates).values_list("id", flat=True))
        unknown = set(updates) - known
        if unknown:
            raise CommandError(f"{len(unknown)} unknown job_ids (first: {sorted(unknown)[:5]})")

        dist: dict[str, int] = {}
        for role in updates.values():
            dist[role] = dist.get(role, 0) + 1
        self.stdout.write(f"Validated {len(updates)} role assignments: "
                          + ", ".join(f"{k}={v}" for k, v in sorted(dist.items(), key=lambda x: -x[1])))
        if dry:
            self.stdout.write(self.style.WARNING("--dry-run: nothing written."))
            return
        n = 0
        for job_id, role in updates.items():
            n += Job.objects.filter(id=job_id).update(role_category=role)
        self.stdout.write(self.style.SUCCESS(
            f"Updated {n} jobs. Run rebuild_job_pool to refresh the engine pool."))