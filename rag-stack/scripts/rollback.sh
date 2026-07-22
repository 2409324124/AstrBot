#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

python3 "${SCRIPT_DIR}/set_backend.py" "${RAG_ENV_FILE}" faiss
set -a
# shellcheck disable=SC1090
source "${RAG_ENV_FILE}"
set +a
astrbot_compose up -d --force-recreate astrbot

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
  python /AstrBot/rag-stack/scripts/configure_astrbot.py restore

echo "AstrBot restored the previous embedding providers and FAISS backend."
