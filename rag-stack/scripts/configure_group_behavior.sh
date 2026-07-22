#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

astrbot_compose exec -T astrbot \
  python /AstrBot/rag-stack/scripts/configure_group_behavior.py "$@"
