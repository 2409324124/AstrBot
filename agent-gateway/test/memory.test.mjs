import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { ConversationMemory } from "../src/memory.ts";
import { SqliteGatewayStore } from "../src/store.ts";

test("conversation memory survives restart and stays isolated by UMO", async () => {
  const directory = await mkdtemp(join(tmpdir(), "gateway-memory-"));
  const path = join(directory, "gateway.sqlite3");
  const firstStore = new SqliteGatewayStore(path);
  const first = new ConversationMemory({ store: firstStore, tokenBudget: 200 });
  first.record("group:1", "我的CPU是9470C", "记住了");
  firstStore.close();

  const secondStore = new SqliteGatewayStore(path);
  const second = new ConversationMemory({ store: secondStore, tokenBudget: 200 });
  assert.match(second.context("group:1"), /9470C/);
  assert.equal(second.context("group:2"), "");
  secondStore.close();
  await rm(directory, { recursive: true, force: true });
});

test("conversation memory rolls old turns into a bounded summary", async () => {
  const directory = await mkdtemp(join(tmpdir(), "gateway-memory-"));
  const store = new SqliteGatewayStore(join(directory, "gateway.sqlite3"));
  const memory = new ConversationMemory({ store, tokenBudget: 90 });

  for (let index = 0; index < 12; index += 1) {
    memory.record(
      "group:1",
      `用户问题${index}与额外内容`,
      `助手回答${index}与额外内容`,
    );
  }

  const context = memory.context("group:1");
  assert.match(context, /\[历史摘要\]/);
  assert.match(context, /\[最近对话\]/);
  assert.ok([...context].length <= 90);
  assert.match(context, /用户问题11/);
  store.close();
  await rm(directory, { recursive: true, force: true });
});
