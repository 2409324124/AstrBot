import assert from "node:assert/strict";
import test from "node:test";

import {
  createModels,
  fauxAssistantMessage,
  fauxProvider,
  fauxToolCall
} from "@earendil-works/pi-ai";
import { Type } from "typebox";

import { PiAgentRuntime } from "../src/pi-runtime.ts";

test("Pi runtime returns streamed assistant text and usage", async () => {
  const faux = fauxProvider();
  const models = createModels();
  models.setProvider(faux.provider);
  faux.setResponses([
    fauxAssistantMessage("检索链路正常")
  ]);
  const runtime = new PiAgentRuntime({
    models,
    model: faux.getModel(),
    timeoutMs: 1000
  });

  const result = await runtime.run({
    sessionId: "private:1907483592",
    systemPrompt: "只基于提供的证据回答。",
    prompt: "当前检索是否正常？",
    tools: []
  });

  assert.equal(result.text, "检索链路正常");
  assert.ok(result.usage.input > 0);
  assert.ok(result.usage.output > 0);
  assert.equal(faux.state.callCount, 1);
});

test("Pi runtime executes a tool and returns the follow-up answer", async () => {
  const faux = fauxProvider();
  const models = createModels();
  models.setProvider(faux.provider);
  faux.setResponses([
    fauxAssistantMessage(
      fauxToolCall("rag_search", { query: "Xeon Max 9470C" }, { id: "tool-1" }),
      { stopReason: "toolUse" }
    ),
    fauxAssistantMessage("9470C 为 52 核 Xeon Max。")
  ]);
  let searched = "";
  const runtime = new PiAgentRuntime({
    models,
    model: faux.getModel(),
    timeoutMs: 1000
  });

  const result = await runtime.run({
    sessionId: "private:1907483592",
    systemPrompt: "检索后回答。",
    prompt: "我的服务器 CPU 是什么？",
    tools: [{
      name: "rag_search",
      label: "RAG Search",
      description: "Search local knowledge",
      parameters: Type.Object({ query: Type.String() }),
      execute: async (_id, params) => {
        searched = params.query;
        return {
          content: [{ type: "text", text: "Xeon Max 9470C，52 核" }],
          details: {}
        };
      }
    }]
  });

  assert.equal(searched, "Xeon Max 9470C");
  assert.equal(result.text, "9470C 为 52 核 Xeon Max。");
  assert.equal(faux.state.callCount, 2);
});

test("Pi runtime switches model without recreating the gateway", async () => {
  const online = fauxProvider({ provider: "online", models: [{ id: "online-a" }] });
  const local = fauxProvider({ provider: "local", models: [{ id: "local-b" }] });
  const models = createModels();
  models.setProvider(online.provider);
  models.setProvider(local.provider);
  local.setResponses([fauxAssistantMessage("本地模型已接管")]);
  const runtime = new PiAgentRuntime({
    models,
    model: online.getModel(),
    timeoutMs: 1000
  });

  runtime.setModel(local.getModel());
  const result = await runtime.run({
    sessionId: "group:709694410",
    systemPrompt: "回答。",
    prompt: "测试模型切换",
    tools: []
  });

  assert.equal(result.text, "本地模型已接管");
  assert.equal(online.state.callCount, 0);
  assert.equal(local.state.callCount, 1);
});
