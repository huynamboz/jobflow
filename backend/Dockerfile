# JobFlow-GNN backend — production image (CPU-only torch).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

# Runtime libs: libpq for psycopg2, libgomp for torch, curl for healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch first (exact version that the local checkpoint/runtime uses) so
# requirements.txt's `torch>=2.0` is already satisfied and pip never pulls CUDA.
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.11.0"

COPY requirements.txt .
# Pin the HF stack to the exact versions running locally — newer transformers
# releases have an import-time `NameError: name 'nn' is not defined` on py3.11.
RUN pip install -r requirements.txt gunicorn whitenoise \
        "transformers==5.4.0" "sentence-transformers==5.3.0" "tokenizers==0.22.2"

# Bundle the multilingual sentence-transformer into the image so the first
# matching call doesn't stall downloading ~470MB at runtime.
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

COPY . .

EXPOSE 8000

# 1 worker on purpose: the GNN + embedding model load once into RAM (~1.2GB).
# Long timeout because a cold matching call is CPU-bound on 1 core.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "1", \
     "--threads", "2", \
     "--timeout", "600", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
