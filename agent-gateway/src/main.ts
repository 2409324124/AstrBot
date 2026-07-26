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
import { RuntimeIntentRouter } from "./intent-router.ts";
import { ConversationMemory } from "./memory.ts";
import { PiAgentRuntime } from "./pi-runtime.ts";
import { HybridRag, OpenAIEmbeddingClient } from "./rag.ts";
import { SqliteGatewayStore } from "./store.ts";

export function buildApp(env: NodeJS.ProcessEnv) {
  const config = loadConfig(env);
  const store = new SqliteGatewayStore(config.databasePath);
  const persistedAdminConfig = store.getAdminConfig();
  const activeModelId = persistedAdminConfig?.model ?? config.llmModel;
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
    id: activeModelId,
    name: activeModelId,
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
  const routerModel: Model<"openai-completions"> = {
    ...model,
    id: config.routerModel,
    name: config.routerModel,
    maxTokens: config.routerMaxOutputTokens,
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
    models:
      routerModel.id === model.id ? [model] : [model, routerModel],
    api: { stream, streamSimple },
  });
  const models = createModels();
  models.setProvider(provider);
  const runtime = new PiAgentRuntime({
    models,
    model,
    timeoutMs: config.agentTimeoutMs,
  });
  const routerRuntime = new PiAgentRuntime({
    models,
    model: routerModel,
    timeoutMs: config.routerTimeoutMs,
  });
  const memory = new ConversationMemory({
    store,
    tokenBudget: Math.max(
      1024,
      config.contextWindow - config.maxOutputTokens - 4096,
    ),
  });
  const gatewayAgent = new GatewayAgent({
    router: new RuntimeIntentRouter({
      runtime: routerRuntime,
      onUsage: (sessionId, usage) => store.add(sessionId, usage),
    }),
    audit: {
      record: (entry) => console.info(JSON.stringify(entry)),
    },
    rag,
    runtime,
    exa: new ExaSearchClient({ apiKey: config.exaApiKey }),
    evidenceThreshold: config.ragEvidenceThreshold,
    memory,
    usage: store,
    maxPromptTokens: Math.max(
      1024,
      config.contextWindow - config.maxOutputTokens - 1024,
    ),
  });
  const app = createApp({
    eventToken: config.eventToken,
    adminToken: config.adminToken,
    decisionStore: store,
    adminStore: store,
    initialAdminConfig: {
      model: config.llmModel,
      groupWhitelist: config.groupWhitelist,
    },
    onModelChange: (modelId) => {
      runtime.setModel({ ...model, id: modelId, name: modelId });
    },
    handleEvent: gatewayAgent.handle.bind(gatewayAgent),
    handleSessionControl: async (request) =>
      await gatewayAgent.control(request.session_id, request.action),
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
