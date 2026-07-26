import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { createApp } from "../src/app.ts";
import { SqliteGatewayStore } from "../src/store.ts";

const event = {
  schema_version: "1",
  message_id: "private-1907483592-1",
  umo: "aiocqhttp:FriendMessage:1907483592",
  chat_type: "private",
  sender_id: "1907483592",
  self_id: "bot-account",
  text: "你是谁",
  mentions: [],
  timestamp: 1784860800000,
  is_admin: true,
  owner_takeover_active: false
};

test("authenticated QQ event receives a versioned gateway decision", async () => {
  const app = createApp({
    eventToken: "event-secret",
    handleEvent: async () => ({
      action: "reply",
      messages: [{ type: "text", text: "我是东云bot（ai生成内容）" }],
      reason_code: "explicit_private_request"
    })
  });

  const response = await app.inject({
    method: "POST",
    url: "/v1/events",
    headers: { authorization: "Bearer event-secret" },
    payload: event
  });

  assert.equal(response.statusCode, 200);
  assert.deepEqual(response.json(), {
    action: "reply",
    messages: [{ type: "text", text: "我是东云bot（ai生成内容）" }],
    reason_code: "explicit_private_request",
    trace_id: response.json().trace_id
  });
  assert.match(response.json().trace_id, /^[0-9a-f-]{36}$/);
  await app.close();
});

test("duplicate QQ delivery reuses the first decision without rerunning the agent", async () => {
  let calls = 0;
  const app = createApp({
    eventToken: "event-secret",
    handleEvent: async () => {
      calls += 1;
      return {
        action: "reply",
        messages: [{ type: "text", text: "只生成一次（ai生成内容）" }],
        reason_code: "agent_reply"
      };
    }
  });

  const request = {
    method: "POST",
    url: "/v1/events",
    headers: { authorization: "Bearer event-secret" },
    payload: event
  };
  const first = await app.inject(request);
  const duplicate = await app.inject(request);

  assert.equal(first.statusCode, 200);
  assert.equal(duplicate.statusCode, 200);
  assert.equal(calls, 1);
  assert.deepEqual(duplicate.json(), first.json());
  await app.close();
});

test("agent failure closes silently instead of exposing an AstrBot fallback", async () => {
  const app = createApp({
    eventToken: "event-secret",
    handleEvent: async () => {
      throw new Error("provider secret and internal path");
    }
  });

  const response = await app.inject({
    method: "POST",
    url: "/v1/events",
    headers: { authorization: "Bearer event-secret" },
    payload: { ...event, message_id: "private-1907483592-2" }
  });

  assert.equal(response.statusCode, 200);
  assert.deepEqual(response.json(), {
    action: "no_reply",
    messages: [],
    reason_code: "gateway_error",
    trace_id: response.json().trace_id
  });
  assert.doesNotMatch(response.body, /provider secret|internal path/);
  await app.close();
});

test("idempotency survives a gateway process restart", async () => {
  const directory = await mkdtemp(join(tmpdir(), "agent-gateway-"));
  const databasePath = join(directory, "gateway.sqlite3");
  let calls = 0;
  const handleEvent = async () => {
    calls += 1;
    return {
      action: "reply",
      messages: [{ type: "text", text: "持久化回复（ai生成内容）" }],
      reason_code: "agent_reply"
    };
  };
  const firstStore = new SqliteGatewayStore(databasePath);
  const firstApp = createApp({ eventToken: "event-secret", handleEvent, decisionStore: firstStore });
  const request = {
    method: "POST",
    url: "/v1/events",
    headers: { authorization: "Bearer event-secret" },
    payload: { ...event, message_id: "persistent-1" }
  };
  const first = await firstApp.inject(request);
  await firstApp.close();
  firstStore.close();

  const secondStore = new SqliteGatewayStore(databasePath);
  const secondApp = createApp({ eventToken: "event-secret", handleEvent, decisionStore: secondStore });
  const duplicate = await secondApp.inject(request);

  assert.equal(calls, 1);
  assert.deepEqual(duplicate.json(), first.json());
  await secondApp.close();
  secondStore.close();
  await rm(directory, { recursive: true, force: true });
});

test("admin API atomically updates the active model and group whitelist", async () => {
  const directory = await mkdtemp(join(tmpdir(), "agent-gateway-admin-"));
  const store = new SqliteGatewayStore(join(directory, "gateway.sqlite3"));
  const models = [];
  const app = createApp({
    eventToken: "event-secret",
    adminToken: "admin-secret",
    handleEvent: async () => ({ action: "reply", messages: [], reason_code: "called" }),
    decisionStore: store,
    adminStore: store,
    initialAdminConfig: { model: "deepseek-v4-pro", groupWhitelist: ["709694410"] },
    onModelChange: async (model) => models.push(model)
  });

  const unauthorized = await app.inject({ method: "GET", url: "/v1/admin/config" });
  assert.equal(unauthorized.statusCode, 401);

  const changed = await app.inject({
    method: "PATCH",
    url: "/v1/admin/config",
    headers: { authorization: "Bearer admin-secret" },
    payload: {
      model: "qwen3.5-27b-local",
      group_whitelist: ["709694410", "89589336", "709694410"]
    }
  });
  assert.equal(changed.statusCode, 200);
  assert.deepEqual(changed.json(), {
    model: "qwen3.5-27b-local",
    group_whitelist: ["709694410", "89589336"]
  });
  assert.deepEqual(models, ["qwen3.5-27b-local"]);

  const outside = await app.inject({
    method: "POST",
    url: "/v1/events",
    headers: { authorization: "Bearer event-secret" },
    payload: {
      ...event,
      message_id: "outside-group",
      chat_type: "group",
      group_id: "1043304585"
    }
  });
  assert.equal(outside.json().action, "no_reply");
  assert.equal(outside.json().reason_code, "group_not_whitelisted");

  store.close();
  await app.close();
  await rm(directory, { recursive: true, force: true });
});

test("event API rejects malformed payloads before calling the agent", async () => {
  let calls = 0;
  const app = createApp({
    eventToken: "event-secret",
    handleEvent: async () => {
      calls += 1;
      return { action: "reply", messages: [], reason_code: "called" };
    }
  });

  const response = await app.inject({
    method: "POST",
    url: "/v1/events",
    headers: { authorization: "Bearer event-secret" },
    payload: { ...event, message_id: "", text: 42 }
  });

  assert.equal(response.statusCode, 400);
  assert.equal(calls, 0);
  await app.close();
});

test("event API rejects blank text before calling the agent", async () => {
  let calls = 0;
  const app = createApp({
    eventToken: "event-secret",
    handleEvent: async () => {
      calls += 1;
      return { action: "reply", messages: [], reason_code: "called" };
    }
  });

  const response = await app.inject({
    method: "POST",
    url: "/v1/events",
    headers: { authorization: "Bearer event-secret" },
    payload: { ...event, message_id: "blank-private", text: "  \n " }
  });

  assert.equal(response.statusCode, 400);
  assert.equal(calls, 0);
  await app.close();
});

test("event API rejects oversized quoted context before calling the agent", async () => {
  let calls = 0;
  const app = createApp({
    eventToken: "event-secret",
    handleEvent: async () => {
      calls += 1;
      return { action: "reply", messages: [], reason_code: "called" };
    }
  });

  const response = await app.inject({
    method: "POST",
    url: "/v1/events",
    headers: { authorization: "Bearer event-secret" },
    payload: {
      ...event,
      message_id: "oversized-quote",
      reply_context: { sender_id: "owner", text: "x".repeat(2001) }
    }
  });

  assert.equal(response.statusCode, 400);
  assert.equal(calls, 0);
  await app.close();
});

test("authenticated session reset is handled without entering the event agent", async () => {
  let eventCalls = 0;
  const controls = [];
  const app = createApp({
    eventToken: "event-secret",
    initialAdminConfig: {
      model: "deepseek-v4-pro",
      groupWhitelist: ["709694410"]
    },
    handleEvent: async () => {
      eventCalls += 1;
      return { action: "reply", messages: [], reason_code: "called" };
    },
    handleSessionControl: async (request) => {
      controls.push(request);
      return { status: "reset", message: "会话记忆已清空" };
    }
  });

  const response = await app.inject({
    method: "POST",
    url: "/v1/sessions/control",
    headers: { authorization: "Bearer event-secret" },
    payload: {
      schema_version: "1",
      session_id: "aiocqhttp:GroupMessage:709694410",
      action: "reset",
      chat_type: "group",
      group_id: "709694410",
      is_admin: false
    }
  });

  assert.equal(response.statusCode, 200);
  assert.deepEqual(response.json(), {
    status: "reset",
    message: "会话记忆已清空"
  });
  assert.deepEqual(controls, [{
    schema_version: "1",
    session_id: "aiocqhttp:GroupMessage:709694410",
    action: "reset",
    chat_type: "group",
    group_id: "709694410",
    is_admin: false
  }]);
  assert.equal(eventCalls, 0);
  await app.close();
});

test("session controls reject untrusted private and non-whitelisted group callers", async () => {
  let calls = 0;
  const app = createApp({
    eventToken: "event-secret",
    initialAdminConfig: {
      model: "deepseek-v4-pro",
      groupWhitelist: ["709694410"]
    },
    handleEvent: async () => ({ action: "no_reply", messages: [], reason_code: "unused" }),
    handleSessionControl: async (request) => {
      calls += 1;
      return { status: request.action, message: "ok" };
    }
  });
  const base = {
    schema_version: "1",
    session_id: "session",
    action: "stop",
    chat_type: "private",
    is_admin: false
  };

  const unauthorized = await app.inject({
    method: "POST",
    url: "/v1/sessions/control",
    payload: base
  });
  const privateMember = await app.inject({
    method: "POST",
    url: "/v1/sessions/control",
    headers: { authorization: "Bearer event-secret" },
    payload: base
  });
  const outsideGroup = await app.inject({
    method: "POST",
    url: "/v1/sessions/control",
    headers: { authorization: "Bearer event-secret" },
    payload: {
      ...base,
      chat_type: "group",
      group_id: "1043304585",
      is_admin: true
    }
  });

  assert.equal(unauthorized.statusCode, 401);
  assert.equal(privateMember.statusCode, 403);
  assert.equal(outsideGroup.statusCode, 403);
  assert.equal(calls, 0);
  await app.close();
});
