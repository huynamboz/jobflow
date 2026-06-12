"""Crawl jobs from providers and dump to per-provider dated JSON files.

Each provider runs in its OWN thread (providers crawl in parallel), and each
provider writes to its own folder:

    <out-dir>/<provider>/<YYYY-MM-DD>.json   (a JSON array of RawJob dicts)

Re-running on the same day MERGES into that day's file (dedup by source_url),
so multiple crawls accumulate instead of overwriting. No DB write — this command
only produces the raw crawl files.

Usage:
    python manage.py crawl_jobs --provider jobspy --query "react developer" --results 50
    python manage.py crawl_jobs --all --results 50
    python manage.py crawl_jobs --all --out-dir data/crawl --workers 4
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from ml_service.crawler import get_provider, list_providers
from ml_service.crawler.storage import _raw_job_to_dict


DEFAULT_QUERIES = [
    "software engineer",
    "python developer",
    "frontend developer",
    "backend developer",
    "fullstack developer",
    "react developer",
    "data engineer",
    "devops engineer",
]

_print_lock = threading.Lock()


class Command(BaseCommand):
    help = "Crawl jobs from providers (parallel) and dump per-provider dated JSON files"

    def add_arguments(self, parser):
        parser.add_argument("--provider", type=str, default="jobspy", help=f"Provider: {', '.join(list_providers())}")
        parser.add_argument("--query", type=str, help="Search query (single). If not set, uses default queries.")
        parser.add_argument("--location", type=str, default="", help="Location filter")
        parser.add_argument("--results", type=int, default=50, help="Results per query")
        parser.add_argument("--all", action="store_true", help="Use all available providers")
        parser.add_argument("--out-dir", type=str, default="", help="Output root (default: <BASE_DIR>/data/crawl)")
        parser.add_argument("--workers", type=int, default=0, help="Parallel providers (default: number of providers)")

    def handle(self, *args, **options):
        query = options["query"]
        location = options["location"]
        results_wanted = options["results"]
        use_all = options["all"]

        queries = [query] if query else DEFAULT_QUERIES
        providers = list_providers() if use_all else [options["provider"]]

        out_root = Path(options["out_dir"]) if options["out_dir"] else Path(settings.BASE_DIR) / "data" / "crawl"
        date_str = datetime.now().strftime("%Y-%m-%d")
        workers = options["workers"] or max(1, len(providers))

        self.stdout.write(f"Providers: {providers} (parallel, {workers} workers)")
        self.stdout.write(f"Queries: {queries}")
        self.stdout.write(f"Results/query: {results_wanted}  ·  Out: {out_root}/<provider>/{date_str}.json")

        def crawl_one(pname: str) -> dict:
            """Crawl all queries for one provider and write its dated file."""
            try:
                p = get_provider(pname)
                jobs = []
                for q in queries:
                    try:
                        jobs.extend(p.fetch(q, location=location, results_wanted=results_wanted))
                    except Exception as e:  # noqa: BLE001 — one query failing shouldn't kill the provider
                        with _print_lock:
                            self.stdout.write(self.style.WARNING(f"  {pname} → {q!r}: FAILED ({e})"))
                added, total = self._merge_write(out_root / pname / f"{date_str}.json", jobs)
                return {"provider": pname, "crawled": len(jobs), "added": added, "total": total}
            except Exception as e:  # noqa: BLE001 — provider init/fetch crash
                return {"provider": pname, "error": str(e)}

        grand_added = 0
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="crawl") as pool:
            futures = {pool.submit(crawl_one, pname): pname for pname in providers}
            for fut in as_completed(futures):
                r = fut.result()
                with _print_lock:
                    if r.get("error"):
                        self.stdout.write(self.style.ERROR(f"  {r['provider']}: provider failed ({r['error']})"))
                    else:
                        grand_added += r["added"]
                        self.stdout.write(
                            f"  {r['provider']}: crawled {r['crawled']} → +{r['added']} new "
                            f"({r['total']} in {date_str}.json)"
                        )

        self.stdout.write(self.style.SUCCESS(f"\nDone. {grand_added} new jobs written across {len(providers)} provider file(s)."))

    @staticmethod
    def _merge_write(path: Path, jobs: list) -> tuple[int, int]:
        """Merge RawJobs into the day's JSON array (dedup by source_url). Returns
        (added, total)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: list[dict] = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                existing = []
        seen = {o.get("source_url") for o in existing if o.get("source_url")}
        added = 0
        for job in jobs:
            d = _raw_job_to_dict(job)
            url = d.get("source_url")
            if url and url in seen:
                continue
            if url:
                seen.add(url)
            existing.append(d)
            added += 1
        path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        return added, len(existing)
