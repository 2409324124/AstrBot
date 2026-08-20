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
  outboundHttpProxy?: string;
  routerModel: string;
  routerTimeoutMs: number;
  routerMaxOutputTokens: number;
  gatewayTimezone: string;
  groupWhitelist: string[];
  contextWindow: number;
  maxOutputTokens: number;
  ragEvidenceThreshold: number;
  agentTimeoutMs: number;
};

function groupWhitelist(env: NodeJS.ProcessEnv): string[] {
  const groups = (env.GROUP_WHITELIST ?? "")
    .split(",")
    .map((group) => group.trim())
    .filter(Boolean);
  if (groups.some((group) => !/^\d{5,20}$/u.test(group))) {
    throw new Error("GROUP_WHITELIST must contain comma-separated group IDs");
  }
  return [...new Set(groups)];
}

function required(env: NodeJS.ProcessEnv, name: string): string {
  const value = env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

function optionalHttpUrl(env: NodeJS.ProcessEnv, name: string): string | undefined {
  const value = env[name]?.trim();
  if (!value) {
    return undefined;
  }
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${name} must be a valid HTTP(S) URL`);
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error(`${name} must be a valid HTTP(S) URL`);
  }
  return parsed.toString().replace(/\/$/u, "");
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
    outboundHttpProxy: optionalHttpUrl(env, "OUTBOUND_HTTP_PROXY"),
    routerModel: env.ROUTER_MODEL?.trim() || required(env, "LLM_MODEL"),
    routerTimeoutMs: boundedNumber(
      env,
      "ROUTER_TIMEOUT_MS",
      30000,
      1000,
      120000,
    ),
    routerMaxOutputTokens: boundedNumber(
      env,
      "ROUTER_MAX_OUTPUT_TOKENS",
      512,
      256,
      2048,
    ),
    gatewayTimezone: env.GATEWAY_TIMEZONE?.trim() || "Asia/Shanghai",
    groupWhitelist: groupWhitelist(env),
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
