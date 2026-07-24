import assert from "node:assert/strict";
import test from "node:test";

import { HybridRag, OpenAIEmbeddingClient } from "../src/rag.ts";

test("hybrid RAG fuses BGE-M3 dense and multilingual BM25 results", async () => {
  let queryRequest;
  const rag = new HybridRag({
    collection: "agent_rag_v1",
    embedding: {
      embed: async (texts) => {
        assert.deepEqual(texts, ["我的服务器CPU是什么？"]);
        return [[0.1, 0.2, 0.3]];
      }
    },
    qdrant: {
      query: async (collection, request) => {
        assert.equal(collection, "agent_rag_v1");
        queryRequest = request;
        return {
          points: [{
            id: "chunk-1",
            score: 0.91,
            payload: {
              text: "服务器 CPU 是 Intel Xeon Max 9470C，52 核。",
              source: "test.md",
              kb_id: "server"
            }
          }]
        };
      }
    }
  });

  const hits = await rag.search("我的服务器CPU是什么？", { topK: 8 });

  assert.deepEqual(queryRequest, {
    prefetch: [
      { query: [0.1, 0.2, 0.3], using: "dense", limit: 24 },
      {
        query: {
          text: "我的服务器CPU是什么？",
          model: "qdrant/bm25",
          options: { tokenizer: "multilingual", language: "none" }
        },
        using: "bm25",
        limit: 24
      }
    ],
    query: { fusion: "rrf" },
    limit: 8,
    with_payload: true
  });
  assert.deepEqual(hits, [{
    id: "chunk-1",
    score: 0.91,
    text: "服务器 CPU 是 Intel Xeon Max 9470C，52 核。",
    source: "test.md",
    kbId: "server"
  }]);
});

test("embedding client splits more than 64 texts without reordering vectors", async () => {
  const batchSizes = [];
  const client = new OpenAIEmbeddingClient({
    baseUrl: "http://embedding-server:8000/v1",
    apiKey: "embedding-secret",
    model: "BAAI/bge-m3",
    batchSize: 32,
    fetch: async (_url, init) => {
      const body = JSON.parse(init.body);
      batchSizes.push(body.input.length);
      return new Response(JSON.stringify({
        data: body.input.map((text, index) => ({
          index,
          embedding: [Number(text.slice(1))]
        })).reverse()
      }), { status: 200, headers: { "content-type": "application/json" } });
    }
  });
  const texts = Array.from({ length: 70 }, (_, index) => `t${index}`);

  const vectors = await client.embed(texts);

  assert.deepEqual(batchSizes, [32, 32, 6]);
  assert.deepEqual(vectors, texts.map((_, index) => [index]));
});
