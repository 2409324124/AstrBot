# AstrBot / Agent Gateway 接手说明

> 更新日期：2026-07-29（Asia/Shanghai）  
> 用途：在清空当前超长会话后，让新的 Codex/Agent 不依赖聊天历史即可继续维护。  
> 安全：本文不记录 sudo 密码、QQ 凭据、API Key 或真实 token。真实值只存在远端未跟踪的 `.env` 文件中。

## 1. 先读这里

这是一个运行在远端 Ubuntu 服务器上的 QQ Bot。AstrBot 只负责 QQ/OneBot 传输；主要对话编排已经切到独立的 TypeScript Agent Gateway。Gateway 负责语义路由、Pi Agent、Exa 搜索、本地混合 RAG、会话记忆、token 统计和群白名单。

接手后先做只读检查，不要直接 `git pull`、重建全部容器、迁移知识库或重启 NapCat。生产 QQ 登录状态在 NapCat 中，通常不应重启它。

本地审计文档：

- `task_plan.md`：阶段、决策和已知错误
- `findings.md`：根因与架构发现
- `progress.md`：测试、部署和回滚证据
- `agent-gateway/README.md`：Gateway 接口与命令边界
- `rag-stack/README.md`：本地 RAG、备份、迁移和运维

## 2. 主机、仓库和分支

### 本机工作副本

```bash
cd /home/miku/astrbot-rag-work
git status --short
git log -3 --oneline --decorate
```

- 本机路径：`/home/miku/astrbot-rag-work`
- 当前分支：`feature/local-rag-qdrant`
- 用户 fork：`git@github.com:2409324124/AstrBot.git`，remote 名为 `fork`
- 上游：`https://github.com/AstrBotDevs/AstrBot.git`，remote 名为 `origin`
- 功能提交：`0f6b6b3 feat: add gateway session command controls`
- 最新审计提交：`9ca8140 docs: record gateway command rollout`
- 截至 2026-07-29，本机与 `fork/feature/local-rag-qdrant` 同步且工作树干净。

### 远端生产机

远端经 Tailscale 地址连接：

```bash
ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=6 miku@100.66.104.25
```

远端路径：

```text
/home/miku/astrbot-deploy/AstrBot     # 生产源码
/mnt/PM983/astrbot-rag                 # Qdrant、模型缓存、Gateway SQLite、快照
/home/miku/astrbot-deploy/backups      # 部署前源码/配置/SQLite 备份
```

生产源码最后确认在 `0f6b6b3`；`9ca8140` 仅增加审计文档。接手时必须重新确认：

```bash
cd /home/miku/astrbot-deploy/AstrBot
git status --short
git rev-parse --short HEAD
git branch --show-current
```

远端 Docker 通常需要 `sudo`。让用户在交互式 SSH 中执行 `sudo -v`，不要把密码写进命令、脚本、日志或本文。

## 3. 当前架构

```text
QQ
 │
NapCat / OneBot
 │
AstrBot + astrbot_plugin_agent_gateway
 │  POST /v1/events（EVENT_TOKEN）
Agent Gateway :8090
 ├─ 语义意图路由（独立 LLM JSON 分类）
 ├─ Pi Agent / DeepSeek 在线 API
 ├─ Exa Web/X 搜索
 ├─ BGE-M3 Embedding :8000
 ├─ Qdrant :6333（dense + BM25 + RRF）
 └─ SQLite /data/gateway.sqlite3（记忆、配置、决策、用量）
```

主要容器：

```text
astrbot
napcat
astrbot-agent-gateway
astrbot-embedding
astrbot-qdrant
```

服务端口都只发布到远端回环地址：

- AstrBot Dashboard：`127.0.0.1:6185`
- Gateway：`127.0.0.1:8090`
- BGE-M3 OpenAI-compatible Embedding：`127.0.0.1:8000/v1`
- Qdrant：`127.0.0.1:6333`

模型与数据：

- Embedding：`BAAI/bge-m3`，1024 维，GPU 运行
- 向量集合：`agent_rag_v1`
- 在线主模型与 Router：生产最后确认为 `deepseek-v4-pro`
- Gateway 上下文硬预算：16384 tokens
- 持久根目录：`/mnt/PM983/astrbot-rag`

## 4. 第一次接手时的只读检查

登录远端后：

```bash
cd /home/miku/astrbot-deploy/AstrBot
sudo -v

sudo docker ps --format '{{.Names}}|{{.Status}}|{{.Image}}' \
  | grep -E '^(astrbot|napcat)'

sudo docker inspect \
  astrbot astrbot-agent-gateway napcat astrbot-qdrant astrbot-embedding \
  --format '{{.Name}}|restart={{.RestartCount}}|status={{.State.Status}}|started={{.State.StartedAt}}'

curl -fsS http://127.0.0.1:8090/healthz
curl -fsS http://127.0.0.1:8090/readyz

df -h / /mnt/PM983
nvidia-smi
```

预期：五个容器均为 running，Gateway health/ready 正常，restart count 为 0。最后一次部署只重建了 AstrBot 与 Gateway，NapCat/Qdrant/Embedding 保持原启动时间。

只看启动和错误，不要直接倾倒群聊原文：

```bash
sudo docker logs --since 15m astrbot 2>&1 \
  | grep -E 'agent_gateway|Agent Gateway|ERROR|Traceback|Exception' \
  | tail -n 80

sudo docker logs --since 15m astrbot-agent-gateway 2>&1 \
  | grep -E 'ERROR|Traceback|Exception|health|ready' \
  | tail -n 80
```

## 5. Compose 与日常启停

真实秘密文件：

```text
/home/miku/astrbot-deploy/AstrBot/rag-stack/.env
/home/miku/astrbot-deploy/AstrBot/agent-gateway/.env
```

两者均未跟踪，禁止打印全文或提交。发布模板是对应的 `.env.example`。

### RAG/Gateway Compose

```bash
cd /home/miku/astrbot-deploy/AstrBot
sudo docker compose \
  --env-file rag-stack/.env \
  -f rag-stack/docker-compose.yml \
  ps
```

只重建 Gateway：

```bash
sudo docker compose \
  --env-file rag-stack/.env \
  -f rag-stack/docker-compose.yml \
  up -d --build --force-recreate agent-gateway
```

### AstrBot Compose

AstrBot 使用两个 Compose 文件；遗漏 `--env-file` 会在 Qdrant 密钥插值阶段失败：

```bash
sudo docker compose \
  --env-file rag-stack/.env \
  -f compose.yml \
  -f rag-stack/astrbot.override.yml \
  ps
```

只重建 AstrBot：

```bash
sudo docker compose \
  --env-file rag-stack/.env \
  -f compose.yml \
  -f rag-stack/astrbot.override.yml \
  up -d --no-build --force-recreate astrbot
```

不要使用不带服务名的 `down`/`up --force-recreate`；这可能无意重启 NapCat、Embedding 或 Qdrant。

## 6. 远端代理与构建坑

远端代理最后使用：

```bash
export HTTP_PROXY=http://127.0.0.1:18081
export HTTPS_PROXY=http://127.0.0.1:18081
export http_proxy="$HTTP_PROXY"
export https_proxy="$HTTPS_PROXY"
```

代理只对远端主机回环有效。容器构建需要通过 `RAG_BUILD_PROXY`/Compose build args；不要假定容器里的 `127.0.0.1:18081` 指向宿主机。

已知问题：一次 Gateway 常规构建在获取 Docker Hub `node:22.19.0-bookworm-slim` 元数据时超时。因为当次 `package.json` 与 lockfile 没变化，临时从已验证旧镜像只覆盖 `src/`，并以 `--network=none` 构建成功。这只是依赖未变化时的应急办法；依赖变化后必须完成正常联网构建。

远端大于等于 1GB 的下载不要由 Agent 自动执行，应把明确命令交给用户手动运行。BGE-M3 已缓存，不应重复下载。

## 7. 备份、恢复与最后回滚点

最后一次部署前备份：

```text
/mnt/PM983/astrbot-rag/snapshots/astrbot-rag-20260726T192451Z
/home/miku/astrbot-deploy/backups/session-controls-20260726T192508Z
```

后者包含：

- `source.bundle`
- `cmd_config.json`（敏感，0600）
- `gateway.sqlite3`（敏感，0600）

新备份通常使用：

```bash
cd /home/miku/astrbot-deploy/AstrBot
./rag-stack/scripts/backup.sh
```

已知坑：该脚本曾因 Compose 视图不含 AstrBot 而报告 `service "astrbot" is not running`。不要因此重启服务；可直接调用同一只读备份实现：

```bash
sudo docker exec astrbot \
  python /AstrBot/rag-stack/scripts/backup_state.py
```

回滚脚本在 `rag-stack/scripts/rollback.sh`，但它会切回 FAISS 并重建 AstrBot；执行前必须先读脚本、确认 `.env` 和目标回滚范围。禁止使用 `git reset --hard` 或删除现有 Qdrant 数据。

## 8. Gateway 命令和权限边界

Gateway 切流后，以下命令在 QQ 插件入口截流，不进入普通意图/RAG/LLM：

- `~/new`：清 Gateway 会话和该会话 token 统计
- `~/reset`：清 Gateway 会话，保留统计
- `~/stop`：取消当前 Router/Pi Agent 请求
- `~/stats`：读取已完成调用统计，不调用模型
- `~/help`：程序固定回复
- `~/research <问题>`：明确强制外部研究
- `/sid`：放行 AstrBot
- 管理员 `/name`：放行 AstrBot
- `/provider`：提示改用 `-astrbot切换 模型 <ID>`
- `/dashboard_update`、`/set`、`/unset` 和未知斜杠命令：静默截流，零 token

权限：

- Gateway 白名单群成员只能控制本群会话
- 私聊只有 AstrBot 管理员可以使用控制命令和 Gateway 管理命令
- 白名单外群在 Gateway 之前拒绝

管理员私聊管理命令：

```text
-astrbot切换 状态
-astrbot切换 模型 deepseek-v4-pro
-astrbot切换 白名单 列表
-astrbot切换 白名单 添加 <群号>
-astrbot切换 白名单 删除 <群号>
```

不要在文档里硬编码管理员 QQ 或当前白名单。使用上述只读命令查询运行状态，防止文档过期。

## 9. 定时任务明确关闭

用户不需要定时任务。当前设计有三层约束：

1. Gateway 不暴露 cron/reminder 工具。
2. Gateway 系统提示禁止声称已创建定时任务。
3. AstrBot `provider_settings.proactive_capability.add_cron_tools=false`。

验证：

```bash
sudo docker exec astrbot python -c '
import json, sqlite3
c=json.load(open("/AstrBot/data/cmd_config.json", encoding="utf-8-sig"))
print("add_cron_tools=", c.get("provider_settings", {}).get("proactive_capability", {}).get("add_cron_tools"))
d=sqlite3.connect("/AstrBot/data/data_v4.db")
print("cron_jobs=", d.execute("select count(*) from cron_jobs").fetchone()[0])
d.close()
'
```

预期：`False` 和 `0`。可逆配置脚本：

```bash
sudo docker exec astrbot \
  python /AstrBot/rag-stack/scripts/configure_agent_safety.py apply
```

恢复状态位于未跟踪文件 `rag-stack/runtime/agent-safety-backup.json`。除非用户明确改变需求，不要执行 restore。

## 10. 测试门禁

本机：

```bash
cd /home/miku/astrbot-rag-work/agent-gateway
npm ci
npm run typecheck
npm test

cd /home/miku/astrbot-rag-work
.venv/bin/python -m pytest -q tests/unit/test_agent_gateway_plugin.py
.venv/bin/ruff check astrbot_plugin_agent_gateway tests/unit/test_agent_gateway_plugin.py
git diff --check
```

最后一次结果：Node 8 个测试文件通过，Python 相关矩阵 70 项通过，生产容器插件测试 19/19 通过。系统 Python 可能缺 `pytest_asyncio`，优先使用项目 `.venv`；本机 `aiosqlite 0.22.1` 曾在全量测试中挂起，持久化相关回归可在远端 AstrBot 容器中验证。

生产容器插件测试：

```bash
sudo docker exec astrbot \
  python -m pytest -q /AstrBot/tests/unit/test_agent_gateway_plugin.py
```

## 11. 仍需完成/继续观察

1. 从真实 QQ 白名单群执行 `~/stats`、`~/new`，再问依赖旧记忆的问题，确认下一轮不携带旧会话。HTTP 控制端已验证，但真实 QQ 传输层验证仍应保留。
2. 继续观察“号主实际发言后 15 分钟人工接管”与明确交还提示词。OneBot 无法可靠表达单纯的“号主在线”，只能根据号主真实发言建立活动窗口。
3. RAG 路由边界必须维持：`local_knowledge` 自动 RAG；`technical_concept` 不自动注入，但可由 Agent 按需调用 RAG/Web；闲聊不应出现“知识库没有资料”。
4. 群里的短省略追问必须把 OneBot Reply 正文作为 `reply_context` 传给 Router、检索和回答。不要退回仅按当前短文本分类。
5. 任何生产 canary 都要同时核对 route、automatic RAG hits、工具调用、最终相关性和 token，不要只看“有没有回复”。

## 12. 修改与发布纪律

- 行为修复先补失败测试，再实现，再跑相关门禁。
- 修改前备份配置、Gateway SQLite 和必要的 Qdrant 状态。
- 保留用户已有工作树，不使用破坏性 reset/checkout。
- 真实密钥只放未跟踪 `.env`，模板使用占位符。
- 用户明确要求 push 时，正常检查通过后直接 push 到 `fork/feature/local-rag-qdrant`。
- 部署时只重建有变化的 AstrBot 或 Gateway；不要顺手重启 NapCat/Qdrant/Embedding。
- 日志输出按事件 ID、路由、错误计数筛选，不把群聊/私聊正文写入 Git 审计文档。

## 13. 给新 Agent 的最短启动提示

可以把下面这段直接作为新会话首条消息：

```text
请先完整阅读 /home/miku/astrbot-rag-work/AGENT_HANDOFF.md、task_plan.md、findings.md、progress.md。
本机仓库是 /home/miku/astrbot-rag-work，分支 feature/local-rag-qdrant；生产机用
ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=6 miku@100.66.104.25，远端仓库是
/home/miku/astrbot-deploy/AstrBot。先做只读状态检查，不要重启 NapCat/Qdrant/Embedding，
不要打印 .env 或聊天正文。需要修改时遵循测试先行、部署前备份、只重建目标服务。
```
