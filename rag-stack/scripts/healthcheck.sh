#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

exec python3 "${SCRIPT_DIR}/astrbot_ops.py" \
  verify --mode "${ASTRBOT_HEALTHCHECK_MODE:-full}" "$@"
