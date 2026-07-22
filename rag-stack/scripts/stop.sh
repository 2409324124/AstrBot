#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

if [[ "${ASTRBOT_VECTOR_DB:-faiss}" == "qdrant" && "${1:-}" != "--force" ]]; then
  echo "AstrBot is configured for Qdrant. Run rollback.sh first or pass --force." >&2
  exit 1
fi

rag_compose down
