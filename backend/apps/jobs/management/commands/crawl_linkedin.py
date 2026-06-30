"""MASTER LinkedIn crawl.

One command → crawl a curated set of IT roles from LinkedIn into today's file
(data/crawl/linkedin/<YYYY-MM-DD>.json), with a live dashboard. Runs SERIALLY in
the main thread (Playwright launches a browser per role and is unreliable off the
main thread). Requires a logged-in session. No DB write.

Usage:
    python manage.py crawl_linkedin
    python manage.py crawl_linkedin --location "Vietnam" --results 80
    python manage.py crawl_linkedin --roles "react developer,devops engineer"
    python manage.py crawl_linkedin --limit 3        # debug: first 3 roles only

For multiple locations, run once per location — files merge (dedup) into the
same day's linkedin file.
"""

import argparse

from django.core.management.base import BaseCommand

from apps.jobs.services.crawl_runner import LINKEDIN_ROLES, live_crawl


class Command(BaseCommand):
    help = "Master LinkedIn crawl: curated IT roles → today's linkedin file (guest by default, no login)"

    def add_arguments(self, parser):
        parser.add_argument("--results", type=int, default=50, help="Results per role")
        parser.add_argument("--location", type=str, default="", help="Location filter (e.g. 'Vietnam', 'United States')")
        parser.add_argument("--delay", type=float, default=2.0, help="Seconds between roles (LinkedIn rate-limits; default 2.0)")
        parser.add_argument("--roles", type=str, default="", help="Comma list overriding the curated roles")
        parser.add_argument("--limit", type=int, default=0, help="Cap number of roles (debug)")
        parser.add_argument("--out-dir", type=str, default="", help="Output root (default: <BASE_DIR>/data/crawl)")
        parser.add_argument("--auth", action="store_true",
                            help="Use the authenticated Playwright session instead of the login-free guest endpoints "
                                 "(richer fields: salary, applicant count). Requires linkedin_auth.py login first.")
        parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True,
                            help="[--auth only] Run the browser headless (default). Use --no-headless to watch it.")

    def handle(self, *args, **options):
        auth = options["auth"]
        if auth:
            # Authenticated mode needs a saved login session — fail fast if missing.
            from ml_service.crawler.providers.linkedin_auth import load_state_path
            if not load_state_path():
                self.stderr.write(self.style.ERROR(
                    "LinkedIn not logged in (required for --auth). Run:\n"
                    "  .venv/bin/python -m ml_service.crawler.providers.linkedin_auth\n"
                    "Or drop --auth to use the login-free guest crawl."
                ))
                return

        roles = [r.strip() for r in options["roles"].split(",") if r.strip()] or LINKEDIN_ROLES
        if options["limit"]:
            roles = roles[: options["limit"]]

        provider_kwargs = {"auth": True, "headless": options["headless"]} if auth else {"auth": False}
        live_crawl(
            ["linkedin"], roles,
            results_wanted=options["results"], location=options["location"],
            out_dir=options["out_dir"], request_delay=options["delay"],
            serial=True,
            provider_kwargs=provider_kwargs,
            title="🔗 LinkedIn crawl" + ("" if auth else " (guest)"),
            full=True,
        )
