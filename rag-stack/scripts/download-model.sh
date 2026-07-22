#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

rag_compose pull embedding-server

download_container="astrbot-embedding-download"
tei_image="${TEI_IMAGE:-ghcr.io/huggingface/text-embeddings-inference:86-1.9}"
cache_dir="${RAG_DATA_ROOT}/hf-cache"
proxy_url="${HTTPS_PROXY:-${https_proxy:-}}"
model_cache_name="models--${EMBEDDING_MODEL//\//--}"
helper_image="${ASTRBOT_RAG_IMAGE:-astrbot-local-rag:4.26.5}"

cleanup() {
  "${DOCKER[@]}" rm -f "${download_container}" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

proxy_args=()
if [[ -n "${proxy_url}" ]]; then
  proxy_args+=(
    -e "HTTPS_PROXY=${proxy_url}"
    -e "HTTP_PROXY=${proxy_url}"
    -e "https_proxy=${proxy_url}"
    -e "http_proxy=${proxy_url}"
  )
else
  echo "No HTTPS_PROXY is set; the model bootstrap will use direct network access." >&2
fi

echo "Starting one-time host-network download container."
echo "Follow detailed progress in another shell with:"
echo "  ${DOCKER[*]} logs -f ${download_container}"
"${DOCKER[@]}" run -d \
  --name "${download_container}" \
  --network host \
  --runtime=nvidia \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
  --shm-size 1g \
  "${proxy_args[@]}" \
  -v "${cache_dir}:/data" \
  "${tei_image}" \
  --model-id "${EMBEDDING_MODEL}" \
  --served-model-name "${EMBEDDING_MODEL}" \
  --port 8000 \
  --dtype float16 \
  --max-client-batch-size 64 \
  --api-key "${EMBEDDING_API_KEY}" >/dev/null

download_ready=0
for attempt in {1..2880}; do
  if curl -fsS \
    -H "Authorization: Bearer ${EMBEDDING_API_KEY}" \
    http://127.0.0.1:8000/health >/dev/null 2>&1; then
    download_ready=1
    break
  fi
  if [[ "$("${DOCKER[@]}" inspect -f '{{.State.Running}}' "${download_container}")" != "true" ]]; then
    "${DOCKER[@]}" logs --tail 200 "${download_container}" >&2
    echo "The temporary embedding downloader exited before becoming ready." >&2
    exit 1
  fi
  if (( attempt % 12 == 0 )); then
    du -sh "${cache_dir}" 2>/dev/null || true
  fi
  sleep 5
done
if [[ "${download_ready}" -ne 1 ]]; then
  echo "BGE-M3 did not finish downloading within four hours." >&2
  exit 1
fi

"${DOCKER[@]}" stop "${download_container}" >/dev/null
"${DOCKER[@]}" rm "${download_container}" >/dev/null

"${DOCKER[@]}" run --rm \
  --entrypoint python \
  -v "${cache_dir}:/data" \
  "${helper_image}" \
  -c "from pathlib import Path; root=Path('/data/${model_cache_name}/snapshots'); snapshots=[p for p in root.iterdir() if p.is_dir()]; assert snapshots, f'no snapshots under {root}'; link=Path('/data/bge-m3'); link.unlink(missing_ok=True); link.symlink_to(max(snapshots, key=lambda p: p.stat().st_mtime))"

rag_compose up -d embedding-server
for _ in {1..120}; do
  if curl -fsS \
    -H "Authorization: Bearer ${EMBEDDING_API_KEY}" \
    http://127.0.0.1:8000/health >/dev/null 2>&1; then
    trap - EXIT
    echo "BGE-M3 is cached and the normal embedding service is ready."
    exit 0
  fi
  sleep 2
done

rag_compose logs --tail 200 embedding-server >&2
echo "The normal embedding service did not become ready." >&2
exit 1
