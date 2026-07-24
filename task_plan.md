# 任务计划：AstrBot 结构化意图路由与本地证据回复

## 目标

把当前基于字符串启发式的“事实问题一律要求 Exa 来源”替换为：LLM 结构化意图分类、非递归 Lorebook 本地证据注入，以及按路由区分本地知识、外部事实和普通聊天的回复策略；修复 BM25 / RAG 问题被静默吞掉的问题。

## 当前阶段

阶段 11：把 AstrBot 降级为 QQ 网关，旁路实现独立 Agent Gateway 与混合 RAG

## 各阶段

### 阶段 1：根因审计与接口确认

- [x] 复现并追踪“BM25 问题无回复”的主调用路径
- [x] 确认当前知识库实现包含稠密检索、BM25 稀疏检索与 RRF 融合
- [x] 确认静默发生在最终回复策略，而不是 Qdrant / BGE-M3 / 知识库检索
- [x] 确认现有 Provider 调用、配置和持久化数据路径
- **状态：** complete

### 阶段 2：设计并记录路由契约

- [x] 定义四类结构化意图：local_system、technical_concept、external_fact、chat_creative
- [x] 定义 LLM 分类失败时的保守降级行为、超时与日志边界
- [x] 定义 Lorebook 文件格式、2–4 条上限和约 600–1000 token 证据预算
- [x] 明确本地证据与外部可信来源的不同标记和最终回复边界
- **状态：** complete

### 阶段 3：测试驱动实现

- [x] 先写 LLM JSON 路由的失败测试，再实现最小路由器
- [x] 先写 Lorebook 非递归激活的失败测试，再实现最小加载与注入
- [x] 接入主 Agent：本地/技术路由注入本地证据，外部事实路由调用 Exa
- [x] 删除字符串意图判定和最终阶段的隐式重判定
- **状态：** complete

### 阶段 4：本地验证

- [x] 运行目标单元测试与相关 Agent / 回复策略测试
- [x] 运行静态检查和 diff 检查
- [x] 复核 BM25 问题、外部事实、闲聊和分类失败四条路径
- **状态：** complete

### 阶段 5：远端备份、部署与运行验证

- [x] 备份远端源码、配置与现有 Lorebook（如有）
- [x] 只重启 AstrBot；不变更 NapCat 登录状态、Qdrant 数据或 Embedding 服务
- [x] 验证容器健康、日志和已部署文件哈希
- [x] 通过临时 WebChat 会话进入真实 AstrBot 主链路（不读取既有聊天）
- [x] 修复会话实际配置未启用结构化路由的问题后，完成三路回归
- **状态：** complete

### 阶段 6：完成性审计与真实回归

- [x] 重新读取原始三层设计并逐项建立证据矩阵
- [x] 发现并用 TDD 修复 `chat_creative` 误落入外部事实 guard
- [x] 审计 `web_trusted` 来源类型、3–5 轮窗口与预算边界
- [x] 限制 Web Search 工具只对外部事实路由或显式研究命令开放
- [x] 将代码修复同步远端并验证文件哈希与服务状态
- [x] 核对并修复默认/会话级配置作用域，使真实请求启用结构化路由
- [x] 完成 BM25、外部事实、闲聊三路径真实回归
- **状态：** complete

### 阶段 7：语义边界与对抗性压力测试

- [x] 用不复用示例措辞的本地部署改写验证 `local_system`
- [x] 验证一般技术解释、深入研究、BM25/RRF 边界为 `technical_concept`
- [x] 验证改写、闲聊和分类提示注入仍为 `chat_creative`
- [x] 确认压力测试期间无 fallback、无外部搜索误触发和无真实错误日志
- [x] 诊断并修复本地 BM25 回答多段重复与重复 AI 标记
- [x] 让 `local_system` 始终获得不含密钥的实时配置证据，消除运行状态回答漂移
- **状态：** complete

### 阶段 8：号主人工接管修复

- [x] RED→GREEN：按 NapCat 真实 `message.group` 自身消息格式识别号主人工发言
- [x] RED→GREEN：可靠排除 AstrBot 自身出站消息，避免循环与指纹残留误判
- [x] RED→GREEN：当前群 900 秒人工优先，普通 @ 不回复，明确命令可执行
- [x] RED→GREEN：仅号主引用消息可用自然交还口令让 Bot 接管
- [x] RED→GREEN：`ignore_bot_self_message` 开启时仍保留已标记的号主人工消息
- [x] 增量加入 `东云bot` 大小写唤醒词，保留并可恢复原配置
- [x] 通过 NapCat WebUI API 热开启活动 WebSocket Client 的自身消息上报
- [x] 远端备份、分支快进、仅 AstrBot 重启与容器内回归
- [ ] RED→GREEN：跨设备自身消息未上报时，通过群成员最后发言时间与 Bot 出站时间对账启动接管
- [ ] 限频、首轮基线、API 异常 fail-open、Bot 自身发送不误判
- [ ] 重新复现真实 QQ 抢话：确认号主消息是否被标记、窗口是否写入、后续 @ 是否在 LLM 前被抑制
- [ ] 为真实失败路径新增回归测试并完成 RED→GREEN
- [ ] 真实 QQ 烟测：号主发言、同群 @ 抑制、引用交还、跨群隔离
- **状态：** in_progress

### 阶段 9：知识库意图路由与 16K 输入预算

- [x] RED→GREEN：在知识库检索前完成五类结构化意图判断
- [x] RED→GREEN：只在 local_knowledge / technical_concept 中使用 BGE-M3 多原型选库
- [x] RED→GREEN：0.52 阈值、最多两个知识库、最多三个片段，失败时不扩大检索
- [x] RED→GREEN：严格把主请求输入预算限制到 16384 tokens，并保持工具消息配对
- [x] 增加不记录聊天正文的阶段耗时和路由审计日志
- **状态：** completed

### 阶段 10：联合回归、远端部署与灰度

- [x] 运行目标测试、完整相关测试、静态检查和 diff 审计
- [x] 备份远端源码、配置、SQLite 与 Qdrant 快照
- [x] 仅重建/重启 AstrBot，保持 NapCat、Qdrant、Embedding 在线
- [ ] 管理员私聊和单群灰度验证路由、延迟与人工接管
- [ ] 提交并推送到 `fork/feature/local-rag-qdrant`
- **状态：** in_progress

### 阶段 11：独立 Agent Gateway 与 RAG 迁移

- [x] RED→GREEN：TypeScript Gateway 事件接口、幂等和 fail-closed 契约
- [x] RED→GREEN：Pi Agent 的 OpenAI-compatible 流式调用、工具循环、超时和模型切换
- [x] RED→GREEN：独立 Qdrant dense + BM25 + RRF 自动召回与 `rag_search` 工具
- [x] RED→GREEN：QQ 网关插件的私聊权限、人工接管和明确唤醒
- [x] 管理员私聊命令改为调用 Gateway 的模型与白名单管理接口
- [x] RED→GREEN：管理配置独立鉴权、SQLite 持久化、群白名单在 LLM/RAG 前拒绝
- [x] RED→GREEN：事件运行时校验，非法 payload 不进入 Agent
- [x] RED→GREEN：按 UMO 隔离的 SQLite 会话记忆、同会话串行化与 16K 内滚动压缩
- [x] 运行迁移脚本新建 `agent_rag_v1`，11282 点完成，旧集合保持只读
- [x] RED→GREEN：从 AstrBot `kb.db` 只读解析文档名，修复迁移后证据来源显示为 `unknown`
- [x] 完成 31 条历检索（Top-16 31/31）、负例、联网搜索、权限、重复事件和故障本地回归
- [ ] 远端旁路部署、备份、一次性切换白名单会话并验证回滚开关
- **状态：** in_progress

## 已做决策

| 决策 | 理由 |
|---|---|
| 意图由隔离的 LLM JSON 分类决定 | 用户明确拒绝以字符串匹配决定意图；可随语境处理本地部署、技术讨论与外部事实。 |
| 关键词仅用于 Lorebook 激活 | 保留低成本、可控的本地上下文补充，不将其误当作语义意图分类。 |
| 外部事实仍要求 Exa 可信来源 | 保留原有反幻觉与来源审计边界。 |
| 本地系统与技术问题使用标注的本地证据 | 避免把“当前配置是否有 BM25”错误当成需要外部网页核验的问题。 |
| 人工接管只作用于号主实际发言的当前群 | OneBot 无法可靠表示“被动在线”；按实际发言建立 900 秒活动窗口。 |
| 接管期普通 @ 由号主优先处理 | 仅明确命令或号主引用交还可以唤起 Bot。 |
| 交还权限仅号主 | 普通成员和群管理员不能绕过人工接管。 |
| 本地问题拆为 `local_runtime` 与 `local_knowledge` | 运行配置问题不得误触发知识库；本地文档问题才进入向量选库。 |
| 选库使用本地 BGE-M3 多原型相似度 | 不增加第二次 LLM 调用；名称、描述和文档标题共同降低错库概率。 |
| 主模型输入硬预算为 16384 tokens | 最近实际请求达到约 5.6 万 token 并耗时 25.8 秒。 |
| 号主接管阶段重新打开 | 用户真实 QQ 测试证明上一轮“代码完成”的结论不成立，必须重新从入口证据定位。 |
| AstrBot 只保留 QQ 网关职责 | 现有 RAG 在调用 Qdrant 前被 LLM 路由和知识库选择器双重截断，继续修改核心会扩大耦合与回归面。 |
| Agent Gateway 使用 TypeScript、Fastify 与 Pi Agent 0.82.0 | 用户已确认框架；通过内部运行时接口隔离快速变化的依赖。 |
| 自动 RAG 不受 LLM 意图路由控制 | 每个有效问题先检索，再由证据阈值决定是否注入；模型仍可调用 `rag_search` 深挖。 |
| 新建 `agent_rag_v1` 且不迁移旧聊天历史 | 用户要求新会话开始；旧 Qdrant 集合与 AstrBot 数据只读保留用于回滚。 |
| 一次性切换全部白名单会话 | 先旁路验收，切换失败时通过单一开关恢复旧路径。 |

## 已知风险与错误

| 问题 | 次数 | 处理 |
|---|---:|---|
| 旧 `is_fact_sensitive_prompt()` 将绝大多数非闲聊判为事实问题 | 1 | 本次改为 LLM 路由，彻底移除其在主路径和最终阶段的意图职责。 |
| 远端 AstrBot 运行中，直接同步源码可能影响活跃对话 | 0 | 完成本地测试后再备份；仅短暂停止/启动 AstrBot。 |
| 首次远端原子部署命令的多层 shell 引号解析失败 | 1 | 未执行配置脚本或重启；改为同步一个简单、可审计的 root 执行脚本，避免在 SSH 命令中嵌套 `grep` 与命令替换。 |
| 首次 `rsync` 发送多个文件时未保留相对目录 | 1 | 文件被写入 AstrBot 根目录而未覆盖实际模块；容器仍为旧代码。改用 `rsync -R` 保留 `astrbot/core/...` 与 `data/...` 目录，再以哈希验证后重启。 |
| `chat_creative` 未显式返回，错误落入外部事实 guard | 1 | 新增失败测试证明会调用 Exa；增加显式聊天分支后测试转绿。 |
| Lorebook 首条命中可绕过内容预算 | 1 | 新增 1001 字符首条测试后移除特殊豁免，任何条目都必须满足总预算。 |
| Web Search 工具在路由前全局挂载 | 1 | 增加路由门控并把调用顺序改为先路由、后注入工具；显式 `/research` 保留覆盖能力。 |
| 首次真实三路回归全部显示 `fallback=True` | 1 | 日志证明运行配置为“verified policy 已启用、structured router 未启用”；先审计默认与会话级配置映射，不把它误判为模型 JSON 错误。 |
| 远端没有 `docker` 用户组，`sg docker` 日志命令失败 | 1 | 改用已授权的 `sudo docker logs`，只筛选路由/分类器日志；不重复 `sg docker`。 |
| 第二次回归把“你是谁”误分为 `local_system` | 1 | 根因是路由提示把 “this bot” 与当前部署混为一类；先新增失败测试，再明确助手身份属于 `chat_creative`、本地路由必须依赖当前部署证据。 |
| 系统 `pytest` 缺少 `pytest_asyncio` | 1 | 项目依赖实际位于 `.venv`；改用 `.venv/bin/pytest`，不重复系统 pytest。 |
| 最终只读状态复合命令遇到 SSH `Broken pipe` | 1 | 命令未执行修改；改用上传的短只读脚本并启用 keepalive，成功返回状态。 |
| 本地 BM25 限制问题出现多段近似重复和多次 AI 标记 | 1 | 多 Plain 最小测试复现后折叠为单一文本组件，并归一化大小写/内联标记；容器断言与真实回归通过。 |
| “是否开启外部搜索”两次答案相反 | 1 | local_system 现始终注入不含凭据的实时配置快照；连续三次均正确回答已开启 Exa。 |
| NapCat 自身消息开关写入了错误的顶层字段 | 1 | 活动 `websocketClients[astrbot]` 仍为 false；改由官方 WebUI API更新嵌套字段。 |
| 现有实现监听不存在的 `message_sent.group` 路径 | 1 | 真实 NapCat payload 回放证明事件为 `message.group.normal`；改到普通群消息入口分类。 |
| 只读配置对比脚本发生一次 Python 引号错误 | 1 | 改用不含嵌套单引号的输出表达式后成功。 |
| 读取带 BOM 的 AstrBot JSON 首次失败 | 1 | 后续统一使用 `utf-8-sig`。 |
| 本轮首次测试误用系统 Python，缺少 `pytest_asyncio` | 1 | 改用项目 `.venv/bin/python -m pytest`，不修改依赖。 |
| 远端 Docker 套接字为 `root:root` 且不存在 `docker` 组 | 1 | 不再尝试 `sg docker`；部署窗口使用已授权 sudo，普通配置优先走热更新 API。 |
| 远端只读命令中的 `sed` 引号未闭合 | 1 | 未发生修改；移除不必要的文本替换。 |
| 远端配置读取因权限不足失败 | 1 | 不绕过权限；在统一备份部署窗口内用 sudo 读取，并限制输出为安全字段。 |
| 首个远端检查请求包含非必要 WS URL | 1 | 安全审查拒绝，未执行；后续不读取或输出 URL。 |
| 首次秘密扫描的 shell 引号未闭合，随后 `rg` 模式被当作选项 | 2 | 均未修改文件；改为只输出文件名并用 `--` 终止选项，最终未发现真实秘密。 |
| 大测试矩阵卡在未初始化的全局知识库会话存储 | 2 | 为 Agent 构建测试隔离 KB，专门 KB 测试保持原覆盖；`test_astr_main_agent.py` 104/104 通过。 |
| 本机 `.venv` 的 `aiosqlite 0.22.1` 最小内存连接也超时 | 1 | Qdrant/原有 FTS 测试均受影响；不误报为 Qdrant 代码失败，转到远端运行容器验证。 |
| worktree Git 元数据位于只读的 `/srv/storage` | 1 | 首次暂存未执行；经用户已授权的 Git 写权限成功创建逻辑提交。 |
| root 0700 备份目录无法由普通 shell 展开 `*.json` | 1 | 三个备份已成功；通配 chmod 失败后会话退出，重新进入并改用显式文件名。 |
| `sudo python3` 看不到用户级 `httpx` | 1 | 脚本在 import 前停止、配置未变；随后只继承现有用户 site-packages 路径执行成功。 |
| 首次 Compose 路径只包含 NapCat，无 AstrBot 服务 | 1 | 命令无目标且未重启任何容器；从容器标签读取真实 Compose 路径后仅重启 AstrBot。 |
| 一次延迟的未过滤日志输出包含无关群聊正文 | 1 | 不保存到审计文档；后续只输出启动行或错误计数，不再读取原始日志正文。 |

## 备注

- 规划、发现和测试结果分别写入 `task_plan.md`、`findings.md` 与 `progress.md`。
- 不在这些文件中记录 API Key、私聊文本或 QQ 登录状态。
- 阶段 8 代码与部署已完成；最终状态暂留 `in_progress`，等待用户侧真实 QQ 发言烟测。
