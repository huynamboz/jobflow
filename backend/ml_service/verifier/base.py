"""Contracts for the job-status verifier.

A verifier is responsible for determining whether a specific job listing on
a remote platform is still accepting applications. The verifier service
depends only on the abstractions defined here; adding a new platform is a
matter of dropping a new ``JobStatusVerifier`` subclass into the
``providers/`` package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class JobStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    SESSION_EXPIRED = "session_expired"
    UNKNOWN = "unknown"
    ERROR = "error"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class VerifyResult:
    status: JobStatus
    reason: str = ""
    final_url: str | None = None
    verified_at: datetime = field(default_factory=_utcnow)


class JobStatusVerifier(ABC):
    """Per-platform verifier. See contracts/verifier_interface.md for the full
    contract.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier — used by the registry and the management
        command's ``--platform`` flag.
        """

    @abstractmethod
    def supports(self, url: str) -> bool:
        """Return True iff this verifier handles ``url``.

        MUST be pure (no I/O), MUST NOT raise — return False on malformed
        input.
        """

    @abstractmethod
    def verify(self, url: str) -> VerifyResult:
        """Check a single URL. Subclasses MAY simply delegate to
        ``verify_batch([url])[0]``.
        """

    def verify_batch(self, urls: list[str]) -> list[VerifyResult]:
        """Default batch impl loops over ``verify``. Subclasses SHOULD
        override when reusing a resource (browser context, HTTP session)
        yields material savings.
        """
        return [self.verify(u) for u in urls]
