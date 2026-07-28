import assert from "node:assert/strict";
import test from "node:test";

import { GatewayAgent } from "../src/gateway-agent.ts";

const ALL_TOOL_NAMES = [
  "rag_search",
  "web_search",
  "get_current_time",
  "get_weather",
  "get_air_quality",
  "calculate",
  "convert_units",
  "convert_currency"
];

function fixedRouter(route = "local_knowledge") {
  return {
    classify: async () => ({ route, confidence: 0.99, isFallback: false })
  };
}

test("Gateway agent answers casual dining chat without consulting local RAG", async () => {
  const order = [];
  let runInput;
  const agent = new GatewayAgent({
    router: {
      classify: async (input) => {
        order.push("route");
        assert.deepEqual(input, { text: "我話今日中午食啲乜" });
        return { route: "chat_creative", confidence: 0.95, isFallback: false };
      }
    },
    rag: {
      search: async () => {
        order.push("rag");
        return [{
          id: "irrelevant",
          score: 0.5,
          text: "Food101 benchmark from the CLIP paper",
          source: "2021_clip.txt",
          kbId: "papers"
        }];
      }
    },
    exa: { search: async () => [] },
    runtime: {
      run: async (input) => {
        order.push("llm");
        runInput = input;
        return {
          text: "食个焗猪扒饭啦。",
          usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
        };
      }
    },
    evidenceThreshold: 0.03
  });

  const decision = await agent.handle({
    schema_version: "1",
    message_id: "group-chat-1",
    umo: "qq_napcat:GroupMessage:763898834",
    chat_type: "group",
    group_id: "763898834",
    sender_id: "member",
    self_id: "bot-account",
    text: "我話今日中午食啲乜",
    mentions: [],
    timestamp: 1784860800000,
    is_admin: false,
    owner_takeover_active: false
  });

  assert.deepEqual(order, ["route", "llm"]);
  assert.doesNotMatch(runInput.prompt, /本地证据|2021_clip/);
  assert.deepEqual(runInput.tools.map((tool) => tool.name), ALL_TOOL_NAMES);
  assert.match(runInput.systemPrompt, /无法创建定时任务或提醒/);
  assert.equal(decision.messages[0].text, "食个焗猪扒饭啦。\n（ai生成内容）");
});

test("Gateway agent resolves an elliptical question from quoted context", async () => {
  let routerInput;
  let ragCalls = 0;
  let runInput;
  const agent = new GatewayAgent({
    router: {
      classify: async (input) => {
        routerInput = input;
        return { route: "technical_concept", confidence: 0.97, isFallback: false };
      }
    },
    rag: {
      search: async () => {
        ragCalls += 1;
        return [];
      }
    },
    exa: { search: async () => [] },
    runtime: {
      run: async (input) => {
        runInput = input;
        return {
          text: "Pi 作为 Agent Gateway 编排层可行。",
          usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
        };
      }
    },
    memory: {
      context: () => "用户：准备把 AstrBot 接到独立 Gateway",
      record: () => undefined
    },
    evidenceThreshold: 0.03
  });

  const decision = await agent.handle({
    schema_version: "1",
    message_id: "quoted-follow-up-1",
    umo: "qq_napcat:GroupMessage:902811542",
    chat_type: "group",
    group_id: "902811542",
    sender_id: "member",
    self_id: "bot-account",
    text: "会好用吗",
    mentions: [],
    reply_context: {
      sender_id: "owner",
      text: "直接接 Pi 这个轮子"
    },
    timestamp: 1784860800000,
    is_admin: false,
    owner_takeover_active: false
  });

  assert.deepEqual(routerInput, {
    text: "会好用吗",
    replyContext: { senderId: "owner", text: "直接接 Pi 这个轮子" },
    recentContext: "用户：准备把 AstrBot 接到独立 Gateway"
  });
  assert.equal(ragCalls, 0);
  assert.match(runInput.prompt, /\[引用消息\]\n直接接 Pi 这个轮子/);
  assert.match(runInput.prompt, /\[用户问题\]\n会好用吗/);
  assert.match(runInput.systemPrompt, /不要仅以.*知识库.*没有/);
  assert.deepEqual(runInput.tools.map((tool) => tool.name), ALL_TOOL_NAMES);
  assert.equal(decision.action, "reply");
});

test("Gateway agent emits a content-free route audit", async () => {
  const audits = [];
  const agent = new GatewayAgent({
    router: {
      classify: async () => ({
        route: "chat_creative",
        confidence: 0.91,
        isFallback: false
      })
    },
    rag: { search: async () => [] },
    exa: { search: async () => [] },
    runtime: {
      run: async () => ({
        text: "可以。",
        usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
      })
    },
    audit: { record: (entry) => audits.push(entry) },
    evidenceThreshold: 0.03
  });

  await agent.handle({
    schema_version: "1",
    message_id: "audit-1",
    umo: "qq_napcat:GroupMessage:902811542",
    chat_type: "group",
    group_id: "902811542",
    sender_id: "member",
    self_id: "bot-account",
    text: "secret message body",
    mentions: [],
    timestamp: 1784860800000,
    is_admin: false,
    owner_takeover_active: false
  });

  assert.equal(audits.length, 2);
  assert.equal(audits[0].event, "gateway_route");
  assert.equal(audits[0].route, "chat_creative");
  assert.equal(audits[0].confidence, 0.91);
  assert.equal(audits[0].automatic_rag_hits, 0);
  assert.match(audits[0].session_ref, /^[0-9a-f]{12}$/);
  assert.deepEqual(
    {
      event: audits[1].event,
      action: audits[1].action,
      reason_code: audits[1].reason_code
    },
    { event: "gateway_reply", action: "reply", reason_code: "agent_reply" }
  );
  assert.doesNotMatch(JSON.stringify(audits), /secret message body|902811542/);
});

test("Gateway agent fallback keeps tools available without injecting automatic RAG", async () => {
  let ragCalls = 0;
  let runInput;
  const agent = new GatewayAgent({
    router: {
      classify: async () => ({
        route: "technical_concept",
        confidence: 0,
        isFallback: true
      })
    },
    rag: {
      search: async () => {
        ragCalls += 1;
        return [];
      }
    },
    exa: { search: async () => [] },
    runtime: {
      run: async (input) => {
        runInput = input;
        return {
          text: "我可以先澄清你的问题。",
          usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
        };
      }
    },
    evidenceThreshold: 0.03
  });

  await agent.handle({
    schema_version: "1",
    message_id: "fallback-1",
    umo: "private:fallback",
    chat_type: "private",
    sender_id: "member",
    self_id: "bot-account",
    text: "这个问题有点模糊",
    mentions: [],
    timestamp: 1784860800000,
    is_admin: true,
    owner_takeover_active: false
  });

  assert.equal(ragCalls, 0);
  assert.doesNotMatch(runInput.prompt, /本地证据/);
  assert.deepEqual(runInput.tools.map((tool) => tool.name), ALL_TOOL_NAMES);
});

test("Gateway agent routes current external facts to web search without local RAG", async () => {
  let ragCalls = 0;
  let runInput;
  const agent = new GatewayAgent({
    router: {
      classify: async () => ({
        route: "external_fact",
        confidence: 0.98,
        isFallback: false
      })
    },
    rag: {
      search: async () => {
        ragCalls += 1;
        return [];
      }
    },
    exa: { search: async () => [] },
    runtime: {
      run: async (input) => {
        runInput = input;
        return {
          text: "我会先检索最新来源。",
          usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
        };
      }
    },
    evidenceThreshold: 0.03
  });

  await agent.handle({
    schema_version: "1",
    message_id: "external-1",
    umo: "group:external",
    chat_type: "group",
    group_id: "763898834",
    sender_id: "member",
    self_id: "bot-account",
    text: "今天发布了哪些AI模型？",
    mentions: [],
    timestamp: 1784860800000,
    is_admin: false,
    owner_takeover_active: false
  });

  assert.equal(ragCalls, 0);
  assert.deepEqual(runInput.tools.map((tool) => tool.name), ALL_TOOL_NAMES);
  assert.equal(runInput.requiredTool, "web_search");
  assert.doesNotMatch(runInput.systemPrompt, /已经执行了本地知识检索/);
  assert.match(runInput.systemPrompt, /网页搜索/);
});

test("Gateway agent exposes every tool and requires the routed weather tool", async () => {
  let runInput;
  const agent = new GatewayAgent({
    router: {
      classify: async () => ({
        route: "external_fact",
        confidence: 0.99,
        isFallback: false,
        toolHint: "get_weather"
      })
    },
    rag: { search: async () => [] },
    exa: { search: async () => [] },
    openMeteo: {
      weather: async () => ({ condition: "大致晴朗" }),
      airQuality: async () => ({ usAqi: 50 })
    },
    runtime: {
      run: async (input) => {
        runInput = input;
        const weather = input.tools.find((tool) => tool.name === "get_weather");
        await weather.execute(
          "weather-1",
          { location: "广州", forecast_days: 7 },
          new AbortController().signal
        );
        return {
          text: "广州今天大致晴朗。",
          usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
        };
      }
    },
    evidenceThreshold: 0.03
  });

  const decision = await agent.handle({
    schema_version: "1",
    message_id: "weather-route-1",
    umo: "group:weather",
    chat_type: "group",
    group_id: "763898834",
    sender_id: "member",
    self_id: "bot-account",
    text: "广州未来七天天气如何？",
    mentions: [],
    timestamp: 1784860800000,
    is_admin: false,
    owner_takeover_active: false
  });

  assert.deepEqual(runInput.tools.map((tool) => tool.name), ALL_TOOL_NAMES);
  assert.equal(runInput.requiredTool, "get_weather");
  assert.match(decision.messages[0].text, /https:\/\/open-meteo\.com\//);
});

test("explicit research bypasses intent classification and forces web search", async () => {
  let routerCalls = 0;
  let webCalls = 0;
  let runInput;
  const agent = new GatewayAgent({
    router: {
      classify: async () => {
        routerCalls += 1;
        return { route: "chat_creative", confidence: 1, isFallback: false };
      }
    },
    rag: { search: async () => [] },
    exa: {
      search: async (query, options) => {
        webCalls += 1;
        assert.equal(query, "上海限行新规");
        assert.deepEqual(options, { maxResults: 5 });
        return [{
          title: "官方通告",
          url: "https://example.gov.cn/rules",
          text: "最新限行范围",
          publishedDate: "2026-07-27"
        }];
      }
    },
    runtime: {
      run: async (input) => {
        runInput = input;
        return {
          text: "已检索。",
          usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
        };
      }
    },
    evidenceThreshold: 0.03
  });

  await agent.handle({
    schema_version: "1",
    message_id: "research-1",
    umo: "group:709694410",
    chat_type: "group",
    group_id: "709694410",
    sender_id: "member",
    self_id: "bot-account",
    text: "上海限行新规",
    mentions: [],
    force_route: "external_fact",
    timestamp: 1784860800000,
    is_admin: false,
    owner_takeover_active: false
  });

  assert.equal(routerCalls, 0);
  assert.equal(webCalls, 1);
  assert.deepEqual(runInput.tools.map((tool) => tool.name), ALL_TOOL_NAMES);
  assert.equal(runInput.requiredTool, undefined);
  assert.match(runInput.systemPrompt, /必须调用匹配的实时信息工具/);
  assert.match(runInput.prompt, /https:\/\/example\.gov\.cn\/rules/);
});

test("Gateway agent does not present stored documents as live runtime state", async () => {
  let ragCalls = 0;
  let runInput;
  const agent = new GatewayAgent({
    router: fixedRouter("local_runtime"),
    rag: {
      search: async () => {
        ragCalls += 1;
        return [];
      }
    },
    exa: { search: async () => [] },
    runtime: {
      run: async (input) => {
        runInput = input;
        return {
          text: "我目前没有这项实时状态证据。",
          usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
        };
      }
    },
    evidenceThreshold: 0.03
  });

  await agent.handle({
    schema_version: "1",
    message_id: "runtime-1",
    umo: "private:runtime",
    chat_type: "private",
    sender_id: "admin",
    self_id: "bot-account",
    text: "当前Gateway是否正常？",
    mentions: [],
    timestamp: 1784860800000,
    is_admin: true,
    owner_takeover_active: false
  });

  assert.equal(ragCalls, 0);
  assert.deepEqual(runInput.tools.map((tool) => tool.name), ALL_TOOL_NAMES);
  assert.doesNotMatch(runInput.systemPrompt, /已经执行了本地知识检索/);
  assert.match(runInput.systemPrompt, /实时状态/);
});

test("session reset aborts an in-flight reply before clearing persistent memory", async () => {
  const events = [];
  const audits = [];
  let finishRun;
  const runtime = {
    run: async () => await new Promise((resolve) => {
      finishRun = resolve;
    }),
    abort: () => {
      events.push("abort");
      finishRun({
        text: "不应写回的旧回答",
        usage: { input: 10, output: 5, cacheRead: 0, cacheWrite: 0, totalTokens: 15, cost: {} }
      });
      return 1;
    }
  };
  const memory = {
    context: () => "旧记忆",
    record: () => events.push("record"),
    clear: () => events.push("clear")
  };
  const agent = new GatewayAgent({
    router: fixedRouter("chat_creative"),
    rag: { search: async () => [] },
    exa: { search: async () => [] },
    runtime,
    memory,
    audit: { record: (entry) => audits.push(entry) },
    evidenceThreshold: 0.03
  });
  const event = {
    schema_version: "1",
    message_id: "reset-race-1",
    umo: "group:709694410",
    chat_type: "group",
    group_id: "709694410",
    sender_id: "member",
    self_id: "bot-account",
    text: "慢请求",
    mentions: [],
    timestamp: 1784860800000,
    is_admin: false,
    owner_takeover_active: false
  };

  const pendingReply = agent.handle(event);
  await new Promise((resolve) => setImmediate(resolve));
  const reset = agent.control(event.umo, "reset");

  assert.deepEqual(await pendingReply, {
    action: "no_reply",
    messages: [],
    reason_code: "session_stopped"
  });
  assert.deepEqual(await reset, {
    status: "reset",
    message: "会话记忆已清空"
  });
  assert.deepEqual(events, ["abort", "clear"]);
  assert.deepEqual(
    audits.filter((entry) => entry.event === "gateway_control").map((entry) => ({
      control_action: entry.control_action,
      control_result: entry.control_result
    })),
    [{ control_action: "reset", control_result: "completed" }]
  );
});

test("session stats persist completed router and answer usage while reset retains it", async () => {
  const totals = new Map();
  const usage = {
    add: (sessionId, value) => {
      const current = totals.get(sessionId) ?? {
        requests: 0,
        input: 0,
        output: 0,
        cacheRead: 0,
        cacheWrite: 0
      };
      current.requests += 1;
      current.input += value.input;
      current.output += value.output;
      current.cacheRead += value.cacheRead;
      current.cacheWrite += value.cacheWrite;
      totals.set(sessionId, current);
    },
    get: (sessionId) => totals.get(sessionId),
    clear: (sessionId) => totals.delete(sessionId)
  };
  const agent = new GatewayAgent({
    router: {
      classify: async (_input, sessionId) => {
        usage.add(sessionId, {
          input: 7,
          output: 3,
          cacheRead: 2,
          cacheWrite: 0,
          totalTokens: 12,
          cost: {}
        });
        return {
          route: "chat_creative",
          confidence: 0.99,
          isFallback: false
        };
      }
    },
    rag: { search: async () => [] },
    exa: { search: async () => [] },
    runtime: {
      run: async () => ({
        text: "完成",
        usage: { input: 20, output: 5, cacheRead: 4, cacheWrite: 1, totalTokens: 30, cost: {} }
      })
    },
    memory: { context: () => "", record: () => undefined, clear: () => undefined },
    usage,
    evidenceThreshold: 0.03
  });
  const sessionId = "group:709694410";
  await agent.handle({
    schema_version: "1",
    message_id: "usage-1",
    umo: sessionId,
    chat_type: "group",
    group_id: "709694410",
    sender_id: "member",
    self_id: "bot-account",
    text: "你好",
    mentions: [],
    timestamp: 1784860800000,
    is_admin: false,
    owner_takeover_active: false
  });

  await agent.control(sessionId, "reset");
  assert.deepEqual(await agent.control(sessionId, "stats"), {
    status: "stats",
    message: "调用 2 次；输入 27，缓存读取 6，缓存写入 1，输出 8，总计 42 tokens"
  });
  await agent.control(sessionId, "new");
  assert.deepEqual(await agent.control(sessionId, "stats"), {
    status: "stats",
    message: "当前会话暂无用量记录"
  });
});

test("Gateway agent retrieves evidence before calling the LLM", async () => {
  const order = [];
  let runInput;
  const agent = new GatewayAgent({
    router: fixedRouter(),
    rag: {
      search: async (query, options) => {
        order.push("rag");
        assert.equal(query, "我的服务器CPU是什么？");
        assert.deepEqual(options, { topK: 16 });
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
  const audits = [];
  const agent = new GatewayAgent({
    router: {
      classify: async () => ({
        route: "external_fact",
        confidence: 0.99,
        isFallback: false
      })
    },
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
    audit: { record: (entry) => audits.push(entry) },
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
  assert.equal(audits.filter((entry) => entry.event === "gateway_tool").length, 1);
  const webAudit = audits.find(
    (entry) => entry.event === "gateway_tool" && entry.tool === "web_search"
  );
  assert.ok(webAudit);
  assert.deepEqual(
    {
      tool: webAudit.tool,
      result_count: webAudit.result_count
    },
    { tool: "web_search", result_count: 1 }
  );
  assert.equal(decision.action, "reply");
});

test("RAG tool uses the accepted depth without overflowing tool context", async () => {
  let toolSearchOptions;
  let ragCalls = 0;
  const audits = [];
  const agent = new GatewayAgent({
    router: fixedRouter(),
    rag: {
      search: async (_query, options) => {
        ragCalls += 1;
        if (ragCalls === 1) {
          return [];
        }
        toolSearchOptions = options;
        return Array.from({ length: options.topK }, (_, index) => ({
          id: `chunk-${index}`,
          score: 0.8,
          text: `切片${index}${"X".repeat(700)}`,
          source: `source-${index}.md`,
          kbId: "test"
        }));
      }
    },
    exa: { search: async () => [] },
    runtime: {
      run: async (input) => {
        const tool = input.tools.find((candidate) => candidate.name === "rag_search");
        assert.ok(tool);
        const result = await tool.execute(
          "tool-rag",
          { query: "详细检索" },
          new AbortController().signal
        );
        assert.ok([...result.content[0].text].length <= 6000);
        return {
          text: "检索完成",
          usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
        };
      }
    },
    audit: { record: (entry) => audits.push(entry) },
    evidenceThreshold: 0.2
  });

  await agent.handle({
    schema_version: "1",
    message_id: "rag-depth-1",
    umo: "private:1",
    chat_type: "private",
    sender_id: "1",
    self_id: "bot",
    text: "深入研究",
    mentions: [],
    timestamp: 1784860800000,
    is_admin: true,
    owner_takeover_active: false
  });

  assert.deepEqual(toolSearchOptions, { topK: 16 });
  const toolAudit = audits.find(
    (entry) => entry.event === "gateway_tool" && entry.tool === "rag_search"
  );
  assert.ok(toolAudit);
  assert.equal(toolAudit.result_count, 16);
});

test("Gateway agent injects and records persistent conversation context", async () => {
  const recorded = [];
  const prompts = [];
  const memory = {
    context: () => "[最近对话]\n用户：我的CPU是9470C\n助手：记住了",
    record: (...args) => recorded.push(args)
  };
  const agent = new GatewayAgent({
    router: fixedRouter(),
    rag: { search: async () => [] },
    exa: { search: async () => [] },
    memory,
    runtime: {
      run: async (input) => {
        prompts.push(input.prompt);
        return {
          text: "你的CPU是9470C。",
          usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
        };
      }
    },
    evidenceThreshold: 0.2,
    maxPromptTokens: 200
  });
  const current = {
    schema_version: "1",
    message_id: "memory-1",
    umo: "group:709694410",
    chat_type: "group",
    group_id: "709694410",
    sender_id: "1907483592",
    self_id: "bot-account",
    text: "那我的CPU是什么？",
    mentions: [],
    timestamp: 1784860800000,
    is_admin: true,
    owner_takeover_active: false
  };

  await agent.handle(current);

  assert.match(prompts[0], /我的CPU是9470C/);
  assert.deepEqual(recorded, [[
    "group:709694410",
    "那我的CPU是什么？",
    "你的CPU是9470C。"
  ]]);
  assert.ok([...prompts[0]].length <= 200);
});

test("Gateway agent hard-bounds an oversized current message", async () => {
  let prompt = "";
  const agent = new GatewayAgent({
    router: fixedRouter(),
    rag: { search: async () => [] },
    exa: { search: async () => [] },
    runtime: {
      run: async (input) => {
        prompt = input.prompt;
        return {
          text: "已处理",
          usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
        };
      }
    },
    evidenceThreshold: 0.2,
    maxPromptTokens: 100
  });

  await agent.handle({
    schema_version: "1",
    message_id: "oversized-1",
    umo: "private:1",
    chat_type: "private",
    sender_id: "1",
    self_id: "bot",
    text: `开头${"A".repeat(500)}结尾`,
    mentions: [],
    timestamp: 1784860800000,
    is_admin: true,
    owner_takeover_active: false
  });

  assert.ok([...prompt].length <= 100);
  assert.match(prompt, /开头/);
  assert.match(prompt, /结尾/);
  assert.match(prompt, /已截断/);
});

test("Gateway agent bounds quoted context without dropping the current question", async () => {
  let prompt = "";
  const agent = new GatewayAgent({
    router: fixedRouter(),
    rag: { search: async () => [] },
    exa: { search: async () => [] },
    runtime: {
      run: async (input) => {
        prompt = input.prompt;
        return {
          text: "已处理",
          usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
        };
      }
    },
    evidenceThreshold: 0.2,
    maxPromptTokens: 100
  });

  await agent.handle({
    schema_version: "1",
    message_id: "oversized-quote-1",
    umo: "private:1",
    chat_type: "private",
    sender_id: "1",
    self_id: "bot",
    text: "会好用吗",
    mentions: [],
    reply_context: {
      sender_id: "owner",
      text: `引用开头${"Q".repeat(500)}引用结尾`
    },
    timestamp: 1784860800000,
    is_admin: true,
    owner_takeover_active: false
  });

  assert.ok([...prompt].length <= 100);
  assert.match(prompt, /\[用户问题\]\n会好用吗/);
  assert.match(prompt, /\[引用消息\]/);
});
