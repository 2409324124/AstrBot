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

type GatewayAgentOptions = {
  rag: RagPort;
  runtime: RuntimePort;
  exa: ExaPort;
  evidenceThreshold: number;
};

const SYSTEM_PROMPT = `你是东云bot。回答前已经执行了本地知识检索。
只把标为“本地证据”的内容当作本地知识，不得伪造来源。
若证据不足，可调用 rag_search 改写查询继续检索。
普通闲聊尽量不超过20个中文字符；技术内容按需要完整回答。
不要自行添加 AI 内容标记，网关会统一添加。`;

export class GatewayAgent {
  readonly #rag: RagPort;
  readonly #runtime: RuntimePort;
  readonly #exa: ExaPort;
  readonly #evidenceThreshold: number;

  constructor(options: GatewayAgentOptions) {
    this.#rag = options.rag;
    this.#runtime = options.runtime;
    this.#exa = options.exa;
    this.#evidenceThreshold = options.evidenceThreshold;
  }

  async handle(event: GatewayEvent): Promise<GatewayDecision> {
    const initialHits = await this.#rag.search(event.text, { topK: 8 });
    const evidence = initialHits.filter(
      (hit) => hit.score >= this.#evidenceThreshold,
    );
    const ragParameters = Type.Object({
      query: Type.String({ minLength: 1 }),
      top_k: Type.Optional(Type.Integer({ minimum: 1, maximum: 12 })),
    });
    const ragTool: AgentTool<typeof ragParameters, { hitCount: number }> = {
      name: "rag_search",
      label: "RAG Search",
      description: "Search the local persistent knowledge base",
      parameters: ragParameters,
      execute: async (_toolCallId, params) => {
        const hits = await this.#rag.search(params.query, {
          topK: params.top_k ?? 8,
        });
        return {
          content: [
            {
              type: "text",
              text: hits
                .map(
                  (hit, index) =>
                    `[${index + 1}] ${hit.text}\n来源: ${hit.source}`,
                )
                .join("\n\n"),
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
    const evidenceBlock = evidence.length
      ? evidence
          .map(
            (hit, index) =>
              `[本地证据 ${index + 1}] ${hit.text}\n来源: ${hit.source}`,
          )
          .join("\n\n")
      : "[本地证据] 未检索到达到阈值的内容。";
    const result = await this.#runtime.run({
      sessionId: event.umo,
      systemPrompt: SYSTEM_PROMPT,
      prompt: `${evidenceBlock}\n\n[用户问题]\n${event.text}`,
      tools: [ragTool, webTool],
    });
    const text = result.text
      .replace(/[（(]\s*(?:AI|ai)生成内容\s*[）)]/gu, "")
      .trim();
    if (!text) {
      return { action: "no_reply", messages: [], reason_code: "empty_agent_reply" };
    }
    const sources = [...new Set(evidence.map((hit) => hit.source))];
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
