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
  assert.ok(result.usage.output > Math.ceil(result.text.length / 4));
});

test("Pi runtime requires a named tool only on the first provider turn", async () => {
  const faux = fauxProvider();
  const models = createModels();
  models.setProvider(faux.provider);
  const payloads = [];
  faux.setResponses([
    async (_context, options, _state, model) => {
      payloads.push(await options?.onPayload?.({ model: model.id, tools: [] }, model));
      return fauxAssistantMessage(
        fauxToolCall("get_weather", { location: "广州" }, { id: "tool-weather" }),
        { stopReason: "toolUse" }
      );
    },
    async (_context, options, _state, model) => {
      payloads.push(await options?.onPayload?.({ model: model.id, tools: [] }, model));
      return fauxAssistantMessage("广州当前天气晴朗。");
    }
  ]);
  const runtime = new PiAgentRuntime({
    models,
    model: faux.getModel(),
    timeoutMs: 1000
  });

  await runtime.run({
    sessionId: "group:weather",
    systemPrompt: "查询后回答。",
    prompt: "今天广州天气怎么样？",
    requiredTool: "get_weather",
    tools: [{
      name: "get_weather",
      label: "Weather",
      description: "Get current weather and forecast",
      parameters: Type.Object({ location: Type.String() }),
      execute: async () => ({
        content: [{ type: "text", text: "广州：晴，32°C" }],
        details: {}
      })
    }]
  });

  assert.deepEqual(payloads[0]?.tool_choice, {
    type: "function",
    function: { name: "get_weather" }
  });
  assert.equal(payloads[1]?.tool_choice, undefined);
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

test("Pi runtime aborts only the active session", async () => {
  const faux = fauxProvider({ tokensPerSecond: 100 });
  const models = createModels();
  models.setProvider(faux.provider);
  faux.setResponses([fauxAssistantMessage("这是一段足够长的慢速回答，用于验证会话取消。")]);
  const runtime = new PiAgentRuntime({
    models,
    model: faux.getModel(),
    timeoutMs: 10000
  });

  const pending = runtime.run({
    sessionId: "group:slow",
    systemPrompt: "回答。",
    prompt: "慢速测试",
    tools: []
  });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(runtime.abort("group:other"), 0);
  assert.equal(runtime.abort("group:slow"), 1);
  await assert.rejects(pending, /aborted/i);
  assert.equal(runtime.abort("group:slow"), 0);
});
