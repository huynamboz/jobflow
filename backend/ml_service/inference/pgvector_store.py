"""Raw-SQL access to the `job_pool_vec` pgvector table (feature 027).

pgvector is the pool STORE / source of truth: rebuild_job_pool upserts encoded
embeddings here (incrementally), and serving loads the pool from here at startup
+ hot-reloads on change. No ORM model / pgvector-python dependency — vectors are
passed as the text literal ('[a,b,c]'). (A per-request ANN retriever was removed
— see retrieval/__init__.py — so there is no ANN query here, only KV access.)
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _vec_literal(v) -> str:
    return "[" + ",".join(f"{float(x):.7g}" for x in v) + "]"


def available() -> bool:
    """True if the table + vector extension are present (Stage B provisioned)."""
    from django.db import connection
    try:
        with connection.cursor() as c:
            c.execute("SELECT to_regclass('public.job_pool_vec')")
            return c.fetchone()[0] is not None
    except Exception as exc:  # noqa: BLE001
        logger.warning("pgvector_store.available check failed: %s", exc)
        return False


_UPSERT_TAIL = (
    " ON CONFLICT (job_id) DO UPDATE SET "
    "gnn_emb=EXCLUDED.gnn_emb, text_vec=EXCLUDED.text_vec, "
    "role_category=EXCLUDED.role_category, model_fingerprint=EXCLUDED.model_fingerprint, "
    "content_hash=EXCLUDED.content_hash, updated_at=now()"
)


def _flush(cursor, batch: list) -> None:
    """One multi-row INSERT … ON CONFLICT (far faster than executemany)."""
    values = ",".join(["(%s,%s,%s,%s,%s,%s,now())"] * len(batch))
    flat = [v for row in batch for v in row]
    cursor.execute(
        "INSERT INTO job_pool_vec "
        "(job_id, gnn_emb, text_vec, role_category, model_fingerprint, content_hash, updated_at) "
        f"VALUES {values}{_UPSERT_TAIL}",
        flat,
    )


def upsert_jobs(rows, *, batch: int = 500) -> int:
    """Upsert rows = iterable of (job_id, gnn_emb, text_vec, role_category,
    model_fingerprint, content_hash). Returns count written."""
    from django.db import connection
    buf, n = [], 0
    with connection.cursor() as c:
        for job_id, gnn, txt, role, fp, chash in rows:
            buf.append((int(job_id), _vec_literal(gnn),
                        _vec_literal(txt) if txt is not None else None,
                        role or "", fp, chash or ""))
            if len(buf) >= batch:
                _flush(c, buf); n += len(buf); buf = []
        if buf:
            _flush(c, buf); n += len(buf)
    return n


def pool_version(model_fingerprint: str) -> str:
    """A cheap version token for the current model's store rows: (count, latest
    updated_at). Serving polls this to hot-reload when an incremental rebuild
    upserts deltas — the pgvector analogue of the snapshot mtime."""
    from django.db import connection
    with connection.cursor() as c:
        c.execute(
            "SELECT count(*), COALESCE(max(updated_at), 'epoch'::timestamptz) "
            "FROM job_pool_vec WHERE model_fingerprint=%s",
            [model_fingerprint],
        )
        cnt, mx = c.fetchone()
        return f"{cnt}:{mx.isoformat() if mx else '0'}"


def delete_not_in(keep_job_ids, model_fingerprint: str) -> int:
    """Evict rows for the current model whose job_id is not in keep_job_ids
    (jobs that left the pool: deactivated / dropped below 2 skills / removed)."""
    from django.db import connection
    keep = list(keep_job_ids)
    with connection.cursor() as c:
        # also drop any rows from a stale model fingerprint
        c.execute("DELETE FROM job_pool_vec WHERE model_fingerprint <> %s", [model_fingerprint])
        deleted = c.rowcount or 0
        if keep:
            c.execute("DELETE FROM job_pool_vec WHERE job_id <> ALL(%s)", [keep])
        else:
            c.execute("DELETE FROM job_pool_vec")
        return deleted + (c.rowcount or 0)


def stored_hashes(model_fingerprint: str) -> dict[int, str]:
    """{job_id: content_hash} for the current model — drives the Stage C diff."""
    from django.db import connection
    with connection.cursor() as c:
        c.execute("SELECT job_id, content_hash FROM job_pool_vec WHERE model_fingerprint=%s",
                  [model_fingerprint])
        return {int(jid): h for jid, h in c.fetchall()}


def fetch_pool(model_fingerprint: str) -> dict[int, tuple[list, list | None]]:
    """{job_id: (gnn_emb, text_vec)} for the current model — the serving store
    load path (feature 027 'chuẩn prod': pool comes from pgvector, not a file)."""
    import json
    from django.db import connection
    out: dict[int, tuple[list, list | None]] = {}
    with connection.cursor() as c:
        c.execute(
            "SELECT job_id, gnn_emb::text, text_vec::text FROM job_pool_vec WHERE model_fingerprint=%s",
            [model_fingerprint],
        )
        for jid, g, t in c.fetchall():
            out[int(jid)] = (json.loads(g), json.loads(t) if t else None)
    return out


def count(model_fingerprint: str | None = None) -> int:
    from django.db import connection
    with connection.cursor() as c:
        if model_fingerprint:
            c.execute("SELECT count(*) FROM job_pool_vec WHERE model_fingerprint=%s", [model_fingerprint])
        else:
            c.execute("SELECT count(*) FROM job_pool_vec")
        return int(c.fetchone()[0])
