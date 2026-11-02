#!/usr/bin/env bash
# Idempotent setup of the 8k-context vision model.
set -euo pipefail

BASE="${BASE:-qwen2.5vl:3b}"
DERIVED="${DERIVED:-qwen2.5vl:3b-8k}"
CTX="${CTX:-8192}"

echo "==> Pulling base model $BASE"
ollama pull "$BASE"

echo "==> Deriving $DERIVED with num_ctx=$CTX"
TMP="$(mktemp)"
ollama show "$BASE" --modelfile > "$TMP"

if grep -q '^PARAMETER num_ctx' "$TMP"; then
    # Portable in-place replace (BSD + GNU sed)
    sed -i.bak "s/^PARAMETER num_ctx.*/PARAMETER num_ctx $CTX/" "$TMP"
    rm -f "$TMP.bak"
else
    echo "PARAMETER num_ctx $CTX" >> "$TMP"
fi

ollama create "$DERIVED" -f "$TMP"
rm -f "$TMP"

echo "==> Verifying"
ollama show "$DERIVED" | grep -i num_ctx
echo "==> Done."
