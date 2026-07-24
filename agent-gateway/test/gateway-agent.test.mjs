import assert from "node:assert/strict";
import test from "node:test";

import { GatewayAgent } from "../src/gateway-agent.ts";

test("Gateway agent retrieves evidence before calling the LLM", async () => {
  const order = [];
  let runInput;
  const agent = new GatewayAgent({
    rag: {
      search: async (query, options) => {
        order.push("rag");
        assert.equal(query, "我的服务器CPU是什么？");
        assert.deepEqual(options, { topK: 8 });
        return [{
          id: "chunk-1",
          score: 0.91,
          text: "服务器 CPU 是 Intel Xeon Max 9470C，52 核。",
          source: "test.md",
          kbId: "server"
        }];
      }
    },
    runtime: {
      run: async (input) => {
        order.push("llm");
        runInput = input;
        return {
          text: "你的服务器使用 Xeon Max 9470C。",
          usage: { input: 20, output: 10, cacheRead: 0, cacheWrite: 0, totalTokens: 30, cost: {} }
        };
      }
    },
    exa: { search: async () => [] },
    evidenceThreshold: 0.2
  });

  const decision = await agent.handle({
    schema_version: "1",
    message_id: "private-1",
    umo: "aiocqhttp:FriendMessage:1907483592",
    chat_type: "private",
    sender_id: "1907483592",
    self_id: "bot-account",
    text: "我的服务器CPU是什么？",
    mentions: [],
    timestamp: 1784860800000,
    is_admin: true,
    owner_takeover_active: false
  });

  assert.deepEqual(order, ["rag", "llm"]);
  assert.match(runInput.prompt, /Xeon Max 9470C/);
  assert.match(runInput.prompt, /test\.md/);
  assert.ok(runInput.tools.some((tool) => tool.name === "rag_search"));
  assert.deepEqual(decision, {
    action: "reply",
    messages: [{
      type: "text",
      text: "你的服务器使用 Xeon Max 9470C。\n本地来源：test.md\n（ai生成内容）"
    }],
    reason_code: "agent_reply"
  });
});

test("Gateway agent exposes web search with x.com filtering", async () => {
  let searchOptions;
  const agent = new GatewayAgent({
    rag: { search: async () => [] },
    exa: {
      search: async (_query, options) => {
        searchOptions = options;
        return [{
          title: "发布",
          url: "https://x.com/example/status/1",
          text: "新模型发布",
          publishedDate: "2026-07-24"
        }];
      }
    },
    runtime: {
      run: async (input) => {
        const web = input.tools.find((tool) => tool.name === "web_search");
        assert.ok(web);
        const result = await web.execute("tool-2", {
          query: "最新模型",
          domains: ["x.com"],
          max_results: 5
        }, new AbortController().signal);
        assert.match(result.content[0].text, /https:\/\/x\.com/);
        return {
          text: "已找到发布来源。",
          usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
        };
      }
    },
    evidenceThreshold: 0.2
  });

  const decision = await agent.handle({
    schema_version: "1",
    message_id: "private-2",
    umo: "aiocqhttp:FriendMessage:1907483592",
    chat_type: "private",
    sender_id: "1907483592",
    self_id: "bot-account",
    text: "搜索 X 上的最新模型发布",
    mentions: [],
    timestamp: 1784860800000,
    is_admin: true,
    owner_takeover_active: false
  });

  assert.deepEqual(searchOptions, { domains: ["x.com"], maxResults: 5 });
  assert.equal(decision.action, "reply");
});
