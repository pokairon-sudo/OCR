#!/usr/bin/env bash
set -euo pipefail

echo "==> Python"
python --version

echo "==> Ollama daemon"
curl -sf http://127.0.0.1:11434/api/tags >/dev/null \
    && echo "OK: ollama reachable" \
    || { echo "FAIL: ollama not reachable on :11434"; exit 1; }

echo "==> Model present"
ollama list | grep -q 'qwen2.5vl:3b-8k' \
    && echo "OK: qwen2.5vl:3b-8k listed" \
    || { echo "FAIL: run scripts/setup_ollama_model.sh"; exit 1; }

echo "==> Context size"
ollama show qwen2.5vl:3b-8k | grep -E 'num_ctx\s+8192' \
    && echo "OK: 8k context baked in" \
    || { echo "FAIL: num_ctx not 8192"; exit 1; }

echo "==> Python imports"
python - <<'PY'
import cv2, ollama, pydantic
from invoice import extract, preprocess
print("OK: imports resolve")
PY

echo "==> Unit tests"
pytest -q
