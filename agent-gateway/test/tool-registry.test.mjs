import assert from "node:assert/strict";
import test from "node:test";

import { createGatewayTools } from "../src/tool-registry.ts";

test("local registry always exposes all common and retrieval tools", async () => {
  const calls = [];
  const tools = createGatewayTools({
    rag: { search: async () => [] },
    exa: { search: async () => [] },
    openMeteo: {
      weather: async (location, days) => ({ location, days, source: "weather" }),
      airQuality: async (location) => ({ location, source: "air" })
    },
    frankfurter: {
      convert: async (amount, from, to) => ({ amount, from, to, source: "fx" })
    },
    timezone: "Asia/Shanghai",
    onToolCall: (entry) => calls.push(entry)
  });

  assert.deepEqual(tools.map((tool) => tool.name), [
    "rag_search",
    "web_search",
    "get_current_time",
    "get_weather",
    "get_air_quality",
    "calculate",
    "convert_units",
    "convert_currency"
  ]);

  const weather = tools.find((tool) => tool.name === "get_weather");
  const weatherResult = await weather.execute(
    "weather-1",
    { location: "广州", forecast_days: 7 },
    new AbortController().signal
  );
  assert.match(weatherResult.content[0].text, /"days":7/);

  const calculator = tools.find((tool) => tool.name === "calculate");
  const calculation = await calculator.execute(
    "calc-1",
    { expression: "6 * 7" },
    new AbortController().signal
  );
  assert.match(calculation.content[0].text, /42/);
  assert.deepEqual(calls.map((entry) => ({ tool: entry.tool, status: entry.status })), [
    { tool: "get_weather", status: "success" },
    { tool: "calculate", status: "success" }
  ]);
});
