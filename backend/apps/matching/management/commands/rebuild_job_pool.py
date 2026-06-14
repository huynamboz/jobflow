"""Rebuild the matcher's job pool from the live Job catalog (feature 018 + 027).

Builds JobData from `Job` + `JobSkill`, inductively encodes the job nodes into
the GNN engine (no retraining). The pgvector store (feature 027) is the pool's
source of truth; an on-disk snapshot is also written as a fallback.

By default the rebuild is INCREMENTAL when the pgvector store is populated: only
new/changed jobs are encoded + upserted (content-hash diff), removed jobs are
evicted. Use --full to re-encode everything (also refreshes the snapshot).

    python manage.py rebuild_job_pool              # incremental upsert into pgvector
    python manage.py rebuild_job_pool --full       # full re-encode + snapshot + upsert
    python manage.py rebuild_job_pool --limit 50 --dry-run   # smoke test, no writes
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Rebuild the engine job pool from the live Job catalog (inductive, no retrain)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="Build only the first N jobs (smoke test).")
        parser.add_argument("--dry-run", action="store_true", help="Build + diff, report counts, write nothing.")
        parser.add_argument("--no-save", action="store_true", help="Rebuild the in-process pool only; do not save the snapshot.")
        parser.add_argument("--full", action="store_true", help="Force a full re-encode (default: incremental when the store is populated).")

    def handle(self, *args, **opts):
        from apps.matching.services.matching_service import _get_engine, build_jobdata_from_db
        from ml_service.inference import job_pool_snapshot, pgvector_store, pool_diff

        self.stdout.write("Building JobData from the live catalog…")
        jobs = build_jobdata_from_db(limit=opts["limit"])
        if not jobs:
            raise CommandError("No jobs with skills found — nothing to build.")
        self.stdout.write(f"  {len(jobs)} jobs with skills")

        engine = _get_engine()
        fp = engine.model_signature
        store_ready = pgvector_store.available()
        can_incremental = (store_ready and not opts["full"] and not opts["limit"]
                           and pgvector_store.count(fp) > 0)

        # ---- Incremental path (feature 027 Stage C): encode only new/changed ----
        if can_incremental:
            stored = pgvector_store.stored_hashes(fp)
            to_encode, to_evict, cur_hashes = pool_diff.diff(jobs, stored)
            self.stdout.write(
                f"Incremental: {len(to_encode)} new/changed, "
                f"{len(jobs) - len(to_encode)} unchanged, {len(to_evict)} to evict")
            if opts["dry_run"]:
                self.stdout.write("DRY RUN — nothing written.")
                return
            if to_encode:
                emb, txt = engine.encode_jobs(to_encode)
                ennp = emb.detach().cpu().numpy()
                rows = ((j.job_id, ennp[i], txt[i], j.role_category, fp, cur_hashes[j.job_id])
                        for i, j in enumerate(to_encode))
                n = pgvector_store.upsert_jobs(rows)
            else:
                n = 0
            evicted = pgvector_store.delete_not_in([j.job_id for j in jobs], fp)
            self.stdout.write(self.style.SUCCESS(
                f"pgvector store: upserted {n} (reused {len(jobs) - len(to_encode)}), evicted {evicted}"))
            self.stdout.write("Tip: --full to also refresh the snapshot fallback.")
            return

        # ---- Full path: re-encode everything (+ snapshot fallback) ----
        report = engine.rebuild_job_pool(jobs)
        self.stdout.write(self.style.SUCCESS(
            f"Encoded pool: {report.num_jobs} jobs, "
            f"{report.skill_skipped_edges} skill-skipped edges, {report.encode_seconds}s"))

        if opts["dry_run"] or opts["no_save"]:
            self.stdout.write("Snapshot NOT saved (%s)." % ("--dry-run" if opts["dry_run"] else "--no-save"))
            return

        path = engine.snapshot_job_pool(
            job_pool_snapshot.DEFAULT_DIR, skill_skipped_edges=report.skill_skipped_edges)
        self.stdout.write(self.style.SUCCESS(f"Snapshot saved → {path}"))

        if store_ready:
            emb = engine._job_embeddings.detach().cpu().numpy()
            txt = engine._job_text_vecs
            rows = ((j.job_id, emb[i], txt[i], j.role_category, fp, pool_diff.content_hash(j))
                    for i, j in enumerate(engine._jobs))
            n = pgvector_store.upsert_jobs(rows)
            evicted = pgvector_store.delete_not_in([j.job_id for j in engine._jobs], fp)
            self.stdout.write(self.style.SUCCESS(
                f"pgvector store: upserted {n} jobs, evicted {evicted} stale"))
