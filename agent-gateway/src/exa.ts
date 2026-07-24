export type ExaSearchResult = {
  title: string;
  url: string;
  text: string;
  publishedDate: string | null;
};

type ExaSearchClientOptions = {
  apiKey: string;
  fetch?: typeof fetch;
};

export class ExaSearchClient {
  readonly #apiKey: string;
  readonly #fetch: typeof fetch;

  constructor(options: ExaSearchClientOptions) {
    this.#apiKey = options.apiKey;
    this.#fetch = options.fetch ?? fetch;
  }

  async search(
    query: string,
    options: { domains?: string[]; maxResults: number },
  ): Promise<ExaSearchResult[]> {
    const response = await this.#fetch("https://api.exa.ai/search", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": this.#apiKey,
      },
      body: JSON.stringify({
        query,
        type: "auto",
        numResults: Math.min(Math.max(options.maxResults, 1), 8),
        ...(options.domains?.length
          ? { includeDomains: options.domains.slice(0, 8) }
          : {}),
        contents: { text: { maxCharacters: 3000 } },
      }),
    });
    if (!response.ok) {
      throw new Error(`Exa request failed with status ${response.status}`);
    }
    const body = (await response.json()) as {
      results?: Array<{
        title?: string;
        url?: string;
        text?: string;
        publishedDate?: string | null;
      }>;
    };
    return (body.results ?? []).flatMap((result) => {
      if (!result.url) {
        return [];
      }
      return [
        {
          title: result.title ?? result.url,
          url: result.url,
          text: result.text ?? "",
          publishedDate: result.publishedDate ?? null,
        },
      ];
    });
  }
}
