#!/usr/bin/env bash
# Duplicate backend/ml_service/ → backend/ml_benchmark/ as a frozen sandbox
# for thesis multi-dataset benchmarking. Idempotent: refuses to overwrite
# unless --force is passed.
#
# Implements specs/007-duplicate-ml-benchmark/ plan + research decisions.
#
# Usage:
#   bash backend/scripts/duplicate_ml_service.sh
#   bash backend/scripts/duplicate_ml_service.sh --force   # for re-running

set -euo pipefail

SOURCE="backend/ml_service"
TARGET="backend/ml_benchmark"
FORCE="${1:-}"

if [ ! -d "$SOURCE" ]; then
  echo "ERROR: source $SOURCE does not exist. Run from repo root." >&2
  exit 2
fi

if [ -e "$TARGET" ]; then
  if [ "$FORCE" = "--force" ]; then
    echo "[duplicate] --force given. Removing existing $TARGET ..."
    rm -rf "$TARGET"
  else
    echo "ERROR: $TARGET already exists. Refusing to overwrite." >&2
    echo "To re-run, manually: rm -rf $TARGET && bash $0" >&2
    echo "Or pass --force." >&2
    exit 1
  fi
fi

echo "[duplicate] (a) copying $SOURCE → $TARGET"
cp -R "$SOURCE" "$TARGET"

echo "[duplicate] (b) cleaning caches in $TARGET"
find "$TARGET" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "$TARGET" -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
find "$TARGET" -name '*.pyc' -delete 2>/dev/null || true

echo "[duplicate] (c) stripping production-only modules"
STRIP_DIRS=(
  "$TARGET/api"
  "$TARGET/inference"
  "$TARGET/reranker"
  "$TARGET/verifier"
  "$TARGET/crawler/providers"
)
STRIP_FILES=(
  "$TARGET/crawler/factory.py"
  "$TARGET/crawler/scheduler.py"
  "$TARGET/crawler/storage.py"
  "$TARGET/crawler/README.md"
)
for d in "${STRIP_DIRS[@]}"; do
  if [ -e "$d" ]; then
    rm -rf "$d"
    echo "         removed $d"
  fi
done
for f in "${STRIP_FILES[@]}"; do
  if [ -e "$f" ]; then
    rm -f "$f"
    echo "         removed $f"
  fi
done

echo "[duplicate] (d) rewriting imports ml_service.* → ml_benchmark.*"
# BSD sed (macOS). Regex matches ml_service when preceded by start-of-line
# or non-identifier char, and followed by '.' or whitespace boundary.
FILES_WITH_REF=$(grep -rl --include='*.py' 'ml_service' "$TARGET" || true)
if [ -n "$FILES_WITH_REF" ]; then
  echo "$FILES_WITH_REF" | xargs sed -i '' -E 's/(^|[^a-zA-Z_])ml_service([.[:space:]])/\1ml_benchmark\2/g'
  REWRITE_COUNT=$(echo "$FILES_WITH_REF" | wc -l | tr -d ' ')
  echo "         rewrote $REWRITE_COUNT file(s)"
else
  echo "         no files contained ml_service reference"
fi

echo "[duplicate] (e) summary"
MODULE_COUNT=$(find "$TARGET" -maxdepth 1 -type d ! -path "$TARGET" | wc -l | tr -d ' ')
PY_COUNT=$(find "$TARGET" -name '*.py' | wc -l | tr -d ' ')
REMAINING_REF=$(grep -rln --include='*.py' 'ml_service' "$TARGET" || true)
echo "         modules in sandbox: $MODULE_COUNT"
echo "         .py files in sandbox: $PY_COUNT"
if [ -n "$REMAINING_REF" ]; then
  echo "         WARNING: residual ml_service references in:"
  echo "$REMAINING_REF" | sed 's/^/           /'
else
  echo "         residual ml_service references: 0 ✓"
fi

echo "[duplicate] DONE"
