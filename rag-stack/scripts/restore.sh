#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 || "$2" != "--confirm" ]]; then
  echo "Usage: $0 BACKUP_DIRECTORY --confirm" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

BACKUP_DIR="$(realpath "$1")"
if [[ ! -f "${BACKUP_DIR}/manifest.json" ]]; then
  echo "Backup manifest not found: ${BACKUP_DIR}" >&2
  exit 1
fi

"${SCRIPT_DIR}/rollback.sh"
astrbot_compose stop astrbot
cp -a "${BACKUP_DIR}/knowledge_base/." "${ASTRBOT_KB_ROOT}/"

if [[ -d "${BACKUP_DIR}/astrbot_data" ]]; then
  cp -a "${BACKUP_DIR}/astrbot_data/." "$(dirname "${ASTRBOT_KB_ROOT}")/"
fi

astrbot_compose up -d astrbot
echo "AstrBot SQLite/FAISS state restored. Qdrant snapshot files remain in ${BACKUP_DIR}/qdrant."
echo "Upload those snapshots only if a Qdrant rollback is also required."
