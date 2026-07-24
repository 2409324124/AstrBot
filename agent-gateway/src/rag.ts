export type RagHit = {
  id: string;
  score: number;
  text: string;
  source: string;
  kbId: string;
};

type OpenAIEmbeddingClientOptions = {
  baseUrl: string;
  apiKey: string;
  model: string;
  batchSize: number;
  fetch?: typeof fetch;
};

export class OpenAIEmbeddingClient implements EmbeddingPort {
  readonly #url: string;
  readonly #apiKey: string;
  readonly #model: string;
  readonly #batchSize: number;
  readonly #fetch: typeof fetch;

  constructor(options: OpenAIEmbeddingClientOptions) {
    if (options.batchSize < 1 || options.batchSize > 64) {
      throw new Error("Embedding batch size must be between 1 and 64");
    }
    this.#url = `${options.baseUrl.replace(/\/$/, "")}/embeddings`;
    this.#apiKey = options.apiKey;
    this.#model = options.model;
    this.#batchSize = options.batchSize;
    this.#fetch = options.fetch ?? fetch;
  }

  async embed(texts: string[]): Promise<number[][]> {
    const vectors: number[][] = [];
    for (let start = 0; start < texts.length; start += this.#batchSize) {
      const input = texts.slice(start, start + this.#batchSize);
      const response = await this.#fetch(this.#url, {
        method: "POST",
        headers: {
          authorization: `Bearer ${this.#apiKey}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ model: this.#model, input }),
      });
      if (!response.ok) {
        throw new Error(`Embedding request failed with status ${response.status}`);
      }
      const body = (await response.json()) as {
        data?: Array<{ index: number; embedding: number[] }>;
      };
      if (!body.data || body.data.length !== input.length) {
        throw new Error("Embedding response length mismatch");
      }
      vectors.push(
        ...body.data
          .toSorted((left, right) => left.index - right.index)
          .map((item) => item.embedding),
      );
    }
    return vectors;
  }
}

type EmbeddingPort = {
  embed: (texts: string[]) => Promise<number[][]>;
};

type HybridQueryRequest = {
  prefetch: Array<{
    query:
      | number[]
      | {
          text: string;
          model: "qdrant/bm25";
          options: { tokenizer: "multilingual"; language: "none" };
        };
    using: "dense" | "bm25";
    limit: number;
  }>;
  query: { fusion: "rrf" };
  limit: number;
  with_payload: true;
};

type QdrantPort = {
  query: (
    collection: string,
    request: HybridQueryRequest,
  ) => Promise<{
    points: Array<{
      id: string | number;
      score: number;
      payload?: Record<string, unknown> | null;
    }>;
  }>;
};

type HybridRagOptions = {
  collection: string;
  embedding: EmbeddingPort;
  qdrant: QdrantPort;
};

export class HybridRag {
  readonly #collection: string;
  readonly #embedding: EmbeddingPort;
  readonly #qdrant: QdrantPort;

  constructor(options: HybridRagOptions) {
    this.#collection = options.collection;
    this.#embedding = options.embedding;
    this.#qdrant = options.qdrant;
  }

  async search(query: string, options: { topK: number }): Promise<RagHit[]> {
    const vectors = await this.#embedding.embed([query]);
    const dense = vectors[0];
    if (!dense) {
      throw new Error("Embedding service returned no vector");
    }
    const candidateLimit = Math.max(options.topK * 3, options.topK);
    const result = await this.#qdrant.query(this.#collection, {
      prefetch: [
        { query: dense, using: "dense", limit: candidateLimit },
        {
          query: {
            text: query,
            model: "qdrant/bm25",
            options: { tokenizer: "multilingual", language: "none" },
          },
          using: "bm25",
          limit: candidateLimit,
        },
      ],
      query: { fusion: "rrf" },
      limit: options.topK,
      with_payload: true,
    });
    return result.points.flatMap((point) => {
      const text = point.payload?.text;
      if (typeof text !== "string" || !text.trim()) {
        return [];
      }
      return [
        {
          id: String(point.id),
          score: point.score,
          text,
          source:
            typeof point.payload?.source === "string"
              ? point.payload.source
              : "unknown",
          kbId:
            typeof point.payload?.kb_id === "string"
              ? point.payload.kb_id
              : "unknown",
        },
      ];
    });
  }
}
