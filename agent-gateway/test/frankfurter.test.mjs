import assert from "node:assert/strict";
import test from "node:test";

import { FrankfurterClient } from "../src/frankfurter.ts";

test("Frankfurter converts an amount with the latest reference rate", async () => {
  let requestedUrl;
  const client = new FrankfurterClient({
    fetch: async (input) => {
      requestedUrl = new URL(input);
      return new Response(JSON.stringify({
        date: "2026-07-28",
        base: "USD",
        quote: "CNY",
        rate: 7.1832
      }), { status: 200 });
    }
  });

  const result = await client.convert(12.5, "usd", "cny");

  assert.equal(requestedUrl.pathname, "/v2/rate/USD/CNY");
  assert.deepEqual(result, {
    amount: 12.5,
    from: "USD",
    to: "CNY",
    rate: 7.1832,
    convertedAmount: 89.79,
    date: "2026-07-28",
    note: "欧洲央行参考汇率；不代表银行或支付平台的实时成交价。",
    source: "https://frankfurter.dev/"
  });
});

test("Frankfurter rejects invalid currency codes without making a request", async () => {
  let called = false;
  const client = new FrankfurterClient({
    fetch: async () => {
      called = true;
      throw new Error("unexpected request");
    }
  });

  await assert.rejects(() => client.convert(1, "US", "CNY"), /currency code/i);
  assert.equal(called, false);
});
