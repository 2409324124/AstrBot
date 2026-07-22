#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

if [[ "${ASTRBOT_VECTOR_DB:-faiss}" != "faiss" ]]; then
  echo "Cutover requires ASTRBOT_VECTOR_DB=faiss before the final switch." >&2
  exit 1
fi

"${SCRIPT_DIR}/healthcheck.sh"
astrbot_compose build astrbot
astrbot_compose up -d astrbot

astrbot_ready=0
for _ in {1..60}; do
  if curl -fsS http://127.0.0.1:6185/ >/dev/null 2>&1; then
    astrbot_ready=1
    break
  fi
  sleep 2
done
if [[ "${astrbot_ready}" -ne 1 ]]; then
  echo "AstrBot did not become ready within 120 seconds." >&2
  exit 1
fi

astrbot_compose exec -T astrbot \
  python /AstrBot/rag-stack/scripts/configure_astrbot.py apply

python3 "${SCRIPT_DIR}/set_backend.py" "${RAG_ENV_FILE}" qdrant
set -a
# shellcheck disable=SC1090
source "${RAG_ENV_FILE}"
set +a
astrbot_compose up -d --force-recreate astrbot

echo "AstrBot now uses Qdrant. NapCat was not recreated."
