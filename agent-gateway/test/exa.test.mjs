import assert from "node:assert/strict";
import test from "node:test";

import { ExaSearchClient } from "../src/exa.ts";

test("Exa search supports an explicit x.com domain boundary", async () => {
  let captured;
  const exa = new ExaSearchClient({
    apiKey: "exa-secret",
    fetch: async (url, init) => {
      captured = { url, init, body: JSON.parse(init.body) };
      return new Response(JSON.stringify({
        results: [{
          title: "模型发布说明",
          url: "https://x.com/example/status/1",
          text: "发布内容",
          publishedDate: "2026-07-24"
        }]
      }), { status: 200, headers: { "content-type": "application/json" } });
    }
  });

  const results = await exa.search("最新模型发布", {
    domains: ["x.com"],
    maxResults: 5
  });

  assert.equal(captured.url, "https://api.exa.ai/search");
  assert.equal(captured.init.headers["x-api-key"], "exa-secret");
  assert.deepEqual(captured.body.includeDomains, ["x.com"]);
  assert.equal(captured.body.numResults, 5);
  assert.deepEqual(results, [{
    title: "模型发布说明",
    url: "https://x.com/example/status/1",
    text: "发布内容",
    publishedDate: "2026-07-24"
  }]);
});
