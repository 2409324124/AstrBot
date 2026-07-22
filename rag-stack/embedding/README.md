# Embedding service

The stack runs `BAAI/bge-m3` with the Ampere build of Text Embeddings Inference.
It exposes the OpenAI-compatible `POST /v1/embeddings` endpoint on loopback port
8000 and returns 1024-dimensional dense vectors.

The image and model exceed 1 GB. On the remote server, run
`scripts/download-model.sh` manually so the download follows the remote download
policy and can use the configured proxy.
