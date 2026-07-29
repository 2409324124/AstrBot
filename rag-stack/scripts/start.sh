#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

mkdir -p \
  "${RAG_DATA_ROOT}/qdrant" \
  "${RAG_DATA_ROOT}/hf-cache" \
  "${RAG_DATA_ROOT}/snapshots"

rag_compose up -d

if [[ "${1:-}" == "--with-astrbot" ]]; then
  astrbot_compose up -d astrbot napcat
  ASTRBOT_HEALTHCHECK_MODE=full "${SCRIPT_DIR}/healthcheck.sh"
else
  ASTRBOT_HEALTHCHECK_MODE=core "${SCRIPT_DIR}/healthcheck.sh"
fi
