"""Ad-hoc crawl → per-provider dated JSON files. No DB write.

Providers run in parallel; each writes <out-dir>/<provider>/<YYYY-MM-DD>.json
(merge-dedup by source_url). For the full daily IT/AI sweep use `crawl_daily`.

Usage:
    python manage.py crawl_jobs --provider jobspy --query "react developer" --results 50
    python manage.py crawl_jobs --all --results 50
    python manage.py crawl_jobs --all --out-dir data/crawl --workers 4
"""

from django.core.management.base import BaseCommand

from apps.jobs.services.crawl_runner import default_providers, live_crawl
from ml_service.crawler import list_providers


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


class Command(BaseCommand):
    help = "Crawl jobs from providers (parallel) into per-provider dated JSON files"

    def add_arguments(self, parser):
        parser.add_argument("--provider", type=str, default="jobspy", help=f"Provider: {', '.join(list_providers())}")
        parser.add_argument("--query", type=str, help="Search query (single). If not set, uses default queries.")
        parser.add_argument("--location", type=str, default="", help="Location filter")
        parser.add_argument("--results", type=int, default=50, help="Results per query")
        parser.add_argument("--all", action="store_true", help="Use all API providers (linkedin excluded; use --provider linkedin)")
        parser.add_argument("--out-dir", type=str, default="", help="Output root (default: <BASE_DIR>/data/crawl)")
        parser.add_argument("--workers", type=int, default=0, help="Parallel providers (default: number of providers)")
        parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests per provider (default 1.0)")

    def handle(self, *args, **options):
        queries = [options["query"]] if options["query"] else DEFAULT_QUERIES
        providers = default_providers() if options["all"] else [options["provider"]]

        live_crawl(
            providers, queries,
            results_wanted=options["results"], location=options["location"],
            out_dir=options["out_dir"], workers=options["workers"], request_delay=options["delay"],
            title="Crawl jobs",
        )
