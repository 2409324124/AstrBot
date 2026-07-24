import { pathToFileURL } from "node:url";

import { createModels, createProvider, type Model } from "@earendil-works/pi-ai";
import {
  stream,
  streamSimple,
} from "@earendil-works/pi-ai/api/openai-completions";
import { QdrantClient } from "@qdrant/js-client-rest";

import { createApp } from "./app.ts";
import { loadConfig } from "./config.ts";
import { ExaSearchClient } from "./exa.ts";
import { GatewayAgent } from "./gateway-agent.ts";
import { PiAgentRuntime } from "./pi-runtime.ts";
import { HybridRag, OpenAIEmbeddingClient } from "./rag.ts";
import { SqliteGatewayStore } from "./store.ts";

export function buildApp(env: NodeJS.ProcessEnv) {
  const config = loadConfig(env);
  const embedding = new OpenAIEmbeddingClient({
    baseUrl: config.embeddingBaseUrl,
    apiKey: config.embeddingApiKey,
    model: config.embeddingModel,
    batchSize: config.embeddingBatchSize,
  });
  const qdrantClient = new QdrantClient({
    url: config.qdrantUrl,
    apiKey: config.qdrantApiKey,
  });
  const rag = new HybridRag({
    collection: config.qdrantCollection,
    embedding,
    qdrant: {
      query: async (collection, request) =>
        await qdrantClient.query(collection, request),
    },
  });
  const model: Model<"openai-completions"> = {
    id: config.llmModel,
    name: config.llmModel,
    api: "openai-completions",
    provider: "gateway-openai-compatible",
    baseUrl: config.llmBaseUrl,
    reasoning: true,
    input: ["text"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: config.contextWindow,
    maxTokens: config.maxOutputTokens,
    compat: {
      supportsStore: false,
      supportsDeveloperRole: false,
      requiresReasoningContentOnAssistantMessages: true,
      thinkingFormat: "deepseek",
    },
  };
  const provider = createProvider({
    id: "gateway-openai-compatible",
    name: "Gateway OpenAI-compatible",
    baseUrl: config.llmBaseUrl,
    auth: {
      apiKey: {
        name: "Gateway LLM API key",
        resolve: async () => ({
          auth: { apiKey: config.llmApiKey, baseUrl: config.llmBaseUrl },
          source: "gateway environment",
        }),
      },
    },
    models: [model],
    api: { stream, streamSimple },
  });
  const models = createModels();
  models.setProvider(provider);
  const runtime = new PiAgentRuntime({
    models,
    model,
    timeoutMs: config.agentTimeoutMs,
  });
  const gatewayAgent = new GatewayAgent({
    rag,
    runtime,
    exa: new ExaSearchClient({ apiKey: config.exaApiKey }),
    evidenceThreshold: config.ragEvidenceThreshold,
  });
  const store = new SqliteGatewayStore(config.databasePath);
  const app = createApp({
    eventToken: config.eventToken,
    decisionStore: store,
    handleEvent: gatewayAgent.handle.bind(gatewayAgent),
  });
  app.get("/healthz", async () => ({ status: "ok" }));
  app.get("/readyz", async (_request, reply) => {
    try {
      await qdrantClient.getCollection(config.qdrantCollection);
      return { status: "ready" };
    } catch {
      return reply.code(503).send({ status: "not_ready" });
    }
  });
  app.addHook("onClose", async () => store.close());
  return { app, config };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const { app, config } = buildApp(process.env);
  await app.listen({ host: "0.0.0.0", port: config.port });
}
