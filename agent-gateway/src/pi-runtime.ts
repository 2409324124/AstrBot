import { Agent, type AgentTool } from "@earendil-works/pi-agent-core";
import type { Api, Model, Models, Usage } from "@earendil-works/pi-ai";

export type AgentRunInput = {
  sessionId: string;
  systemPrompt: string;
  prompt: string;
  tools: AgentTool[];
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

  constructor(options: PiAgentRuntimeOptions) {
    this.#models = options.models;
    this.#model = options.model;
    this.#timeoutMs = options.timeoutMs;
  }

  setModel(model: Model<Api>): void {
    this.#model = model;
  }

  async run(input: AgentRunInput): Promise<AgentRunResult> {
    const agent = new Agent({
      initialState: {
        systemPrompt: input.systemPrompt,
        model: this.#model,
        tools: input.tools,
      },
      sessionId: input.sessionId,
      streamFn: this.#models.streamSimple.bind(this.#models),
      toolExecution: "sequential",
    });
    const timeout = setTimeout(() => agent.abort(), this.#timeoutMs);
    try {
      await agent.prompt(input.prompt);
    } finally {
      clearTimeout(timeout);
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
    return {
      text: message.content
        .filter((content) => content.type === "text")
        .map((content) => content.text)
        .join(""),
      usage: message.usage,
    };
  }
}
