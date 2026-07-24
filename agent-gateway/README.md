# AstrBot Agent Gateway

This service keeps QQ transport in AstrBot while moving Agent execution,
automatic hybrid RAG, web search, conversation memory, and administration into
an independently deployable process.

## Runtime flow

```text
AstrBot QQ plugin -> POST /v1/events -> group allowlist -> BGE-M3
                                            |             |
                                            |             v
                                            |      Qdrant dense + BM25 + RRF
                                            v
                                  Pi Agent + Exa tools -> QQ reply
```

- Event decisions, admin settings, and conversation memory persist in
  `/data/gateway.sqlite3`.
- Duplicate OneBot deliveries reuse the first persisted decision.
- Every eligible question performs local retrieval before the LLM call.
- Conversations are isolated by AstrBot UMO. Older exchanges roll into a
  bounded summary; the prompt reserves room for output, system instructions,
  and RAG evidence within the configured context window.
- Gateway errors fail closed and never fall back to AstrBot's old LLM path.

## Configuration

Copy `.env.example` to the ignored `.env` file and replace every placeholder.
`EVENT_TOKEN` authenticates AstrBot event delivery. `ADMIN_TOKEN` is separate
and only authenticates management requests. `GROUP_WHITELIST` is a
comma-separated list of QQ group IDs. Do not commit the real file.

Start the sidecar through `rag-stack/docker-compose.yml` while keeping
`AGENT_GATEWAY_ENABLED=false` until acceptance tests pass.

## Admin API

`GET /v1/admin/config` and `PATCH /v1/admin/config` require
`Authorization: Bearer $ADMIN_TOKEN`. The writable payload is deliberately
limited to a model ID and complete group allowlist:

```json
{
  "model": "deepseek-v4-pro",
  "group_whitelist": ["123456789", "987654321"]
}
```

The AstrBot plugin exposes the same operations only to an administrator's
private QQ chat:

```text
-astrbot切换 状态
-astrbot切换 模型 deepseek-v4-pro
-astrbot切换 白名单 列表
-astrbot切换 白名单 添加 <群号>
-astrbot切换 白名单 删除 <群号>
```

## Verification

```bash
npm ci
npm run typecheck
npm test
curl -fsS http://127.0.0.1:8090/healthz
curl -fsS http://127.0.0.1:8090/readyz
```
