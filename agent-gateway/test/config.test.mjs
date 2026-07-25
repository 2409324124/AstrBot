import assert from "node:assert/strict";
import test from "node:test";

import { loadConfig } from "../src/config.ts";

test("gateway config validates secrets and parses bounded runtime values", () => {
  assert.throws(() => loadConfig({}), /EVENT_TOKEN/);

  const config = loadConfig({
    EVENT_TOKEN: "event-secret",
    ADMIN_TOKEN: "admin-secret",
    QDRANT_URL: "http://qdrant:6333",
    QDRANT_API_KEY: "qdrant-secret",
    EMBEDDING_BASE_URL: "http://embedding-server:8000/v1",
    EMBEDDING_API_KEY: "embedding-secret",
    EXA_API_KEY: "exa-secret",
    LLM_BASE_URL: "https://api.deepseek.com",
    LLM_API_KEY: "llm-secret",
    LLM_MODEL: "deepseek-v4-pro",
    GROUP_WHITELIST: "709694410, 89589336,709694410",
    RAG_EVIDENCE_THRESHOLD: "0.03",
    AGENT_TIMEOUT_MS: "90000"
  });

  assert.equal(config.port, 8090);
  assert.equal(config.embeddingBatchSize, 32);
  assert.equal(config.contextWindow, 16384);
  assert.equal(config.ragEvidenceThreshold, 0.03);
  assert.equal(config.agentTimeoutMs, 90000);
  assert.equal(config.routerModel, "deepseek-v4-pro");
  assert.equal(config.routerTimeoutMs, 30000);
  assert.equal(config.routerMaxOutputTokens, 512);
  assert.deepEqual(config.groupWhitelist, ["709694410", "89589336"]);
});

test("gateway config rejects malformed group whitelist entries", () => {
  const env = {
    EVENT_TOKEN: "event-secret",
    ADMIN_TOKEN: "admin-secret",
    QDRANT_URL: "http://qdrant:6333",
    QDRANT_API_KEY: "qdrant-secret",
    EMBEDDING_BASE_URL: "http://embedding-server:8000/v1",
    EMBEDDING_API_KEY: "embedding-secret",
    EXA_API_KEY: "exa-secret",
    LLM_BASE_URL: "https://api.deepseek.com",
    LLM_API_KEY: "llm-secret",
    LLM_MODEL: "deepseek-v4-pro",
    GROUP_WHITELIST: "709694410,all"
  };
  assert.throws(() => loadConfig(env), /GROUP_WHITELIST/);
});
