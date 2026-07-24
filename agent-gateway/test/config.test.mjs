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
    RAG_EVIDENCE_THRESHOLD: "0.03",
    AGENT_TIMEOUT_MS: "90000"
  });

  assert.equal(config.port, 8090);
  assert.equal(config.embeddingBatchSize, 32);
  assert.equal(config.contextWindow, 16384);
  assert.equal(config.ragEvidenceThreshold, 0.03);
  assert.equal(config.agentTimeoutMs, 90000);
});
