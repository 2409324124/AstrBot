import { Agent, type AgentTool } from "@earendil-works/pi-agent-core";
import type { Api, Model, Models, Usage } from "@earendil-works/pi-ai";

export type AgentRunInput = {
  sessionId: string;
  systemPrompt: string;
  prompt: string;
  tools: AgentTool[];
  requiredTool?: string;
};

export type AgentRunResult = {
  text: string;
  usage: Usage;
};

type PiAgentRuntimeOptions = {
  models: Models;
  model: Model<Api>;
  timeoutMs: number;
};

export class PiAgentRuntime {
  readonly #models: Models;
  #model: Model<Api>;
  readonly #timeoutMs: number;
  readonly #activeAgents = new Map<string, Agent>();

  constructor(options: PiAgentRuntimeOptions) {
    this.#models = options.models;
    this.#model = options.model;
    this.#timeoutMs = options.timeoutMs;
  }

  setModel(model: Model<Api>): void {
    this.#model = model;
  }

  abort(sessionId: string): number {
    const agent = this.#activeAgents.get(sessionId);
    if (!agent) {
      return 0;
    }
    agent.abort();
    return 1;
  }

  async run(input: AgentRunInput): Promise<AgentRunResult> {
    let providerTurn = 0;
    const agent = new Agent({
      initialState: {
        systemPrompt: input.systemPrompt,
        model: this.#model,
        tools: input.tools,
      },
      sessionId: input.sessionId,
      streamFn: this.#models.streamSimple.bind(this.#models),
      toolExecution: "sequential",
      ...(input.requiredTool
        ? {
            onPayload: (payload: unknown) => {
              const firstTurn = providerTurn === 0;
              providerTurn += 1;
              if (!firstTurn || !payload || typeof payload !== "object") {
                return payload;
              }
              return {
                ...payload,
                tool_choice: {
                  type: "function",
                  function: { name: input.requiredTool },
                },
              };
            },
          }
        : {}),
    });
    this.#activeAgents.set(input.sessionId, agent);
    const timeout = setTimeout(() => agent.abort(), this.#timeoutMs);
    try {
      await agent.prompt(input.prompt);
    } finally {
      clearTimeout(timeout);
      if (this.#activeAgents.get(input.sessionId) === agent) {
        this.#activeAgents.delete(input.sessionId);
      }
    }

    const message = agent.state.messages.findLast(
      (candidate) => candidate.role === "assistant",
    );
    if (!message || message.role !== "assistant") {
      throw new Error("Agent returned no assistant message");
    }
    if (message.stopReason === "error" || message.stopReason === "aborted") {
      throw new Error(`Agent stopped with ${message.stopReason}`);
    }
    const usage = agent.state.messages
      .filter((candidate) => candidate.role === "assistant")
      .reduce<Usage>(
        (total, candidate) => ({
          input: total.input + candidate.usage.input,
          output: total.output + candidate.usage.output,
          cacheRead: total.cacheRead + candidate.usage.cacheRead,
          cacheWrite: total.cacheWrite + candidate.usage.cacheWrite,
          totalTokens: total.totalTokens + candidate.usage.totalTokens,
          cost: {
            input: total.cost.input + candidate.usage.cost.input,
            output: total.cost.output + candidate.usage.cost.output,
            cacheRead: total.cost.cacheRead + candidate.usage.cost.cacheRead,
            cacheWrite: total.cost.cacheWrite + candidate.usage.cost.cacheWrite,
            total: total.cost.total + candidate.usage.cost.total,
          },
        }),
        {
          input: 0,
          output: 0,
          cacheRead: 0,
          cacheWrite: 0,
          totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
        },
      );
    return {
      text: message.content
        .filter((content) => content.type === "text")
        .map((content) => content.text)
        .join(""),
      usage,
    };
  }
}
