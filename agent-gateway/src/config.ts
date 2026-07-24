export type GatewayConfig = {
  port: number;
  eventToken: string;
  adminToken: string;
  databasePath: string;
  qdrantUrl: string;
  qdrantApiKey: string;
  qdrantCollection: string;
  embeddingBaseUrl: string;
  embeddingApiKey: string;
  embeddingModel: string;
  embeddingBatchSize: number;
  exaApiKey: string;
  llmBaseUrl: string;
  llmApiKey: string;
  llmModel: string;
  contextWindow: number;
  maxOutputTokens: number;
  ragEvidenceThreshold: number;
  agentTimeoutMs: number;
};

function required(env: NodeJS.ProcessEnv, name: string): string {
  const value = env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

function boundedNumber(
  env: NodeJS.ProcessEnv,
  name: string,
  fallback: number,
  minimum: number,
  maximum: number,
): number {
  const value = env[name] ? Number(env[name]) : fallback;
  if (!Number.isFinite(value) || value < minimum || value > maximum) {
    throw new Error(`${name} must be between ${minimum} and ${maximum}`);
  }
  return value;
}

export function loadConfig(env: NodeJS.ProcessEnv): GatewayConfig {
  return {
    port: boundedNumber(env, "PORT", 8090, 1, 65535),
    eventToken: required(env, "EVENT_TOKEN"),
    adminToken: required(env, "ADMIN_TOKEN"),
    databasePath: env.GATEWAY_DB_PATH ?? "/data/gateway.sqlite3",
    qdrantUrl: required(env, "QDRANT_URL"),
    qdrantApiKey: required(env, "QDRANT_API_KEY"),
    qdrantCollection: env.QDRANT_COLLECTION ?? "agent_rag_v1",
    embeddingBaseUrl: required(env, "EMBEDDING_BASE_URL"),
    embeddingApiKey: required(env, "EMBEDDING_API_KEY"),
    embeddingModel: env.EMBEDDING_MODEL ?? "BAAI/bge-m3",
    embeddingBatchSize: boundedNumber(
      env,
      "EMBEDDING_BATCH_SIZE",
      32,
      1,
      64,
    ),
    exaApiKey: required(env, "EXA_API_KEY"),
    llmBaseUrl: required(env, "LLM_BASE_URL"),
    llmApiKey: required(env, "LLM_API_KEY"),
    llmModel: required(env, "LLM_MODEL"),
    contextWindow: boundedNumber(env, "CONTEXT_WINDOW", 16384, 4096, 1000000),
    maxOutputTokens: boundedNumber(
      env,
      "MAX_OUTPUT_TOKENS",
      4096,
      256,
      65536,
    ),
    ragEvidenceThreshold: boundedNumber(
      env,
      "RAG_EVIDENCE_THRESHOLD",
      0.03,
      0,
      1,
    ),
    agentTimeoutMs: boundedNumber(
      env,
      "AGENT_TIMEOUT_MS",
      90000,
      1000,
      600000,
    ),
  };
}
