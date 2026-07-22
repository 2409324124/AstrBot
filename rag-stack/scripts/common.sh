#!/usr/bin/env bash
set -euo pipefail

RAG_STACK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAG_ENV_FILE="${RAG_ENV_FILE:-${RAG_STACK_ROOT}/.env}"

if [[ ! -f "${RAG_ENV_FILE}" ]]; then
  echo "Missing ${RAG_ENV_FILE}; copy .env.example and set real secrets." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${RAG_ENV_FILE}"
set +a

ASTRBOT_COMPOSE_FILE="${ASTRBOT_COMPOSE_FILE:-${RAG_STACK_ROOT}/../../compose.yml}"

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
else
  DOCKER=(sudo docker)
fi

rag_compose() {
  "${DOCKER[@]}" compose \
    --env-file "${RAG_ENV_FILE}" \
    -f "${RAG_STACK_ROOT}/docker-compose.yml" \
    "$@"
}

astrbot_compose() {
  "${DOCKER[@]}" compose \
    --env-file "${RAG_ENV_FILE}" \
    -f "${ASTRBOT_COMPOSE_FILE}" \
    -f "${RAG_STACK_ROOT}/astrbot.override.yml" \
    "$@"
}
