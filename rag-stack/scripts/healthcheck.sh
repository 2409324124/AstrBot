#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

curl -fsS \
  -H "api-key: ${QDRANT_API_KEY}" \
  http://127.0.0.1:6333/collections >/dev/null

curl -fsS \
  -H "Authorization: Bearer ${EMBEDDING_API_KEY}" \
  http://127.0.0.1:8000/health >/dev/null

response="$(curl -fsS \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${EMBEDDING_API_KEY}" \
  -d "{\"model\":\"${EMBEDDING_MODEL}\",\"input\":[\"测试中文embedding\"]}" \
  http://127.0.0.1:8000/v1/embeddings)"

EMBEDDING_RESPONSE="${response}" python3 - <<'PY'
import json
import math
import os

payload = json.loads(os.environ["EMBEDDING_RESPONSE"])
vector = payload["data"][0]["embedding"]
expected = int(os.environ.get("EMBEDDING_DIMENSION", "1024"))
if len(vector) != expected or not all(math.isfinite(value) for value in vector):
    raise SystemExit(f"invalid embedding: dimension={len(vector)}, expected={expected}")
print(json.dumps({"model": payload.get("model"), "dimension": len(vector)}))
PY
