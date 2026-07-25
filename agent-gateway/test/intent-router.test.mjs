import assert from "node:assert/strict";
import test from "node:test";

import { RuntimeIntentRouter } from "../src/intent-router.ts";

test("Intent router returns a validated semantic route without tools or history", async () => {
  let runInput;
  const router = new RuntimeIntentRouter({
    runtime: {
      run: async (input) => {
        runInput = input;
        return {
          text: '{"route":"chat_creative","confidence":0.95}',
          usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
        };
      }
    }
  });

  const decision = await router.classify("我話今日中午食啲乜");

  assert.deepEqual(decision, {
    route: "chat_creative",
    confidence: 0.95,
    isFallback: false
  });
  assert.equal(runInput.tools.length, 0);
  assert.match(runInput.systemPrompt, /semantic meaning/i);
  assert.match(runInput.prompt, /<untrusted_user_message>/);
  assert.doesNotMatch(runInput.prompt, /对话记忆|本地证据/);
});

test("Intent router degrades invalid model output to an untrusted fallback", async () => {
  const router = new RuntimeIntentRouter({
    runtime: {
      run: async () => ({
        text: "我认为这是闲聊",
        usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
      })
    }
  });

  assert.deepEqual(await router.classify("随便聊聊"), {
    route: "technical_concept",
    confidence: 0,
    isFallback: true
  });
});

test("Intent router accepts one JSON object wrapped by model formatting", async () => {
  const router = new RuntimeIntentRouter({
    runtime: {
      run: async () => ({
        text: '```json\n{"route":"local_knowledge","confidence":0.91}\n```',
        usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: {} }
      })
    }
  });

  assert.deepEqual(await router.classify("本地资料里的9470C是什么？"), {
    route: "local_knowledge",
    confidence: 0.91,
    isFallback: false
  });
});
