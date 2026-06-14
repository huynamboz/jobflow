# Postgres 16 (alpine) + pgvector — feature 027 Stage B.
# Same alpine/musl base as the original `postgres:16-alpine` so the existing
# data volume mounts without a libc/collation mismatch (a debian pgvector image
# on a musl-initialised volume risks collation-version index corruption).
#
# Build is baked into the image so the extension survives container recreation
# (a live `apk add` / source build does not).
FROM postgres:16-alpine

RUN set -eux; \
    apk add --no-cache --virtual .pgvbuild build-base git clang19 llvm19; \
    cd /tmp; \
    git clone --depth 1 --branch v0.8.0 https://github.com/pgvector/pgvector.git; \
    cd pgvector; \
    make PG_CONFIG=/usr/local/bin/pg_config; \
    make install PG_CONFIG=/usr/local/bin/pg_config; \
    cd /; rm -rf /tmp/pgvector; \
    apk del .pgvbuild
