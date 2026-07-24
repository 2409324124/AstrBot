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
