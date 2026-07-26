import { createHash } from "node:crypto";

import type { AgentTool } from "@earendil-works/pi-agent-core";
import { Type } from "typebox";

import type {
  GatewayDecision,
  GatewayEvent,
  SessionControlAction,
  SessionControlResponse,
} from "./app.ts";
import type { ExaSearchResult } from "./exa.ts";
import type { AgentRunInput, AgentRunResult } from "./pi-runtime.ts";
import type { RagHit } from "./rag.ts";

type RagPort = {
  search: (query: string, options: { topK: number }) => Promise<RagHit[]>;
};

type RuntimePort = {
  run: (input: AgentRunInput) => Promise<AgentRunResult>;
  abort?: (sessionId: string) => number;
};

type ExaPort = {
  search: (
    query: string,
    options: { domains?: string[]; maxResults: number },
  ) => Promise<ExaSearchResult[]>;
};

type MemoryPort = {
  context: (sessionId: string) => string;
  record: (sessionId: string, user: string, assistant: string) => void;
  clear?: (sessionId: string) => void;
};

export type SessionUsage = {
  requests: number;
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
};

export type UsagePort = {
  add: (sessionId: string, usage: AgentRunResult["usage"]) => void;
  get: (sessionId: string) => SessionUsage | undefined;
  clear: (sessionId: string) => void;
};

export type GatewayAuditEntry = {
  event:
    | "gateway_route"
    | "gateway_tool"
    | "gateway_reply"
    | "gateway_control";
  session_ref: string;
  route?: IntentRoute;
  confidence?: number;
  fallback?: boolean;
  has_reply_context?: boolean;
  automatic_rag_hits?: number;
  tool?: "rag_search" | "web_search";
  result_count?: number;
  action?: "reply" | "no_reply";
  reason_code?: string;
  control_action?: SessionControlAction;
  control_result?: "completed" | "stopped" | "idle";
  duration_ms: number;
};

type AuditPort = {
  record: (entry: GatewayAuditEntry) => void;
};

export type IntentRoute =
  | "local_runtime"
  | "local_knowledge"
  | "technical_concept"
  | "external_fact"
  | "chat_creative";

export type IntentDecision = {
  route: IntentRoute;
  confidence: number;
  isFallback: boolean;
};

export type IntentRoutingInput = {
  text: string;
  replyContext?: {
    senderId: string;
    text: string;
  };
  recentContext?: string;
};

type IntentRouterPort = {
  classify: (
    input: IntentRoutingInput,
    sessionId?: string,
  ) => Promise<IntentDecision>;
  abort?: (sessionId: string) => number;
};

type GatewayAgentOptions = {
  router: IntentRouterPort;
  rag: RagPort;
  runtime: RuntimePort;
  exa: ExaPort;
  evidenceThreshold: number;
  memory?: MemoryPort;
  usage?: UsagePort;
  audit?: AuditPort;
  maxPromptTokens?: number;
};

const SYSTEM_PROMPT = `你是东云bot。回答前已经执行了本地知识检索。
只把标为“本地证据”的内容当作本地知识，不得伪造来源。
若证据不足，可调用 rag_search 改写查询继续检索。
普通闲聊尽量不超过20个中文字符；技术内容按需要完整回答。
不要自行添加 AI 内容标记，网关会统一添加。`;

const CHAT_SYSTEM_PROMPT = `你是东云bot。自然回应普通聊天、个人意见与开放式社交互动。
不要把闲聊当作知识库问答，也不要声称查询过本地知识库。
普通闲聊尽量不超过20个中文字符。
不要自行添加 AI 内容标记，网关会统一添加。`;

const TECHNICAL_SYSTEM_PROMPT = `你是东云bot。回答技术解释、方案比较和可行性问题。
引用消息用于解析当前问题的指代；逐项覆盖用户明确提出的问题，不得悄悄缩小范围。
本地证据只是补充材料。证据不足时可基于稳定技术知识分析，或在需要现行资料时调用网页搜索。
不要仅以“本地知识库没有资料”作为答案，也不要用无关知识库条目代替对当前技术问题的分析。
不要自行添加 AI 内容标记，网关会统一添加。`;

const FALLBACK_SYSTEM_PROMPT = `你是东云bot。意图路由暂时无法给出可信结论。
不要假装已经搜索；仅在确有需要时调用本地知识或网页搜索工具。
如果问题含糊，先自然回应或请求澄清。
不要自行添加 AI 内容标记，网关会统一添加。`;

const EXTERNAL_SYSTEM_PROMPT = `你是东云bot。这个问题依赖当前外部事实。
回答事实前必须调用网页搜索，并在答案中保留可核验的来源 URL。
如果搜索失败或来源不足，明确说明尚未核验，不要用本地知识库替代当前事实。
不要自行添加 AI 内容标记，网关会统一添加。`;

const LOCAL_RUNTIME_SYSTEM_PROMPT = `你是东云bot。这个问题询问当前部署的实时状态。
本轮没有自动注入实时配置或日志；只能使用对话中已经明确提供的状态。
证据不足时直接说明无法核验，不要把历史文档或一般知识伪装成实时状态。
不要自行添加 AI 内容标记，网关会统一添加。`;

function length(text: string): number {
  return [...text].length;
}

function clipMiddle(text: string, limit: number): string {
  if (length(text) <= limit) {
    return text;
  }
  const marker = "\n[...内容已截断...]\n";
  const available = Math.max(0, limit - length(marker));
  const start = Math.ceil(available / 2);
  const end = Math.floor(available / 2);
  const points = [...text];
  return `${points.slice(0, start).join("")}${marker}${
    end ? points.slice(-end).join("") : ""
  }`;
}

function head(text: string, limit: number): string {
  return [...text].slice(0, Math.max(0, limit)).join("");
}

function tail(text: string, limit: number): string {
  const points = [...text];
  return points.slice(Math.max(0, points.length - limit)).join("");
}

export class GatewayAgent {
  readonly #router: IntentRouterPort;
  readonly #rag: RagPort;
  readonly #runtime: RuntimePort;
  readonly #exa: ExaPort;
  readonly #evidenceThreshold: number;
  readonly #memory: MemoryPort | undefined;
  readonly #usage: UsagePort | undefined;
  readonly #audit: AuditPort | undefined;
  readonly #maxPromptTokens: number;
  readonly #sessionQueues = new Map<string, Promise<void>>();
  readonly #sessionGenerations = new Map<string, number>();

  constructor(options: GatewayAgentOptions) {
    this.#router = options.router;
    this.#rag = options.rag;
    this.#runtime = options.runtime;
    this.#exa = options.exa;
    this.#evidenceThreshold = options.evidenceThreshold;
    this.#memory = options.memory;
    this.#usage = options.usage;
    this.#audit = options.audit;
    this.#maxPromptTokens = options.maxPromptTokens ?? 12288;
  }

  async handle(event: GatewayEvent): Promise<GatewayDecision> {
    const generation = this.#sessionGenerations.get(event.umo) ?? 0;
    const previous = this.#sessionQueues.get(event.umo) ?? Promise.resolve();
    const run = previous.then(
      async () => await this.#handleSerial(event, generation),
    );
    const tail = run.then(
      () => undefined,
      () => undefined,
    );
    this.#sessionQueues.set(event.umo, tail);
    try {
      return await run;
    } finally {
      if (this.#sessionQueues.get(event.umo) === tail) {
        this.#sessionQueues.delete(event.umo);
      }
    }
  }

  async control(
    sessionId: string,
    action: SessionControlAction,
  ): Promise<SessionControlResponse> {
    const startedAt = Date.now();
    const sessionRef = createHash("sha256")
      .update(sessionId)
      .digest("hex")
      .slice(0, 12);
    const recordControl = (
      result: "completed" | "stopped" | "idle",
    ): void => {
      this.#audit?.record({
        event: "gateway_control",
        session_ref: sessionRef,
        control_action: action,
        control_result: result,
        duration_ms: Date.now() - startedAt,
      });
    };
    if (action === "stats") {
      await (this.#sessionQueues.get(sessionId) ?? Promise.resolve());
      const usage = this.#usage?.get(sessionId);
      if (!usage) {
        recordControl("completed");
        return { status: "stats", message: "当前会话暂无用量记录" };
      }
      const total =
        usage.input + usage.output + usage.cacheRead + usage.cacheWrite;
      const response: SessionControlResponse = {
        status: "stats",
        message: `调用 ${usage.requests} 次；输入 ${usage.input}，缓存读取 ${usage.cacheRead}，缓存写入 ${usage.cacheWrite}，输出 ${usage.output}，总计 ${total} tokens`,
      };
      recordControl("completed");
      return response;
    }

    this.#sessionGenerations.set(
      sessionId,
      (this.#sessionGenerations.get(sessionId) ?? 0) + 1,
    );
    const stopped =
      (this.#router.abort?.(sessionId) ?? 0) +
      (this.#runtime.abort?.(sessionId) ?? 0);
    if (action === "stop") {
      const response: SessionControlResponse = {
        status: "stop",
        message: stopped > 0 ? "已停止当前任务" : "当前没有运行中的任务",
      };
      recordControl(stopped > 0 ? "stopped" : "idle");
      return response;
    }

    await (this.#sessionQueues.get(sessionId) ?? Promise.resolve());
    this.#memory?.clear?.(sessionId);
    if (action === "new") {
      this.#usage?.clear(sessionId);
    }
    const response: SessionControlResponse = {
      status: action,
      message: action === "new" ? "已开始新会话" : "会话记忆已清空",
    };
    recordControl("completed");
    return response;
  }

  async #handleSerial(
    event: GatewayEvent,
    generation: number,
  ): Promise<GatewayDecision> {
    const startedAt = Date.now();
    const sessionRef = createHash("sha256")
      .update(event.umo)
      .digest("hex")
      .slice(0, 12);
    const recordReplyAudit = (
      action: "reply" | "no_reply",
      reasonCode: string,
    ): void => {
      this.#audit?.record({
        event: "gateway_reply",
        session_ref: sessionRef,
        action,
        reason_code: reasonCode,
        duration_ms: Date.now() - startedAt,
      });
    };
    const memory = this.#memory?.context(event.umo) ?? "";
    const replyContext = event.reply_context
      ? {
          senderId: event.reply_context.sender_id,
          text: event.reply_context.text,
        }
      : undefined;
    const intent: IntentDecision = event.force_route
      ? {
          route: event.force_route,
          confidence: 1,
          isFallback: false,
        }
      : await this.#router.classify(
          {
            text: event.text,
            ...(replyContext ? { replyContext } : {}),
            ...(memory ? { recentContext: tail(memory, 1200) } : {}),
          },
          event.umo,
        );
    if ((this.#sessionGenerations.get(event.umo) ?? 0) !== generation) {
      recordReplyAudit("no_reply", "session_stopped");
      return { action: "no_reply", messages: [], reason_code: "session_stopped" };
    }
    const isCasualChat =
      intent.route === "chat_creative" && !intent.isFallback;
    const usesAutomaticRag =
      !intent.isFallback && intent.route === "local_knowledge";
    const retrievalQuery = replyContext
      ? `${replyContext.text}\n${event.text}`
      : event.text;
    const forcedWebStartedAt = Date.now();
    const forcedWebResults = event.force_route
      ? await this.#exa.search(retrievalQuery, { maxResults: 5 })
      : [];
    if (event.force_route) {
      this.#audit?.record({
        event: "gateway_tool",
        session_ref: sessionRef,
        tool: "web_search",
        result_count: forcedWebResults.length,
        duration_ms: Date.now() - forcedWebStartedAt,
      });
    }
    if ((this.#sessionGenerations.get(event.umo) ?? 0) !== generation) {
      recordReplyAudit("no_reply", "session_stopped");
      return { action: "no_reply", messages: [], reason_code: "session_stopped" };
    }
    const initialHits = usesAutomaticRag
      ? await this.#rag.search(retrievalQuery, { topK: 16 })
      : [];
    if ((this.#sessionGenerations.get(event.umo) ?? 0) !== generation) {
      recordReplyAudit("no_reply", "session_stopped");
      return { action: "no_reply", messages: [], reason_code: "session_stopped" };
    }
    const evidence = initialHits.filter(
      (hit) => hit.score >= this.#evidenceThreshold,
    );
    this.#audit?.record({
      event: "gateway_route",
      session_ref: sessionRef,
      route: intent.route,
      confidence: intent.confidence,
      fallback: intent.isFallback,
      has_reply_context: Boolean(replyContext),
      automatic_rag_hits: evidence.length,
      duration_ms: Date.now() - startedAt,
    });
    const ragParameters = Type.Object({
      query: Type.String({ minLength: 1 }),
      top_k: Type.Optional(Type.Integer({ minimum: 1, maximum: 24 })),
    });
    const ragTool: AgentTool<typeof ragParameters, { hitCount: number }> = {
      name: "rag_search",
      label: "RAG Search",
      description: "Search the local persistent knowledge base",
      parameters: ragParameters,
      execute: async (_toolCallId, params) => {
        const toolStartedAt = Date.now();
        const hits = await this.#rag.search(params.query, {
          topK: params.top_k ?? 16,
        });
        this.#audit?.record({
          event: "gateway_tool",
          session_ref: sessionRef,
          tool: "rag_search",
          result_count: hits.length,
          duration_ms: Date.now() - toolStartedAt,
        });
        const toolEvidence = hits
          .map(
            (hit, index) =>
              `[${index + 1}] ${hit.text}\n来源: ${hit.source}`,
          )
          .join("\n\n");
        return {
          content: [
            {
              type: "text",
              text: head(toolEvidence, 6000),
            },
          ],
          details: { hitCount: hits.length },
        };
      },
    };
    const webParameters = Type.Object({
      query: Type.String({ minLength: 1 }),
      domains: Type.Optional(
        Type.Array(Type.String({ minLength: 1 }), { maxItems: 8 }),
      ),
      max_results: Type.Optional(Type.Integer({ minimum: 1, maximum: 8 })),
    });
    const webTool: AgentTool<typeof webParameters, { resultCount: number }> = {
      name: "web_search",
      label: "Web Search",
      description:
        "Search current web information. Use domains=['x.com'] for X/Twitter.",
      parameters: webParameters,
      execute: async (_toolCallId, params) => {
        const toolStartedAt = Date.now();
        const results = await this.#exa.search(params.query, {
          ...(params.domains ? { domains: params.domains } : {}),
          maxResults: params.max_results ?? 5,
        });
        this.#audit?.record({
          event: "gateway_tool",
          session_ref: sessionRef,
          tool: "web_search",
          result_count: results.length,
          duration_ms: Date.now() - toolStartedAt,
        });
        return {
          content: [
            {
              type: "text",
              text: results
                .map(
                  (result, index) =>
                    `[${index + 1}] ${result.title}\n${result.url}\n${result.text}`,
                )
                .join("\n\n"),
            },
          ],
          details: { resultCount: results.length },
        };
      },
    };
    const evidenceBlock = forcedWebResults.length
      ? forcedWebResults
          .map(
            (result, index) =>
              `[网页证据 ${index + 1}] ${result.title}\n${result.url}\n${result.text}`,
          )
          .join("\n\n")
      : !usesAutomaticRag
        ? ""
        : evidence.length
          ? evidence
              .map(
                (hit, index) =>
                  `[本地证据 ${index + 1}] ${hit.text}\n来源: ${hit.source}`,
              )
              .join("\n\n")
          : "[本地证据] 未检索到达到阈值的内容。";
    const questionBudget = Math.max(1, Math.floor(this.#maxPromptTokens * 0.6));
    const userLabel = "[用户问题]\n";
    const userBudget = replyContext
      ? Math.max(length(userLabel) + 16, Math.floor(questionBudget * 0.45))
      : questionBudget;
    const userBlock = `${userLabel}${clipMiddle(
      event.text,
      Math.max(0, userBudget - length(userLabel)),
    )}`;
    const replyLabel = "[引用消息]\n";
    const replyBudget = Math.max(0, questionBudget - length(userBlock) - 2);
    const replyBlock =
      replyContext && replyBudget > length(replyLabel)
        ? `${replyLabel}${clipMiddle(
            replyContext.text,
            replyBudget - length(replyLabel),
          )}`
        : "";
    const questionBlock = [replyBlock, userBlock].filter(Boolean).join("\n\n");
    let remaining = this.#maxPromptTokens - length(questionBlock);
    const memoryCandidate = memory ? `[对话记忆]\n${memory}` : "";
    const memoryLimit = Math.min(
      Math.floor(this.#maxPromptTokens * 0.25),
      Math.max(0, remaining - 2),
    );
    const boundedMemory = memoryCandidate
      ? tail(memoryCandidate, memoryLimit)
      : "";
    remaining -= boundedMemory ? length(boundedMemory) + 2 : 0;
    const boundedEvidence = head(
      evidenceBlock,
      Math.max(0, remaining - (remaining > 2 ? 2 : 0)),
    );
    const prompt = [boundedMemory, boundedEvidence, questionBlock]
      .filter(Boolean)
      .join("\n\n");
    const tools = intent.isFallback
      ? [ragTool, webTool]
      : intent.route === "chat_creative"
        ? []
        : intent.route === "external_fact"
          ? [webTool]
          : intent.route === "technical_concept"
            ? [ragTool, webTool]
            : [ragTool];
    const baseSystemPrompt = intent.isFallback
      ? FALLBACK_SYSTEM_PROMPT
      : isCasualChat
        ? CHAT_SYSTEM_PROMPT
        : intent.route === "external_fact"
          ? EXTERNAL_SYSTEM_PROMPT
          : intent.route === "local_runtime"
            ? LOCAL_RUNTIME_SYSTEM_PROMPT
            : intent.route === "technical_concept"
              ? TECHNICAL_SYSTEM_PROMPT
              : SYSTEM_PROMPT;
    const result = await this.#runtime.run({
      sessionId: event.umo,
      systemPrompt: `${baseSystemPrompt}\n你无法创建定时任务或提醒，不得声称已经创建、安排或将在未来主动执行。`,
      prompt,
      tools,
    });
    if ((this.#sessionGenerations.get(event.umo) ?? 0) !== generation) {
      recordReplyAudit("no_reply", "session_stopped");
      return { action: "no_reply", messages: [], reason_code: "session_stopped" };
    }
    this.#usage?.add(event.umo, result.usage);
    const text = result.text
      .replace(/[（(]\s*(?:AI|ai)生成内容\s*[）)]/gu, "")
      .trim();
    if (!text) {
      recordReplyAudit("no_reply", "empty_agent_reply");
      return { action: "no_reply", messages: [], reason_code: "empty_agent_reply" };
    }
    this.#memory?.record(event.umo, event.text, text);
    const sources = [
      ...new Set(
        evidence
          .filter((hit) => boundedEvidence.includes(hit.source))
          .map((hit) => hit.source),
      ),
    ];
    const citedText =
      sources.length > 0 && !text.includes("本地来源：")
        ? `${text}\n本地来源：${sources.join("、")}`
        : text;
    recordReplyAudit("reply", "agent_reply");
    return {
      action: "reply",
      messages: [{ type: "text", text: `${citedText}\n（ai生成内容）` }],
      reason_code: "agent_reply",
    };
  }
}
