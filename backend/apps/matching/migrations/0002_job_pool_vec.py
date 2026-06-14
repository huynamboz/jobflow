"""Feature 027 Stage B: pgvector ANN store for job-pool retrieval.

Raw SQL (pgvector type isn't a native Django field and we access it via raw SQL
in pgvector_store.py, so no ORM model is needed). D=256 GNN emb, 384 text vec.
"""
from django.db import migrations

_UP = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS job_pool_vec (
    job_id            bigint PRIMARY KEY,
    gnn_emb           vector(256) NOT NULL,
    text_vec          vector(384),
    role_category     varchar(20) NOT NULL DEFAULT '',
    model_fingerprint varchar(64) NOT NULL,
    content_hash      varchar(64) NOT NULL DEFAULT '',
    updated_at        timestamptz NOT NULL DEFAULT now()
);

-- HNSW index for cosine ANN on the GNN embedding (the recall metric)
CREATE INDEX IF NOT EXISTS job_pool_vec_gnn_hnsw
    ON job_pool_vec USING hnsw (gnn_emb vector_cosine_ops);

CREATE INDEX IF NOT EXISTS job_pool_vec_fp_idx ON job_pool_vec (model_fingerprint);
CREATE INDEX IF NOT EXISTS job_pool_vec_role_idx ON job_pool_vec (role_category);
"""

_DOWN = """
DROP TABLE IF EXISTS job_pool_vec;
-- leave the `vector` extension installed (other features may rely on it)
"""


class Migration(migrations.Migration):
    dependencies = [("matching", "0001_initial")]
    operations = [migrations.RunSQL(_UP, reverse_sql=_DOWN)]
