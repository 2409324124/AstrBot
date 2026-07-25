import type { AgentTool } from "@earendil-works/pi-agent-core";
import { Type } from "typebox";

import type { GatewayDecision, GatewayEvent } from "./app.ts";
import type { ExaSearchResult } from "./exa.ts";
import type { AgentRunInput, AgentRunResult } from "./pi-runtime.ts";
import type { RagHit } from "./rag.ts";

type RagPort = {
  search: (query: string, options: { topK: number }) => Promise<RagHit[]>;
};

type RuntimePort = {
  run: (input: AgentRunInput) => Promise<AgentRunResult>;
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

type IntentRouterPort = {
  classify: (text: string) => Promise<IntentDecision>;
};

type GatewayAgentOptions = {
  router: IntentRouterPort;
  rag: RagPort;
  runtime: RuntimePort;
  exa: ExaPort;
  evidenceThreshold: number;
  memory?: MemoryPort;
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
  readonly #maxPromptTokens: number;
  readonly #sessionQueues = new Map<string, Promise<void>>();

  constructor(options: GatewayAgentOptions) {
    this.#router = options.router;
    this.#rag = options.rag;
    this.#runtime = options.runtime;
    this.#exa = options.exa;
    this.#evidenceThreshold = options.evidenceThreshold;
    this.#memory = options.memory;
    this.#maxPromptTokens = options.maxPromptTokens ?? 12288;
  }

  async handle(event: GatewayEvent): Promise<GatewayDecision> {
    const previous = this.#sessionQueues.get(event.umo) ?? Promise.resolve();
    const run = previous.then(async () => await this.#handleSerial(event));
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

  async #handleSerial(event: GatewayEvent): Promise<GatewayDecision> {
    const intent = await this.#router.classify(event.text);
    const isCasualChat =
      intent.route === "chat_creative" && !intent.isFallback;
    const usesAutomaticRag =
      !intent.isFallback &&
      ["local_knowledge", "technical_concept"].includes(intent.route);
    const initialHits = usesAutomaticRag
      ? await this.#rag.search(event.text, { topK: 16 })
      : [];
    const evidence = initialHits.filter(
      (hit) => hit.score >= this.#evidenceThreshold,
    );
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
        const hits = await this.#rag.search(params.query, {
          topK: params.top_k ?? 16,
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
        const results = await this.#exa.search(params.query, {
          ...(params.domains ? { domains: params.domains } : {}),
          maxResults: params.max_results ?? 5,
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
    const evidenceBlock = !usesAutomaticRag
      ? ""
      : evidence.length
      ? evidence
          .map(
            (hit, index) =>
              `[本地证据 ${index + 1}] ${hit.text}\n来源: ${hit.source}`,
          )
          .join("\n\n")
      : "[本地证据] 未检索到达到阈值的内容。";
    const memory = this.#memory?.context(event.umo) ?? "";
    const questionLabel = "[用户问题]\n";
    const questionBudget = Math.max(
      length(questionLabel),
      Math.floor(this.#maxPromptTokens * 0.6),
    );
    const questionBlock = `${questionLabel}${clipMiddle(
      event.text,
      questionBudget - length(questionLabel),
    )}`;
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
      : intent.route === "chat_creative" || intent.route === "local_runtime"
        ? []
        : intent.route === "external_fact"
          ? [webTool]
          : intent.route === "local_knowledge"
            ? [ragTool]
            : [ragTool, webTool];
    const result = await this.#runtime.run({
      sessionId: event.umo,
      systemPrompt: intent.isFallback
        ? FALLBACK_SYSTEM_PROMPT
        : isCasualChat
          ? CHAT_SYSTEM_PROMPT
          : intent.route === "external_fact"
            ? EXTERNAL_SYSTEM_PROMPT
            : intent.route === "local_runtime"
              ? LOCAL_RUNTIME_SYSTEM_PROMPT
              : SYSTEM_PROMPT,
      prompt,
      tools,
    });
    const text = result.text
      .replace(/[（(]\s*(?:AI|ai)生成内容\s*[）)]/gu, "")
      .trim();
    if (!text) {
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
    return {
      action: "reply",
      messages: [{ type: "text", text: `${citedText}\n（ai生成内容）` }],
      reason_code: "agent_reply",
    };
  }
}
