# Contract: `JobStatusVerifier` Interface

**Scope**: The pluggable contract every per-platform verifier implements. The verifier service depends only on this contract.

**Location**: `backend/ml_service/verifier/base.py`

---

## `JobStatus` (enum)

```python
class JobStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    SESSION_EXPIRED = "session_expired"
    UNKNOWN = "unknown"
    ERROR = "error"
```

Outcomes mean:
- `ACTIVE` — verifier confirmed the listing is still accepting applications.
- `EXPIRED` — verifier confirmed the listing has been closed/removed/filled.
- `SESSION_EXPIRED` — verifier's authenticated session for the source has lapsed; operator must re-authenticate.
- `UNKNOWN` — page rendered but no expired/active markers matched; retry later.
- `ERROR` — network, parser, or runtime failure; retry on backoff.

---

## `VerifyResult` (dataclass)

```python
@dataclass(frozen=True)
class VerifyResult:
    status: JobStatus
    reason: str = ""
    final_url: str | None = None
    verified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

Invariants:
- `verified_at` is always tz-aware UTC.
- `reason` is human-readable; not parsed by the service.
- `final_url` is the URL after redirects when known; `None` if the verifier didn't reach a page (e.g., DNS error).

---

## `JobStatusVerifier` (ABC)

```python
class JobStatusVerifier(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier used by the registry and the management command's --platform flag."""

    @abstractmethod
    def supports(self, url: str) -> bool:
        """True if this verifier handles the URL's domain/pattern.
        MUST be pure (no I/O); the registry calls it on every dispatch."""

    @abstractmethod
    def verify(self, url: str) -> VerifyResult:
        """Check a single URL.
        Default implementation in subclasses MAY simply delegate to verify_batch([url])."""

    def verify_batch(self, urls: list[str]) -> list[VerifyResult]:
        """Check a batch of URLs.
        Default loops over verify(); subclasses SHOULD override when reusing a resource
        (e.g., a browser context, an HTTP session) yields material savings."""
        return [self.verify(u) for u in urls]
```

### Contract obligations on implementers

1. `name` MUST be stable for the lifetime of the class — used as a primary key by the registry.
2. `supports(url)` MUST NOT raise; on a malformed URL it returns `False`.
3. `verify(url)` and `verify_batch(urls)` MUST return one `VerifyResult` per input URL (in order, for the batch form). They MUST NOT raise on per-URL failures — wrap into `VerifyResult(status=ERROR, reason=str(exc))` instead.
4. Implementers MUST be safe to construct without side effects (no network, no DB) so the registry can instantiate them at import time.
5. Implementers MUST be re-entrant across batches — long-lived resources (browser, session) are created/closed *inside* `verify_batch`, not in `__init__`.

### Contract obligations on the caller (`StatusCheckService`)

1. Calls `supports(url)` before dispatching; never passes an unsupported URL to a verifier.
2. Does not retry a `VerifyResult` within the same batch.
3. Records per-URL outcome regardless of order; does not infer global state from any single outcome (e.g., one `SESSION_EXPIRED` does not invalidate the rest of the batch — the service handles that.).

---

## Verifier registry — auto-discovery contract

`backend/ml_service/verifier/factory.py` exposes:

```python
def get_verifier(name: str) -> JobStatusVerifier: ...
def get_verifier_for_url(url: str) -> JobStatusVerifier | None: ...
def list_verifiers() -> dict[str, JobStatusVerifier]: ...
```

Discovery rules:
- The factory scans `backend/ml_service/verifier/providers/` at first call.
- Any non-abstract subclass of `JobStatusVerifier` in that package is registered under its `.name` property.
- A module that raises on import is logged at WARNING and skipped; it must not crash the registry.
- Re-registration with the same `name` raises `ValueError`. (Helps catch typos when two providers accidentally pick the same name.)

`get_verifier_for_url(url)` iterates registered verifiers in registration order, returns the first whose `supports(url)` is `True`, or `None`.

---

## Adding a new verifier (proof of DI)

1. Create `backend/ml_service/verifier/providers/<name>_verifier.py`.
2. Subclass `JobStatusVerifier`; implement `name`, `supports`, `verify` (and optionally `verify_batch`).
3. Done. No other file in `verifier/`, no service, no command, no schema, no test infrastructure needs editing.

A stub used in tests:

```python
class FakeVerifier(JobStatusVerifier):
    name = "fake"
    def __init__(self, scripted: dict[str, VerifyResult]): self._scripted = scripted
    def supports(self, url): return url.startswith("https://fake.example/")
    def verify(self, url): return self._scripted.get(url, VerifyResult(JobStatus.UNKNOWN))
```
