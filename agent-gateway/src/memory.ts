export type ConversationExchange = {
  user: string;
  assistant: string;
};

export type ConversationState = {
  summary: string;
  exchanges: ConversationExchange[];
};

export type ConversationStore = {
  getConversation: (sessionId: string) => ConversationState | undefined;
  saveConversation: (sessionId: string, state: ConversationState) => void;
};

type ConversationMemoryOptions = {
  store: ConversationStore;
  tokenBudget: number;
};

function codePoints(text: string): number {
  return [...text].length;
}

function tail(text: string, limit: number): string {
  const points = [...text];
  return points.length <= limit ? text : points.slice(-limit).join("");
}

function exchangeText(exchange: ConversationExchange): string {
  return `用户：${exchange.user}\n助手：${exchange.assistant}`;
}

function render(state: ConversationState): string {
  const sections: string[] = [];
  if (state.summary) {
    sections.push(`[历史摘要]\n${state.summary}`);
  }
  if (state.exchanges.length) {
    sections.push(`[最近对话]\n${state.exchanges.map(exchangeText).join("\n")}`);
  }
  return sections.join("\n\n");
}

export class ConversationMemory {
  readonly #store: ConversationStore;
  readonly #tokenBudget: number;

  constructor(options: ConversationMemoryOptions) {
    this.#store = options.store;
    this.#tokenBudget = options.tokenBudget;
  }

  context(sessionId: string): string {
    return render(
      this.#store.getConversation(sessionId) ?? { summary: "", exchanges: [] },
    );
  }

  record(sessionId: string, user: string, assistant: string): void {
    const state = this.#store.getConversation(sessionId) ?? {
      summary: "",
      exchanges: [],
    };
    state.exchanges.push({ user, assistant });
    while (
      codePoints(render(state)) > this.#tokenBudget &&
      state.exchanges.length > 1
    ) {
      const oldest = state.exchanges.shift()!;
      state.summary = [state.summary, exchangeText(oldest)]
        .filter(Boolean)
        .join("\n");
      state.summary = tail(
        state.summary,
        Math.max(24, Math.floor(this.#tokenBudget * 0.35)),
      );
    }
    if (codePoints(render(state)) > this.#tokenBudget) {
      const latest = state.exchanges[0]!;
      const available = Math.max(
        12,
        this.#tokenBudget - codePoints(render({ ...state, exchanges: [] })) - 18,
      );
      latest.user = tail(latest.user, Math.floor(available / 2));
      latest.assistant = tail(latest.assistant, Math.ceil(available / 2));
    }
    let rendered = render(state);
    if (codePoints(rendered) > this.#tokenBudget) {
      state.summary = tail(
        state.summary,
        Math.max(0, codePoints(state.summary) - (codePoints(rendered) - this.#tokenBudget)),
      );
      rendered = render(state);
    }
    if (codePoints(rendered) > this.#tokenBudget) {
      state.summary = "";
    }
    this.#store.saveConversation(sessionId, state);
  }
}
