# 进度日志：AstrBot 意图路由与本地证据

## 2026-07-19

### 阶段 7：完成性审计、真实回归与压力测试

- **状态：** complete
- 执行的操作：
  - 完整读取系统化调试与 TDD 工作流。
  - 沿 `build_main_agent()` → `_apply_verified_factual_reply_policy()` → `ResultDecorateStage` → `RespondStage` 追踪消息流。
  - 审计知识库的检索实现，确认本部署的 AstrBot 源码有 BM25 稀疏检索与向量检索融合能力。
  - 审计 Provider 接口，确认可以发起独立、无会话持久化的 JSON 分类调用。
  - TDD 第一条纵向切片：先新增 LLM JSON 路由测试，确认模块不存在时红灯；再实现隔离的 `classify_intent()`，测试转绿。
  - TDD 第二条纵向切片：先新增 Lorebook 激活测试，确认模块不存在时红灯；再实现只扫描原始用户消息、最多四条的非递归激活器，测试转绿。
  - TDD 第三条纵向切片：先令主 Agent 的本地路由测试因缺少路由接口红灯；再接入 `local_system` 路由，验证不会调用 Exa 且会注入本地 RAG 证据。
  - TDD 第四条纵向切片：先修改最终策略测试，证明它仍会按字符串重新判定而红灯；再删除该隐式分类，只执行主 Agent 已记录的结构化路由结果。
  - 新增运行时 Lorebook、默认配置和 Dashboard 配置元数据；默认关闭，远端部署时显式开启。
  - 远端先做时间戳源码备份，再同步文件并保存原配置；启用了 `intent_router_enabled=true`，路由模型仍复用当前模型。
  - 部署中发现一次扁平化同步，确认运行模块未被覆盖后立即以保留目录层级的方式修正；逐文件 SHA-256 匹配后只重启 AstrBot，并移除六个冗余根目录副本。
  - 最终远端运行检查：AstrBot、NapCat、Qdrant、Embedding 均运行，AstrBot 最近 90 秒错误关键词计数为 0。
  - 完成性审计重新对照原始设计，发现 `chat_creative` 会误落入外部事实分支；测试先稳定复现 Exa 被调用，再用显式聊天返回修复，精确测试转绿。
  - 补齐 `web_trusted` 外部证据标签；修复首条 Lorebook 条目可突破预算的漏洞，并补非递归与最近五条用户消息窗口测试。
  - 发现 Web Search 工具在意图路由前全局挂载；新增聊天路由工具隔离测试，加入路由门控并调整主链路为先分类、后注入搜索工具。
  - 将审计修复再次同步远端并逐文件校验哈希，只重启 AstrBot；四项容器均运行且无近期错误。
  - 通过三个临时 WebChat 会话进入真实主链路。外部事实可经 Exa 回答，但 BM25 与闲聊为空；三条路由日志均为 `external_fact/fallback=True`。
  - 只筛选分类器日志后确认根因方向：运行配置明确未开启 structured intent router，请求尚未进入 LLM 分类调用。开始审计默认配置与 UMO/会话级配置覆盖。
  - 通过只输出安全字段的 API 审计确认：仅有 default profile、没有 UMO 路由，实际默认配置的 router 开关为 false。
  - 在停/启仅 AstrBot 的窗口内原子备份并更新配置；持久化开关为 true，四项服务运行且无近期错误。
  - 第二次真实回归：BM25 与外部事实分类正确且均非 fallback；“你是谁”有回复但误分类为 local_system。
  - 为“助手身份不是本地部署问题”新增回归测试，先得到 RED；随后收紧 LLM 分类提示的语义边界并加入四类少量示例，相关测试与完整目标测试、Ruff、diff-check 全部通过。
  - 最终四路真实回归得到 local_system、chat_creative、technical_concept、external_fact，置信度均 0.99 且均非 fallback；所有回答非空并带 AI 标记。
  - 过滤 WebChat 工具事件后单独复测外部事实，纯最终回答明确给出 52 核并附可信来源。
  - 用不含“你是谁”的身份改写复测，仍为 chat_creative/0.99/non-fallback，证明不是精确示例字符串匹配。
  - 精确筛选最近 15 分钟 `[ERROR]`、Traceback、Exception，结果为空；宽泛 `error` 的三行不是服务级异常。
  - 用户要求继续测试，新增阶段 7 的语义边界与对抗性矩阵。
  - 执行九条真实压力案例；九条预期/实际路由全部一致，置信度 0.98–0.99，无 fallback，提示注入未改变路由。
  - 压力测试发现本地 BM25 限制回答出现多段重复与重复 AI 标记；按系统化调试转入事件级链路追踪，尚未修改生产代码。
  - 用多 Plain 最小测试稳定复现重复，完成 RED→GREEN 修复；又以大写内联 AI 标记测试完成第二个 RED→GREEN。两次均部署并只重启 AstrBot。
  - 容器内运行时断言与真实 WebChat 复测通过：正文不重复，规范标记一次，大写标记不存在。
  - 代表性 local/technical/chat 测试的 Exa 工具步骤为 0，但本地“外部搜索是否开启”回答发生前后矛盾；开始为 local_system 增加安全实时配置证据。
  - 以两条纵向测试实现 local_system 安全实时配置快照；只包含搜索开关、提供商、事实策略与路由开关，不含任何 Key；technical 路由不接收无关配置。
  - 部署动态配置证据后，同一搜索状态问题连续三次均正确回答已开启 Exa；密钥请求测试明确拒绝泄漏，疑似密钥前缀为 0。
  - 新增“问答服务/服务拓扑”Lorebook 别名并完成 RED→GREEN；远端按请求读取，无需重启，真实拓扑回答通过。
  - 最终六文件本地/远端 SHA-256 全匹配；pytest、Ruff、diff-check 通过；四容器运行、路由开关 true、最近 15 分钟真实错误计数 0。
- 创建/修改的文件：
  - `task_plan.md`
  - `findings.md`
  - `progress.md`
  - `astrbot/core/intent_router.py`
  - `astrbot/core/local_evidence.py`
  - `astrbot/core/astr_main_agent.py`
  - `astrbot/core/response_policy.py`
  - `astrbot/core/config/default.py`
  - `data/intent_lorebook.json`
  - `tests/unit/test_intent_router.py`
  - `tests/unit/test_astr_main_agent.py`
  - `tests/unit/test_response_policy.py`

## 测试结果

| 测试 | 输入 | 预期结果 | 实际结果 | 状态 |
|---|---|---|---|---|
| 根因路径审计 | “知识库是否使用 BM25” | 定位无回复的实际边界 | 已定位到无可信来源时的空消息链 | passed |
| LLM 路由器 | 模型 JSON：`local_system` | 无历史、无工具地解析为本地系统路由 | 1 passed | passed |
| Lorebook 激活 | 包含 BM25 的本地问题 | 仅激活 `bm25` 本地 RAG 条目 | 2 passed | passed |
| Lorebook 格式 | 一个有效条目和一个非法来源条目 | 只加载本地来源条目 | 4 passed | passed |
| 主 Agent 本地路由 | BM25 本地系统问题 | 不调用 Exa，注入 `local_rag` 证据 | 20 个相关测试通过 | passed |
| 最终回复边界 | 外部事实样式的纯文本 | 不做第二次字符串意图分类 | 20 个相关测试通过 | passed |
| 全量目标静态测试 | 路由器、回复策略与主 Agent | 行为保持一致且代码风格通过 | Ruff、pytest、diff-check 均退出 0 | passed |
| 远端文件校验 | 六个部署文件 | 远端与本地测试副本完全一致 | SHA-256 全部匹配 | passed |
| 远端运行状态 | 仅重启 AstrBot | 其他三项服务不受影响且无近期错误 | 四项服务运行、错误计数 0 | passed |
| 闲聊路由隔离 | `chat_creative` / “你是谁？” | 不调用 Exa、不设置 factual guard | RED 复现后 GREEN | passed |
| 外部来源类型 | WHO 可信来源 | 注入块标记 `web_trusted` | RED 复现后 GREEN | passed |
| Lorebook 硬预算 | 首条 1001 字符、预算 1000 | 不激活超限条目 | RED 复现后 GREEN | passed |
| Lorebook 非递归 | 已激活内容包含其他条目别名 | 不连锁激活 | 精确测试通过 | passed |
| 最近消息窗口 | 当前 + 5 条历史用户消息 | 仅当前与最近 4 条参与激活 | 精确测试通过 | passed |
| 搜索工具路由隔离 | chat 路由 + Exa 已启用 | 不向主模型挂载搜索工具 | RED 复现后 GREEN | passed |
| 真实 WebChat 三路回归（第一次） | BM25 / 闲聊 / 外部事实 | 分别路由到本地、聊天、外部检索 | 三条均 fallback 到 external；仅外部事实非空 | failed |
| 运行配置作用域审计 | 默认/UMO profile | 找到真实有效的 router 开关 | 默认 profile 为 false，无 UMO 覆盖 | passed |
| 真实 WebChat 三路回归（第二次） | BM25 / 闲聊 / 外部事实 | local / chat / external 且非 fallback | local / local / external；回答均非空 | partial |
| 身份闲聊分类边界 | 路由系统提示 | 明确身份闲聊与当前部署问题的边界 | RED 后 GREEN | passed |
| 目标回归与静态检查（提示修复后） | 三个目标测试文件与相关源码 | pytest、Ruff、diff-check 退出 0 | 全部退出 0 | passed |
| 最终四路真实回归 | local / chat / technical / external | 四类路由正确且不 fallback | 四类均 0.99、回答非空 | passed |
| 外部事实纯最终回复 | 9470C 核心数 | 52、可信来源、AI 标记 | 三项均存在 | passed |
| 身份语义改写 | 不含示例“你是谁” | chat_creative 且非 fallback | 0.99、非空 | passed |
| 精确运行错误筛选 | 最近 15 分钟 | 无 ERROR/Traceback/Exception | 空输出 | passed |
| 九条语义边界压力矩阵 | 本地改写 / 技术研究 / 通用与本地 BM25 / 闲聊 / 注入 | route_match 全 true、无 fallback | 9/9 路由正确 | passed |
| 多 Plain 回复策略 | 两个 Plain + AI 标记 | 正文各一次、规范标记一次 | RED 后 GREEN；容器内断言通过 | passed |
| 标记大小写归一化 | 内联 `（AI生成内容）` | 移除模型标记并只附规范版本 | RED 后 GREEN；真实回复通过 | passed |
| 非外部搜索隔离 | local / technical / chat | Exa 工具步骤为 0 | 0 | passed |
| 本地配置事实稳定性 | “是否开启外部搜索”重复测试 | 与当前配置一致 | 前后回答相反 | failed |
| 动态本地配置证据 | 零 Lorebook 命中的 local_system | 注入安全当前配置且不含 Key | RED 后 GREEN | passed |
| 本地配置事实稳定性（修复后） | 相同问题连续 3 次 | 三次均已开启 Exa | 3/3 一致 | passed |
| 凭据请求安全边界 | 询问当前 Exa Key | 不泄漏、不伪造、不触发搜索 | 通过 | passed |
| 中文服务拓扑 | “问答服务由哪些组件串起来” | 激活 deployment 并给出实际链路 | RED 后 GREEN；真实回归通过 | passed |
| 最终部署一致性 | 六个目标文件 | 本地/远端 SHA-256 一致 | 6/6 一致 | passed |
| 最终运行状态 | 四容器、路由开关、15 分钟错误 | 全在线、true、0 | 符合 | passed |

## 错误日志

| 时间 | 错误 | 次数 | 处理 |
|---|---|---:|---|
| 2026-07-19 | 首次按错误目录读取技能文件失败 | 1 | 用 `rg --files` 找到实际 `ok-skills` 路径后完整读取；不重复同一路径。 |
| 2026-07-19 | 远端原子部署命令的嵌套引号在 root shell 前解析失败 | 1 | 配置更新与容器重启均未执行；改用经同步的单独 root 脚本，不重复该复合命令。 |
| 2026-07-19 | 多源 `rsync` 扁平化目标路径，未覆盖实际模块 | 1 | 运行容器仍是旧代码；改用 `-R` 保留目录层级并以 SHA-256 复核，再做第二次仅 AstrBot 重启。 |
| 2026-07-19 | 真实回归三条请求均走 `fallback=True` | 1 | 日志证明是运行配置未启用 router，而非分类模型解析失败；转入配置作用域审计。 |
| 2026-07-19 | 远端不存在 `docker` 用户组，`sg docker` 读取日志失败 | 1 | 使用 `sudo docker logs` 并按分类器关键词过滤。 |
| 2026-07-19 | 系统 `pytest` 无法导入 `pytest_asyncio` | 1 | 确认项目 `.venv` 已含依赖，后续统一使用 `.venv/bin/pytest`。 |
| 2026-07-19 | “你是谁”被 LLM 判为 local_system | 1 | 以测试锁定语义边界，移除 “this bot” 的含混表述并明确身份/人格为 chat_creative。 |
| 2026-07-19 | 最终状态复合 SSH 命令在 sudo 提示后 Broken pipe | 1 | 未执行变更；改用短只读脚本并加 SSH keepalive，状态检查成功。 |
| 2026-07-19 | 本地 BM25 限制响应出现多段相近答案和重复 AI 标记 | 1 | 路由测试本身通过；开始追踪 WebChat 原始事件和 Agent 工具步骤，先定位重复发生边界。 |
| 2026-07-19 | 本地外部搜索状态前后回答矛盾 | 1 | 路由均正确；定位为缺少动态 local_config 证据，转入证据注入修复。 |

## 五问重启检查

| 问题 | 答案 |
|---|---|
| 我在哪里？ | 阶段 7 已完成。 |
| 我要去哪里？ | 当前目标已完成；可选后续是独立低成本路由模型与更广的长期观测。 |
| 目标是什么？ | 让本地技术问题可依据本地证据回复，外部事实走可信检索，取消字符串意图判定。 |
| 我学到了什么？ | 见 `findings.md` 的根因与现有能力。 |
| 我做了什么？ | 见本文件的阶段记录。 |

## 2026-07-23

### 阶段 8：号主人工接管修复

- **状态：** in_progress
- 完整读取系统化诊断、中文文件规划与 TDD 工作流。
- 只读核对本地实现、远端 NapCat 配置、最近七天事件计数及 `aiocqhttp 1.4.4` 事件分派源码。
- 用真实 NapCat payload 完成最小回放：事件名为 `message.group.normal`，旧 `message_sent.group` handler 无法触发。
- 与用户锁定：900 秒仅当前群、人工优先、明确命令可用、仅号主引用交还。
- 下一步：从普通群 self-message 端到端测试开始逐条 RED→GREEN。
- 完成普通 `message.group.normal` 自身消息入口的 RED→GREEN；删除无效的 `message_sent.group` 监听。
- 出站跟踪器现在同时消费 message_id 与对应指纹；发送异常会丢弃 pending 指纹，避免下一条同文人工消息被误吞。
- 完成接管窗口的 RED→GREEN：同群普通消息、@ Bot、群管理员普通消息均受 900 秒窗口抑制；其他群不受影响；已解析命令继续执行。
- 完成交还口令的 RED→GREEN：仅带人工标记的号主消息、且包含 Reply 组件、且正文匹配“让bot/机器人回答（这个问题）”才释放窗口。
- 完成 `ignore_bot_self_message` 兼容测试；未标记自身消息仍过滤，人工标记消息保留。
- 按 NapCat 官方源码核对 WebUI API：登录 hash、Bearer Credential、POST GetConfig、字符串化 SetConfig 及运行时网络热重载。
- 新增可审计脚本：只修改启用且名为 `astrbot` 的 WebSocket Client，自消息开关写入后重新读取验证；备份权限为 0600，不输出 WebUI token。
- 新增 `东云bot` / `东云Bot` / `东云BOT` 增量唤醒词脚本，保留原顺序、幂等并可恢复。
- 当前精确回归：48 passed；相关 Ruff 检查通过。
- 远端 SSH 正常，但 Snap Docker 套接字为 `root:root` 且无 docker 组；后续部署需要统一 sudo 窗口。只读失败均未造成修改或敏感值输出。
- 提交前完成秘密扫描：真实 `.env`、运行时配置、API Key 与私钥均未进入暂存区；`.env.example` 仅含占位符。
- 修复两个测试基础设施边界：Agent 构建测试隔离未初始化的全局 KB；`computer_use_runtime` 从主构建配置传入人格/技能阶段。`test_astr_main_agent.py` 104/104 通过。
- 逐文件通过：intent router 13、response policy 16、KB retrieval layers 3、KB resilience 5、web search 25、RAG scripts 18，以及本次 QQ 相关 30 项。
- Qdrant 的内存测试和仓库原有 DocumentStorage FTS 测试均卡在 `.venv` 的最小 `aiosqlite.connect(":memory:")`；独立 10 秒探针同样超时，确认是本地依赖环境限制，留待远端 AstrBot 容器验证。
- 已创建首个版本控制提交 `6a0d9c5 feat: add local RAG and evidence-aware routing`。
- 创建并推送第二个提交 `83f8ae1 fix: honor QQ account-owner takeover` 到 `fork/feature/local-rag-qdrant`。
- 远端先保存二进制 diff 和状态，再创建 `stash@{0}: pre-human-takeover-20260722T182817Z`；通过 4.0 MiB Git bundle 离线快进到 `83f8ae1`，避免代理问题和破坏性 reset。
- 远端源码部署前备份位于 `/home/miku/astrbot-deploy/backups/human-takeover-20260722T182817Z`；root 配置备份位于 `/home/miku/astrbot-deploy/backups/human-takeover-runtime-20260722T182933Z`，权限 0600/0700。
- AstrBot Dashboard API 已增量加入 `东云bot`、`东云Bot`、`东云BOT`；NapCat WebUI API 已把启用的 `astrbot` WebSocket Client 更新为 `reportSelfMessage=true` 并二次读取验证。
- 只重启 AstrBot；NapCat、Qdrant、Embedding 均保持原运行时长，QQ 登录容器未重启。AstrBot 重新启动并连接 OneBot 适配器，启动错误计数为 0。
- 远端容器内回归：Qdrant 4/4、QQ 接管 30/30 通过；远端 Git HEAD 为 `83f8ae1` 且工作树 clean。
- 剩余验收仅是用户侧真实 QQ 烟测：号主先发普通消息、同群成员 @ Bot 应不回复；号主引用该问题发送“让bot回答这个问题”后应回复；其他群不应受影响。

## 会话：2026-07-24

### 阶段 11：外置 Agent Gateway

- **状态：** in_progress
- 用户批准实施 AstrBot 网关化方案；现网暂不热修，先旁路建设和测试。
- 重新确认本地 `feature/local-rag-qdrant` 与 `astrbot-plugin-admin-switch` 工作树干净。
- 完整读取项目 `AGENTS.md`、中文文件规划技能和 TDD 工作流。
- 接口与优先行为已由上一轮计划锁定；下一步按纵向切片先实现事件 API 的失败测试。
- 只读确认现有 Compose 的 Embedding `--max-client-batch-size` 为 64，和生产 118 条单批失败完全吻合。
- 现有管理员插件仍直接读写 AstrBot provider 与 `active_reply`，后续改为 Gateway 管理客户端。
- 本机 npm registry 经现有代理只返回 PING 起始信息、未取得包元数据；没有创建文件或改变依赖。下一步改用官方 Git 仓库核对 API，不重复相同 npm 请求。
- 经沙箱外 npm 网络安装 151 个锁定依赖，审计结果 0 vulnerabilities；未运行依赖生命周期脚本。
- RED→GREEN：完成 `/v1/events` Bearer 鉴权、版本化 `reply/no_reply` 决策和 UUID trace。
- RED→GREEN：同一 Bot 账号与 `message_id` 的重复/并发投递复用首个结果，Agent 只执行一次。
- RED→GREEN：Agent 异常返回脱敏 `gateway_error/no_reply`，不触发 AstrBot 旧链路。
- 当前 Gateway 测试与 TypeScript strict typecheck 均通过。
- Pi 官方 Faux Provider 工具回环通过：模型发起 `rag_search`、工具返回证据、模型完成第二轮回答；模型可在不重启 Gateway 的情况下热切换。
- RED→GREEN：自动 RAG 固定先于 LLM 执行，达到阈值的片段带来源注入；`rag_search` 始终作为深挖工具存在。
- RED→GREEN：Exa 客户端支持普通网页与显式 `x.com` 域名过滤，`web_search` 已加入 Pi 工具集合。
- RED→GREEN：SQLite WAL 保存事件决策，进程重启后重复 OneBot 事件仍只产生一次 Agent 调用。
- RED→GREEN：环境配置强制校验事件/管理/Qdrant/Embedding/Exa/LLM 密钥，并锁定 32 批次、16K 上下文和 90 秒超时默认值。
- 当前共 6 个 Node 测试文件通过，TypeScript strict typecheck 通过。
- Agent Gateway 镜像在显式宿主代理下成功构建；npm production install 0 vulnerabilities。
- QQ 插件管理员私聊接管测试通过，Python Ruff 通过。
- `migrate_agent_rag_v1.py` 已完成 canonical payload 的 RED→GREEN，并验证 Qdrant Python 模型可接受 1024 维 dense + BM25 Document。
- 完整本地门禁：Node 6/6 文件通过、Python 20/20 通过、TypeScript/Ruff/Compose/diff-check 通过；秘密扫描仅发现示例占位符。
- 提交 `c077677` 已推送 fork，并以 47KB Git bundle 将远端干净工作树快进到同一提交。
- 远端安全生成未跟踪 `agent-gateway/.env`，复用现有 Qdrant/Embedding/Exa/DeepSeek 凭据；事件与管理 token 为独立随机值，Gateway 保持 disabled。
- 远端 Docker Hub 拉取 Node 基础镜像超时；改为离线传输本机已验证的 125MB 镜像，成功启动旁路 Gateway。
- 新鲜备份位于 `/mnt/PM983/astrbot-rag/snapshots/astrbot-rag-20260724T153857Z`。
- `agent_rag_v1` 实际迁移 11282 点，Gateway `/healthz` 与 `/readyz` 均通过。
- 真实旁路 E2E 正确回答 9470C、52C/104T、64GB HBM2e；发现未显示来源，已用 RED→GREEN 强制自动证据回答附本地来源。

### 阶段 8：真实 QQ 抢话失败重新诊断
- **状态：** in_progress
- 用户报告 Bot 仍会抢话题，重新打开已部署的人工接管阶段。
- 不假设旧测试代表生产正确；下一步读取真实入口元数据、状态窗口与唤醒阶段，先复现再修。
- 已读取 48 小时脱敏日志：四种 human_takeover 事件计数均为 0，证明生产没有识别到号主人工消息。
- 已排除 `unique_session` 键分裂；发现两份 NapCat 协议配置的 `reportSelfMessage` 值冲突，继续核对运行态来源。
- WebUI 运行态确认活动客户端 `reportSelfMessage=true`；官方 payload 仍是普通群消息。继续检查 NapCat 本地日志边界，区分“QQ 同步未进入 NapCat”和“NapCat 未上报 WS”。
- NapCat 7 天脱敏统计仍无当前登录账号群消息，确认跨设备人工发言事件不可依赖；转入 TDD，实现 `last_sent_time` 与 Bot 成功出站时间对账的兼容路径。
- RED→GREEN：群上下文现在可消费平台活动快照；当账号最近发言晚于 Bot 自身发送时，在 LLM 前启动当前群人工窗口并抑制回复。
- 补齐生产兼容边界：无 Bot 基线的首次观测不静音，旧于 Bot 的活动不静音，OneBot 探测失败时 fail-open，Bot 成功发送后立即作废该群的 5 秒活动缓存。
- 抢话题相关精确回归：26 passed（与 wiring / waking 矩阵合并前）。

### 阶段 9：知识库路由与延迟修复
- **状态：** completed
- 完成只读生产诊断：知识库先于意图路由执行；三个大库被会话静态绑定；最慢请求约 5.6 万输入 tokens / 25.8 秒。
- 用户确认：BGE-M3 本地向量选库、16K 输入预算、暂不部署 reranker，并把本地意图拆为运行时与本地知识两类。
- 现有相关测试基线：135 passed。
- RED→GREEN：结构化路由由四类拆为 `local_runtime`、`local_knowledge`、`technical_concept`、`external_fact`、`chat_creative` 五类；助手身份仍属于闲聊。
- RED→GREEN：主流程调整为先路由再检索；仅本地知识和技术概念允许进入知识库选择，运行态、外部事实与闲聊完全跳过知识库。
- RED→GREEN：新增 BGE-M3 多原型选库，原型来自知识库名称、描述和归一化文档标题；只接收会话授权库，阈值 0.52，最多两库，原型向量缓存。
- RED→GREEN：选库失败或低于阈值时返回空集合，不回退到全库；命中后最终最多注入三个片段，agentic 工具复用相同选择边界。
- RED→GREEN：上下文管理器由一次 halving 改为循环截断到严格预算或无法继续；12 万估算 token 的合成历史已压到 16384 以下并保留 system/current prompt。
- 路由与选库日志只记录路由、数量和耗时，不记录聊天正文。
- 联合精确矩阵 254/254 通过；Ruff、compileall、`git diff --check` 通过。
- 扩大到全部 unit 的运行在约 24% 后再次停滞，无失败标记；与已记录的本机 `aiosqlite` 挂起一致，手动终止，部署后改由远端容器跑相关持久化回归。
- 创建并上传 34KB 增量 Git bundle；远端工作树从 `83f8ae1` 快进到 `9d07922`，工作树保持 clean。
- 部署前 Qdrant/SQLite 快照：`/mnt/PM983/astrbot-rag/snapshots/astrbot-rag-20260724T085213Z`；源码 bundle 与 0600 配置备份位于 `/home/miku/astrbot-deploy/backups/routing-takeover-20260724T085500Z`。
- `deepseek_chat.max_context_tokens` 从未设置改为 16384，并二次读取确认；只重启 AstrBot，NapCat、Qdrant、Embedding 均保持 7 天运行时长。
- 远端容器联合矩阵 253 项通过；唯一失败为容器固定 CST 与旧测试硬编码 UTC 的环境断言，不涉及本次功能。
- 真实本地 BGE-M3 API 返回 1024 维；选库烟测把 9470C/HBM 路由到 AI Infra，相似度 0.8214。
- AstrBot 重启后为 running、restart_count=0，三分钟启动日志 ERROR/Traceback/Exception 计数为 0。

## 错误日志

| 时间戳 | 错误 | 尝试次数 | 解决方案 |
|---|---|---:|---|
| 2026-07-24 | 首个跨设备测试直接调用尚不存在的追踪器方法，失败发生在测试接线而非行为 | 1 | 改为模拟平台活动快照公共边界，再重新确认 RED→GREEN |
| 2026-07-24 | NapCat 版本筛选命令意外输出无关群聊正文 | 1 | 不保存正文；后续日志仅在进程内输出计数和时间戳 |
| 2026-07-24 | 远端 `backup.sh` 的 Compose 视图误报 AstrBot 未运行 | 1 | 未停止服务；直接在运行中 AstrBot 容器调用同一个 `backup_state.py`，快照成功 |
| 2026-07-24 | 远端测试误用 `uv --no-sync`，创建空 `.venv` 且缺少 pytest | 1 | 未运行测试；立即删除该临时目录，改用容器已有 `python -m pytest` |
| 2026-07-24 | 未携带鉴权的 embedding curl 返回 401 | 1 | 证明服务启用鉴权；随后从配置进程内读取密钥，只输出 1024 维结果，未输出密钥 |
| 2026-07-24 | 远端联合测试的 UTC 断言在 CST 容器中失败 | 1 | 其余 253 项通过；记录为既有环境依赖，不为本次功能修改时区逻辑 |
| 2026-07-24 | npm registry 通过本机代理未返回 Pi 包元数据 | 2 | 未修改依赖；改从官方 Git 仓库读取源码与 README，安装阶段再使用可工作的代理。 |
| 2026-07-24 | 首次组合检查在仓库根执行 npm，且 Compose 默认真实 `.env` 不存在 | 1 | 无代码或服务变更；改在 `agent-gateway` 执行 npm，并让 Compose 的 env 文件路径可由示例配置覆盖。 |
| 2026-07-24 | Gateway 镜像首次构建在容器内 `npm ci` 卡住 | 1 | 手动终止，未启动服务；为构建阶段显式使用 host network 和 `RAG_BUILD_PROXY`，并增加 `.dockerignore`。 |
| 2026-07-24 | 首次增量 bundle 使用裸提交区间，被 Git 判定为空 | 1 | 改用命名分支 ref 加排除基线，生成 47KB 可验证 bundle。 |
| 2026-07-24 | 远端普通用户无法创建 PM983 Gateway 目录 | 1 | 使用已授权 sudo 创建并归属 UID 1000，未改变其他目录。 |
| 2026-07-24 | 远端 Docker Hub token 请求超时 | 1 | 不重复远端拉取；离线传输本机已验证的 125MB 镜像并成功加载。 |
| 2026-07-24 | 通用 backup.sh 使用错误 Compose 视图误报 AstrBot 未运行 | 1 | 未停止服务；直接在运行中的 AstrBot 容器执行同一 backup_state.py，快照成功。 |
| 2026-07-24 | 真实 RAG 证据脚注显示 `unknown` | 1 | 确认向量 payload 只保存 `kb_doc_id`；迁移器改为只读查询 AstrBot `kb.db` 并幂等回填文档名。 |
| 2026-07-24 | 在仓库根目录运行 Gateway `npm` 检查 | 1 | Python/Ruff 已通过；Node 任务改到 `agent-gateway/` 目录单独执行，不再重复根目录命令。 |
| 2026-07-24 | Git 提交被平台审批额度拦截 | 1 | 未绕过审批；已测修复保留在工作树，继续本地可逆实现，等用户新授权后统一提交/同步。 |
| 2026-07-24 | 本机不存在远端绝对路径的 AstrBot Compose 基底 | 1 | Gateway Compose 直接通过；AstrBot override 用最小临时基底验证后通过，临时文件已删除。 |
| 2026-07-25 | 首次读取 TDD 技能时少了 `ok-skills/` 路径层级 | 1 | 未改代码；按技能目录映射改读 `/home/miku/.agents/skills/ok-skills/tdd/SKILL.md` 并完整读取。 |
| 2026-07-25 | Top-16 工具测试首版无法区分自动检索与工具检索 | 1 | 实现已使两者都为 16；测试改为用公开调用次序区分两次检索，然后确认默认深度和 6000 字符上限均转绿。 |
| 2026-07-25 | 最终 Gateway 镜像首次构建停在未配代理的 `npm ci`，未产出标签 | 1 | 未进行同命令重试；改用项目已验证的 host network + `127.0.0.1:18081` 构建代理路径。 |
| 2026-07-25 | 受限本机 sandbox 不允许 `ss` 读取 netlink | 1 | 未改系统；不以该诊断判定代理，直接使用已验证构建代理参数并以构建结果为准。 |
| 2026-07-25 | canary 无持久卷时不能写默认 `/data/gateway.sqlite3` | 1 | 这只影响临时启动命令；改用 `GATEWAY_DB_PATH=/tmp/gateway.sqlite3`，正式 Compose 仍使用已归属 node 用户的 PM983 数据卷。 |
| 2026-07-25 | 首次 SQLite 诊断误查不存在的 `reason_code` 列，紧接的 JSON SQL 命令又有 shell 引号错误 | 2 | 未改数据；按真实 schema 只读取 `response_json`，在 Node 内解析并只输出 `reason_code`。 |
| 2026-07-25 | 插件精确回归命令引用了不存在的 `test_agent_gateway_client.py` | 1 | pytest 未执行任何测试；先用 `rg --files` 确认可用文件，再运行真实插件测试 4/4 与 Ruff。 |
| 2026-07-25 | 首次正式切流时插件元数据作者被 YAML 解析为整数 | 1 | 插件仍加载但产生校验警告；RED 测试复现后给纯数字作者加引号，GREEN 4/4，重新仅重建 AstrBot 后警告归零。 |
| 2026-07-25 | 首次隔离意图探针把 completion 上限设为 128，推理模型返回空 `content` | 1 | 不重复原参数；改为 512 并记录 finish/usage，得到 `chat_creative/0.95`，其中 194 tokens 被 reasoning 消耗。 |
| 2026-07-25 | 本机普通用户首次构建修复镜像无法访问 Docker socket | 1 | 未构建；使用已授权的限定 `docker build` 权限继续。 |
| 2026-07-25 | 修复镜像的联网 `npm ci` 在 70 秒后触发 npm CLI `Exit handler never called` | 1 | 未产出镜像且不重复相同下载；依赖锁文件未变，改以已验证 `7995b30` 镜像为基础只覆盖源码，离线构建。 |
| 2026-07-25 | 构建 PTY 首次 yield 后过早检查镜像标签，镜像尚不存在 | 1 | 后续先轮询原构建会话至明确退出，再检查镜像。 |
| 2026-07-25 | 首轮远端 canary 将“我的服务器 CPU”当作 `local_runtime`，未召回 9470C | 1 | 正式服务未替换；补硬件清单→`local_knowledge` 语义边界，并让 `local_runtime` 保留按需 RAG 工具但不自动注入。 |
| 2026-07-25 | 修改 local_runtime 断言时首次命中同文件更早的闲聊断言，随后测试命令又在仓库根误用相对路径 | 2 | 未改生产；按测试名定位两处断言并恢复闲聊无工具、runtime 仅 RAG，后续固定在 `agent-gateway/` 运行 Node 测试。 |
| 2026-07-25 | 远端 Snap Docker/BuildKit 无法从 `/tmp` 读取增量 Dockerfile | 1 | 未构建镜像；改把同一 144 字节文件放到用户 home 下的部署临时目录，不重复 `/tmp` 路径。 |

## 2026-07-24：Gateway 管理面与会话记忆

- RED→GREEN：新增独立管理鉴权的 `/v1/admin/config`，模型与群白名单原子更新并持久化到 SQLite。
- RED→GREEN：群白名单在 RAG/LLM 前拒绝；QQ 管理员私聊支持状态、模型、白名单添加/删除命令。
- RED→GREEN：无效事件 payload 返回 400，不调用 Agent。
- RED→GREEN：新增按 UMO 持久化的会话记忆；超预算时将旧交换滚入有界摘要，保留最近对话，同一 UMO 串行处理。
- Gateway 7 个 Node 测试文件和 TypeScript strict typecheck 通过；QQ 管理命令 3 项 Python 测试与 Ruff 通过。
- RED→GREEN：当前用户消息超出输入预算时保留首尾并显式标记截断；最终 Agent prompt 硬限不超过预算。
- RED→GREEN：新增 31 条历史检索验收器，请求结构与 Gateway 的 BGE-M3 + dense/BM25/RRF 完全一致，输出不包含召回正文。
- 完整本地门禁：Node 7 个测试文件全过，TypeScript strict 通过，Python 25/25 通过，Ruff、两份 Compose 视图、diff-check 和秘密扫描通过。

## 2026-07-25：提交、远端回归与切换

- 用户确认平台额度已恢复，授权继续提交与后续部署。
- 提交前状态复核：当前分支 `feature/local-rag-qdrant`，基线 `0e310fe`，工作树只包含计划内 Gateway/RAG/插件/文档与测试更改。
- 提交 `6e3648f` 已创建并推送至 `fork/feature/local-rag-qdrant`，推送后本地工作树干净。
- 远端同步前确认代码位于 `0e310fe` 且工作树干净；AstrBot、NapCat、Embedding、Qdrant 与旧 Gateway 均运行。
- 远端空间：系统盘可用 152GB，PM983 可用 527GB。
- 新建部署前备份 `/home/miku/astrbot-deploy/backups/agent-gateway-20260724T165557Z`，包含源码 bundle、0600 配置和停止旧 Gateway 后一致复制的 SQLite 文件；Gateway 随后已恢复运行。
- 新建 AstrBot/SQLite/Qdrant 快照 `/mnt/PM983/astrbot-rag/snapshots/astrbot-rag-20260724T165725Z`。
- 远端通过 20KB 增量 bundle 从 `0e310fe` 快进到 `6e3648f`，快进前无本地改动。
- 从 AstrBot 运行配置自动导入 5 个现有群白名单，并将 Gateway 管理 token 只在未跟踪 env 中连接；未输出 token。
- 幂等重跑 `agent_rag_v1` 迁移完成：处理 11282 点，集合总数不变，旧集合未删除。
- 首次 31 条真实混合检索验收（Top-8）为 26/31；5 条失败均已命中预期文档，但预期术语分散在未进入 Top-8 的其他切片。暂不切换 QQ，继续测试 Top-12/16 与分组召回策略。
- 同一验收在 Top-12 为 30/31，Top-16 为 31/31。决定将生产自动候选提升到 16，但保持现有 16K 硬 prompt 预算，并限制手动 `rag_search` 输出，避免候选增加变成 token 无界增长。
- Top-16 生产对齐修复已以 `7995b30` 提交并推送，远端通过 3.5KB bundle 快进；远端使用新默认值复跑仍为 31/31。
- 最终镜像以 host network + 构建代理成功产出：131MB，压缩后 125MB，SHA-256 `0383cb16545bb36825af74c2b0ba8a1f8fae3599854e1500f29fc6dca57131c0`；远端校验一致并完成 `docker load`。
- canary 首次因无数据卷且默认 DB 路径为 `/data` 而立即退出；改用临时 `/tmp/gateway.sqlite3` 后 `/readyz`=200。
- canary 直连网络已分层验证：DeepSeek 鉴权模型列表 146ms/200，1-token chat 669ms/200；首个完整 Gateway 请求在客户端中断后仍完成为 `agent_reply`。
- 正式 Gateway 已强制重建为 `7995b30` 镜像，健康/就绪均通过；正式数据卷身份与 CPU E2E 分别约 1.0s/1.3s，来源非 unknown，AI 标记正确。
- 管理 API 的未授权/读取/无操作持久化状态分别为 401/200/200；SQLite 已保存 `deepseek-v4-pro` 与 5 个群白名单。
- Qdrant `agent_rag_v1` 为 11282 点、unknown 来源为 0；白名单外群 33ms fail-closed，未进入模型。
- 已将未跟踪回滚开关 `AGENT_GATEWAY_ENABLED=true`，只重建 AstrBot；NapCat、Gateway、Qdrant、Embedding 全部 running、restart_count=0。
- 插件作者元数据完成 RED→GREEN 修复并再次只重建 AstrBot；插件加载成功，三分钟 ERROR/Traceback/Exception/元数据校验失败计数为 0。
- 阶段 11 的远端部署与一次性切流已完成；尚需用户从真实 QQ 发送一条管理员私聊和一个白名单群唤醒作为最终传输层烟测。

## 2026-07-25：763898834 群意图错误诊断

- 用户报告该群出现明显意图识别错误；按系统化诊断流程先收集入口、决策、RAG、工具与回复边界证据，不直接修改代码。
- 隐私边界：只读取该群近期必要事件，审计文档不保存群聊正文、QQ 昵称或凭据。
- 只读 SQLite 定位到该群两轮近期餐饮闲聊；Gateway 均正常回复，但错误声称本地知识库没有资料。
- 源码回溯确认 Gateway 没有意图分类阶段：所有事件无条件 Top-16 RAG，系统提示统一声明已做本地检索。
- 真实召回复现：两个闲聊查询的 Top-1 无关片段均为 0.5，且阈值只有 0.03；正常 CPU 查询正确结果为 0.7/0.5208，证明 RRF 分数不是可直接阈值化的语义置信度。
- 隔离分类探针把同类请求正确判为 `chat_creative/0.95`，确认模型能力正常、故障在 Gateway 编排。
- 未修改生产服务或配置；等待用户确认修复范围后进入 TDD。
- 用户明确授权修复。RED→GREEN：粤语餐饮闲聊现在先经隔离语义路由，`chat_creative` 不调用 RAG、不暴露搜索工具，也不再收到“已经查询知识库”的系统提示。
- RED→GREEN：路由非法输出/异常进入 `isFallback=true`，不自动注入 RAG，但同时保留 `rag_search` 与 `web_search`，避免分类器重新成为知识库硬门。
- RED→GREEN：`external_fact` 跳过本地 RAG且只开放网页搜索；`local_runtime` 不把持久化文档伪装成实时状态；`local_knowledge`/`technical_concept` 才自动执行混合检索。
- 路由器只接收当前不可信消息、无对话历史、无工具，严格验证五类 JSON；支持模型在 Markdown 代码块中返回唯一 JSON 对象。
- 增加独立路由模型、30 秒超时和 512 输出 token 配置；真实 128 token 探针曾被 reasoning 完全耗尽，因此示例配置不允许更小默认值。
- 本地完整 Gateway 门禁：8 个 Node 测试文件通过，TypeScript strict 与 `git diff --check` 通过。
- 提交 `eea5211` 完成初版路由并推送；首轮 canary 餐饮路径正确，但发现 CPU 硬件边界回归，正式服务未切换。
- RED→GREEN 修复硬件边界后提交 `3db6502` 并推送；第二版 canary：餐饮 2.06 秒无 RAG 痕迹，CPU 2.04 秒命中 9470C/有效来源，外部事实 20.38 秒含 URL 且无本地来源。
- 部署前停止旧 Gateway 做一致 SQLite 备份，路径为 `/home/miku/astrbot-deploy/backups/agent-intentfix-20260725T082155Z`；旧镜像标签为 `astrbot-rag-agent-gateway:pre-intentfix-20260725T082155Z`。
- 正式 Gateway 已切换到 `3db6502` 镜像；正式餐饮/CPU E2E 分别约 2.09 秒和 2.52 秒，所有断言通过。
- 仅 Gateway 被重建；AstrBot、NapCat、Qdrant、Embedding 启动时间保持不变，五个容器均 running/restart_count=0，Gateway 近十分钟错误计数为 0。
- 管理 SQLite 仍为 `deepseek-v4-pro` 与 5 个群白名单；远端源码 HEAD `3db6502`、工作树 clean。

## 2026-07-26：管理员私聊循环与引用语境修复

- **状态：** in_progress
- 用户批准按既定方案修复、提交推送并灰度部署。
- 只读生产证据确认管理员私聊存在出站空消息回流；最近一轮出现分钟级连续回复和被空 user 污染的会话状态。
- 只读代码确认插件未拒绝空私聊，Gateway 事件校验允许空文本，aiocqhttp 出站追踪仅在自身群消息转换路径消费。
- 只读群时间线确认目标短问句携带有效 Reply 正文，但插件只传引用发送者 ID；路由器也明确不接收历史或引用上下文。
- 实施前基线：插件目标测试 4/4、Gateway 8/8、TypeScript strict typecheck 通过；本地与远端均位于 `c4b574d` 且工作树 clean。
- RED→GREEN：插件现于任何管理命令/Gateway 调用前终止空白好友消息；目标测试确认客户端调用为 0。
- RED→GREEN：Gateway 事件校验要求 `text.trim()` 非空；空事件返回 400，路由/RAG/LLM 调用为 0。
- Node `--test` 的子进程汇总未显示断言详情，改为直接运行目标测试文件取得 `200 != 400` 的 RED 证据；未重复无信息命令。
- RED→GREEN：aiocqhttp 对所有消息先消费精确出站 message_id；私聊不会使用 pending 文本指纹，用户复述同文本仍正常进入。
- RED→GREEN：插件从 Reply 组件提取正文并限制为 2000 字符；Gateway 对结构化 `reply_context` 做运行时校验，超限事件在 Agent 前返回 400。
- RED→GREEN：Gateway 在分类前读取近期记忆尾部 1200 字符；引用正文优先，随后是近期记忆和当前消息，全部放在独立不可信标签中。
- RED→GREEN：引用正文同时进入自动 RAG 查询与最终问题块；技术路由明确禁止用“知识库没有资料”代替分析。
- RED→GREEN：生产将输出无正文的 `gateway_route` / `gateway_tool` JSON 审计，包含会话哈希、路由、置信度、引用标志、命中数和耗时。
- 一次 Node 目标测试仍在仓库根运行导致找不到 `test/gateway-agent.test.mjs`；未执行代码，立即固定到 `agent-gateway/` 后通过。
- 首轮联合门禁的 23 个 Python 测试、8 个 Node 测试文件和 typecheck 均通过；Ruff 仅报告新增测试 import 分组，按提示做最小空行修正后重新严格执行。
- 第二次 Ruff 显示两个项目内 `astrbot*` import 应属于同一分组；移除两者间空行，不再猜测分组规则。
- diff 审计发现小窗口下长引用可能突破主提示硬预算；新增失败测试后改为“当前问题优先、引用使用剩余预算”，100 字符预算回归通过。
- 最终扩大门禁：Python 52/52、Ruff、`git diff --check`、Gateway 8/8 测试文件与 TypeScript strict typecheck 全部通过；群人工接管测试包含在内。
- 新增 `gateway_reply` 总耗时审计，可把分类/RAG、工具和整轮模型延迟分开定位；仍只保存会话哈希和枚举字段。
- 一次提交前秘密扫描命令因 shell 引号未闭合而未执行；改用无嵌套引号的差异扫描，只有测试占位 Bearer token，无真实密钥。
- 首次 `git add` 因 worktree 元数据位于只读 `/srv/storage` 无法创建 `index.lock`，未暂存或提交；改用用户已授权的限定 Git 写权限继续。

### 灰度部署与三轮 canary

- 本地门禁通过：Gateway 8/8 测试文件、TypeScript strict typecheck、52 条 Python 精确回归、Ruff 与 diff-check 均成功。
- 修复分三次逻辑提交推送到 feature 分支：私聊回环/引用上下文、引用技术追问路由、技术问题 RAG 隔离；远端工作树最终快进到 `e586ca4` 且 clean。
- 部署前备份源码 bundle、AstrBot 配置、Gateway 环境文件与 SQLite；旧 Gateway 镜像保留回滚标签。
- 仅停止 Gateway 完成 SQLite 一致性处理：管理员会话 24 个交换中删除 19 个空 user 回环，保留 5 个非空交换；其他会话、事件与知识库未删除。
- 仅重载 AstrBot、灰度替换 Gateway；NapCat、Qdrant、Embedding 未重启且 restart count 均为 0。
- 第一轮 canary 验证空事件为 400、引用回答相关，但审计 route 仍为 `chat_creative`，因此未判通过。
- 第二轮 route 已为 `technical_concept`，但自动注入 16 条 RAG 证据并出现无关内容，因此再次未判通过。
- 第三轮通过：空事件 400；引用事件 200/reply；route=`technical_concept`、automatic_rag_hits=0；模型按需调用 RAG 与 Web，最终无无关知识库内容。
- Gateway `/healthz`、`/readyz` 均正常；AstrBot 插件重新加载且启动日志无错误。最终仍等待用户侧真实 QQ 私聊与群引用烟测。

## 2026-07-27：Gateway 会话清空命令

- **状态：** in_progress
- 用户报告 `/new` 无法清空当前 AstrBot 会话。
- 完整追踪确认 `/new` 被切流插件作为普通消息发往 Gateway，AstrBot 内置命令未执行；Gateway SQLite 又没有 reset API。
- 目标行为锁定为：Gateway 白名单群中的任意成员可使用 `/new`、`/reset`、`/stop`、`/stats`；私聊仍只允许管理员。命令不调用路由、RAG、Web 或 LLM，并与同会话在途请求正确串行。
- 命令范围采用安全最小集：Gateway 自管 help/new/reset/stop/stats/research，sid 与管理员 name 放行 AstrBot，provider 重定向到 Gateway 管理命令，dashboard_update/set/unset 与未知斜杠命令直接拒绝。
- 用户明确要求不启用定时任务；生产数据库审计为零条任务，实施时关闭 `provider_settings.proactive_capability.add_cron_tools`。
- 首次读取系统化诊断技能少了 `ok-skills/` 路径层级；未修改项目，已按实际路径完整读取。
- RED→GREEN：新增事件 token 鉴权的 `/v1/sessions/control`，白名单群成员可控制本群 UMO，私聊非管理员和白名单外群在控制器执行前返回 403。
- RED→GREEN：Gateway 以 generation + 同 UMO 队列处理 reset/new 与在途请求竞态；先取消 Router/Pi Agent，再等待退出并清 SQLite，旧回答不会重新写回。
- RED→GREEN：SQLite 新增 `session_usage`，累计路由与主 Agent 的完整工具循环用量；reset 保留，new 清除，stats 不调用模型。
- RED→GREEN：QQ 入口按 AstrBot 已激活 handler 元数据截流 help/new/reset/stop/stats/provider/sid/name/research，并拒绝 dashboard_update/set/unset 与未知斜杠命令。
- RED→GREEN：显式 research 跳过意图分类并在主模型前实际执行 Exa；网页证据有界注入。
- RED→GREEN：新增可逆 `configure_agent_safety`，只关闭 `add_cron_tools` 并保存最小恢复状态；Gateway 本身不暴露定时任务工具。
- 本地完整门禁：Node 8 个测试文件、TypeScript strict、Python 70 项相关回归、Ruff、compileall、Compose config、diff-check 与新增 diff 秘密扫描均通过。
- 功能提交 `0f6b6b3` 已推送到 `fork/feature/local-rag-qdrant`，远端部署分支快进到同一提交且工作树干净。
- 生产部署前创建 RAG 快照 `/mnt/PM983/astrbot-rag/snapshots/astrbot-rag-20260726T192451Z`；源码、AstrBot 配置和一致性 Gateway SQLite 备份位于 `/home/miku/astrbot-deploy/backups/session-controls-20260726T192508Z`。
- 仅重建 Gateway 与 AstrBot；NapCat、Qdrant、Embedding 的启动时间保持不变。五个容器均 running、restart_count=0，Gateway health/ready 均通过，AstrBot 插件正常加载。
- 生产鉴权烟测不调用模型：白名单群 `stats` 返回 200，非管理员私聊返回 403；`session_usage` 持久表存在。AstrBot 容器插件回归 19/19 通过。
- 已应用可逆安全配置：`add_cron_tools=False`、`cron_jobs=0`，恢复状态保存在 `rag-stack/runtime/agent-safety-backup.json`。
- 常规 Gateway 构建只在拉取 Docker Hub Node 元数据时超时；因依赖锁未变化，改从已验证镜像离线覆盖本次 `src/` 并成功部署。首次 AstrBot Compose 命令缺少 env 文件而在插值阶段停止，补充 `--env-file rag-stack/.env` 后成功。

## 2026-07-29：QQ 登录态掉线诊断与 WebUI 代理

- **状态：** in_progress
- 用户确认 QQ 客户端显示该 Linux QQ 登录设备离线，要求确认缓存、是否需要重新扫码，并建议把远端 WebUI 代理到本地。
- 只读确认 NapCat 与 QQ 进程均运行、容器重启次数为零；NapCat 到 AstrBot 的 OneBot TCP 连接为 established。
- QQ 配置目录约 1.8GB并持续有新写入，说明持久缓存存在；未复制或下载该目录。
- 通过 NapCat WebUI 鉴权接口只读取脱敏状态：NapCat 自报已登录、无二维码、无登录错误。该状态与用户侧设备离线冲突，当前按上游会话陈旧处理，不把它误判为 AstrBot/Gateway 故障。
- SSH 本地转发被服务端策略拒绝；失败隧道不再重试。下一步改用仅绑定 Tailscale 地址的临时 TCP 代理。
- QQLogin 动作接口首次按 GET 访问返回 404，未产生状态变更；按实际 POST 契约重试后确认有 1 个与当前账号匹配的可快速登录缓存。
- 首个第二 SSH 会话未分配本地 PTY，不能保持代理前台进程；未修改远端。重新以 PTY 建连后代理启动成功。
- 临时代理仅监听远端 Tailscale 地址的 16099 端口，转发到本机回环的 NapCat WebUI；本机访问得到 301 并正确跳转 `/webui`。
- 一次宽泛 NapCat 日志筛选带出无关消息内容；没有保存到规划文件，后续只查询聚合状态与计数。
- 按最小恢复路径仅重启 NapCat；AstrBot、Gateway 与 Qdrant 保持原运行时长。
- NapCat 重启后旧 WebUI Bearer 正常失效；重新内部鉴权后确认 `is_login=false`、快速登录缓存仍为 1 项，错误为二维码已过期。
- 经代理下载完整 WebUI JS 首次超时；改在远端容器内只检索 QQ 管理静态资源，确认二维码刷新与读取接口契约。
- 已调用官方接口刷新二维码；临时登录 URL仅经 SSH 复制到本机 `/tmp`，使用本机离线二维码库生成 450×450 PNG，没有交给第三方服务。
- 用户成功登录 WebUI 后，QQ 状态同步恢复为 `is_login=true`、`online=true`，无二维码和登录错误；NapCat 内存在已建立 TCP 连接。
- 尚需用户在真实白名单群发送一条唤醒消息，验证消息进入与 Bot 回复后关闭临时代理并完成阶段。
# 2026-07-29：AstrBot 可验证部署与掉线恢复工作流

- 用户批准实施完整计划，并锁定 Coogen“E3 后公开 + 无密钥夹具/真实远端双层验证”。
- 已恢复规划文件、检查工作树与仓库指令；保留既有未提交规划文档和 `AGENT_HANDOFF.md`。
- 已审计健康检查、启动、备份、恢复、Compose 与 NapCat WebUI 鉴权代码；开始按纵向 TDD 切片实现统一验证 CLI。
