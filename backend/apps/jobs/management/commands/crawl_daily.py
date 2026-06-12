"""MASTER daily crawl.

One command → crawl ALL providers across the full IT / Software / AI keyword set
into today's per-provider files (data/crawl/<provider>/<YYYY-MM-DD>.json), with a
live dashboard. No DB write.

Usage:
    python manage.py crawl_daily
    python manage.py crawl_daily --results 80
    python manage.py crawl_daily --providers jobspy,freelancer,remotive --results 50
    python manage.py crawl_daily --limit 5          # debug: first 5 keywords only
"""

from django.core.management.base import BaseCommand

from apps.jobs.services.crawl_runner import IT_AI_KEYWORDS, default_providers, live_crawl


class Command(BaseCommand):
    help = "Master daily crawl: all providers × full IT/AI keyword set → today's files"

    def add_arguments(self, parser):
        parser.add_argument("--results", type=int, default=40, help="Results per keyword per provider")
        parser.add_argument("--providers", type=str, default="", help="Comma list (default: all API providers; linkedin excluded — run it separately)")
        parser.add_argument("--location", type=str, default="", help="Location filter")
        parser.add_argument("--workers", type=int, default=0, help="Parallel providers (default: number of providers)")
        parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests per provider (default 1.0)")
        parser.add_argument("--out-dir", type=str, default="", help="Output root (default: <BASE_DIR>/data/crawl)")
        parser.add_argument("--limit", type=int, default=0, help="Cap number of keywords (debug)")

    def handle(self, *args, **options):
        providers = [p.strip() for p in options["providers"].split(",") if p.strip()] or default_providers()
        keywords = IT_AI_KEYWORDS[: options["limit"]] if options["limit"] else IT_AI_KEYWORDS

        live_crawl(
            providers, keywords,
            results_wanted=options["results"], location=options["location"],
            out_dir=options["out_dir"], workers=options["workers"], request_delay=options["delay"],
            title="📡 Daily IT / Software / AI crawl",
        )
