"""Platform + Company management."""

from __future__ import annotations

import logging
import re

from apps.jobs.models import Company, CompanyPlatform, Platform

logger = logging.getLogger(__name__)


class PlatformService:
    """Create/get platforms and companies."""

    @staticmethod
    def get_or_create_platform(name: str, base_url: str = "", logo_url: str = "") -> Platform:
        """Get or create a platform by name. Backfills logo_url on existing rows
        that don't have one yet."""
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        platform, created = Platform.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "base_url": base_url, "logo_url": logo_url},
        )
        if created:
            logger.info("Created platform: %s", name)
        elif logo_url and not platform.logo_url:
            platform.logo_url = logo_url
            platform.save(update_fields=["logo_url"])
        return platform

    @staticmethod
    def get_or_create_company(
        name: str,
        platform: Platform,
        *,
        logo_url: str = "",
        website_url: str = "",
        profile_url: str = "",
        industry: str = "",
        size: str = "",
        location: str = "",
    ) -> Company:
        """Get or create a company, link to platform."""
        if not name or name.lower() in ("unknown", "n/a", ""):
            name = "Unknown"

        # Normalize company name for lookup
        normalized = re.sub(r"\s+", " ", name.strip())

        company, created = Company.objects.get_or_create(
            name__iexact=normalized,
            defaults={
                "name": normalized,
                "logo_url": logo_url,
                "website_url": website_url,
                "industry": industry,
                "size": size,
                "location": location,
            },
        )

        # Update fields if provided and empty
        updated = False
        if logo_url and not company.logo_url:
            company.logo_url = logo_url
            updated = True
        if industry and not company.industry:
            company.industry = industry
            updated = True
        if updated:
            company.save()

        # Link to platform
        CompanyPlatform.objects.get_or_create(
            company=company,
            platform=platform,
            defaults={"profile_url": profile_url},
        )

        return company
