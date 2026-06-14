"""Feature 027: the per-request pgvector ANN retriever was removed (the
in-memory `vector` retriever is faster). pgvector stays as the pool STORE, which
only does key access (by job_id PK / by model_fingerprint) — so the HNSW ANN
index and the role_category index are dead weight (and HNSW build cost on every
upsert). Drop them. The role_category column is kept (harmless; upsert unchanged).
"""
from django.db import migrations

_UP = """
DROP INDEX IF EXISTS job_pool_vec_gnn_hnsw;
DROP INDEX IF EXISTS job_pool_vec_role_idx;
"""

_DOWN = """
CREATE INDEX IF NOT EXISTS job_pool_vec_gnn_hnsw ON job_pool_vec USING hnsw (gnn_emb vector_cosine_ops);
CREATE INDEX IF NOT EXISTS job_pool_vec_role_idx ON job_pool_vec (role_category);
"""


class Migration(migrations.Migration):
    dependencies = [("matching", "0002_job_pool_vec")]
    operations = [migrations.RunSQL(_UP, reverse_sql=_DOWN)]
