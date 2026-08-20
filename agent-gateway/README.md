# AstrBot Agent Gateway

This service keeps QQ transport in AstrBot while moving Agent execution,
automatic hybrid RAG, web search, conversation memory, and administration into
an independently deployable process.

## Runtime flow

```text
AstrBot QQ plugin -> POST /v1/events -> group allowlist -> semantic intent router
                                                               |
                         +----------------+---------------------+----------------+
                         |                |                     |                |
                       chat        local/technical        external fact       fallback
                         |                |                     |                |
                      no RAG       BGE-M3 + Qdrant          Exa search      tools, no auto RAG
                         +----------------+---------------------+----------------+
                                                               |
                                                           Pi Agent -> QQ
```

- Event decisions, admin settings, conversation memory, and per-session token
  usage persist in
  `/data/gateway.sqlite3`.
- Duplicate OneBot deliveries reuse the first persisted decision.
- The isolated router sees only the current untrusted message and returns one
  validated semantic route. Casual chat and external facts never receive
  automatic local evidence.
- Local-knowledge and technical routes use BGE-M3 + dense/BM25/RRF before the
  main LLM. A router failure exposes both tools but injects no automatic RAG,
  so classification failure cannot silently block later retrieval.
- Conversations are isolated by AstrBot UMO. Older exchanges roll into a
  bounded summary; the prompt reserves room for output, system instructions,
  and RAG evidence within the configured context window.
- Gateway errors fail closed and never fall back to AstrBot's old LLM path.
- `~/new`, `~/reset`, `~/stop`, and `~/stats` use an authenticated control endpoint
  before routing, RAG, web search, or LLM execution. Reset is serialized with
  the same UMO so an aborted request cannot restore cleared history.

## Configuration

Copy `.env.example` to the ignored `.env` file and replace every placeholder.
`EVENT_TOKEN` authenticates AstrBot event delivery. `ADMIN_TOKEN` is separate
and only authenticates management requests. `GROUP_WHITELIST` is a
comma-separated list of QQ group IDs. Do not commit the real file.

`ROUTER_MODEL` can use a separate low-latency model from the main Agent.
`ROUTER_TIMEOUT_MS` defaults to 30000 and `ROUTER_MAX_OUTPUT_TOKENS` defaults
to 512; reasoning models may consume most of a smaller limit before producing
their JSON decision.

Set `OUTBOUND_HTTP_PROXY` only when the container needs an HTTP(S) egress
proxy for the online LLM or web tools. The Gateway installs it before creating
clients and explicitly bypasses `qdrant`, `embedding-server`, and loopback
addresses, so local BGE-M3 and Qdrant remain on the Docker network.

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

## QQ command boundary

- Whitelisted group members may use `~/new`, `~/reset`, `~/stop`, `~/stats`,
  `~/help`, and `~/research <question>`. Private controls remain
  administrator-only.
- `~/new` clears Gateway memory and usage; `~/reset` clears memory but retains
  usage; `~/stop` aborts the active router or answer; `~/stats` reports completed
  router and Agent calls.
- `/sid` and administrator `/name` pass through to AstrBot transport commands.
  `/provider` redirects to `-astrbot切换 模型 <ID>`.
- `/dashboard_update`, `/set`, `/unset`, and unknown slash commands are silently
  intercepted and never consume model tokens.
- Retired Gateway controls such as `/new` and `/stats` are also silently
  intercepted; use their `~/` forms instead.
- Explicit `~/research <question>` bypasses semantic classification and performs Exa search
  before the answer model runs.

## Verification

```bash
npm ci
npm run typecheck
npm test
curl -fsS http://127.0.0.1:8090/healthz
curl -fsS http://127.0.0.1:8090/readyz
```
