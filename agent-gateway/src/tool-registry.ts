import type { AgentTool } from "@earendil-works/pi-agent-core";
import { Type } from "typebox";

import { calculateExpression, convertUnits } from "./calculator.ts";
import type { ExaSearchResult } from "./exa.ts";
import type { RagHit } from "./rag.ts";

export type GatewayToolName =
  | "rag_search"
  | "web_search"
  | "get_current_time"
  | "get_weather"
  | "get_air_quality"
  | "calculate"
  | "convert_units"
  | "convert_currency";

type ToolRegistryOptions = {
  rag: {
    search: (query: string, options: { topK: number }) => Promise<RagHit[]>;
  };
  exa: {
    search: (
      query: string,
      options: { domains?: string[]; maxResults: number },
    ) => Promise<ExaSearchResult[]>;
  };
  openMeteo: {
    weather: (location: string, forecastDays: number) => Promise<unknown>;
    airQuality: (location: string) => Promise<unknown>;
  };
  frankfurter: {
    convert: (
      amount: number,
      from: string,
      to: string,
    ) => Promise<unknown>;
  };
  timezone: string;
  onToolCall?: (entry: {
    tool: GatewayToolName;
    status: "success" | "error";
    durationMs: number;
    resultCount?: number;
  }) => void;
};

/**
 * Creates the complete local tool registry for one Gateway request.
 *
 * @param options Service ports, default timezone, and audit callback.
 * @returns All tools that should be visible to the Pi runtime.
 */
export function createGatewayTools(options: ToolRegistryOptions): AgentTool[] {
  const audited = async <T>(
    tool: GatewayToolName,
    operation: () => Promise<T> | T,
    resultCount?: (result: T) => number,
  ): Promise<T> => {
    const startedAt = Date.now();
    try {
      const result = await operation();
      options.onToolCall?.({
        tool,
        status: "success",
        durationMs: Date.now() - startedAt,
        ...(resultCount ? { resultCount: resultCount(result) } : {}),
      });
      return result;
    } catch (error) {
      options.onToolCall?.({
        tool,
        status: "error",
        durationMs: Date.now() - startedAt,
      });
      throw error;
    }
  };

  const ragParameters = Type.Object({
    query: Type.String({ minLength: 1 }),
    top_k: Type.Optional(Type.Integer({ minimum: 1, maximum: 24 })),
  });
  const ragTool: AgentTool<typeof ragParameters> = {
    name: "rag_search",
    label: "RAG Search",
    description: "Search the local persistent knowledge base",
    parameters: ragParameters,
    execute: async (_toolCallId, params) => {
      const hits = await audited(
        "rag_search",
        async () =>
          await options.rag.search(params.query, {
            topK: params.top_k ?? 16,
          }),
        (results) => results.length,
      );
      const evidence = hits
        .map(
          (hit, index) =>
            `[${index + 1}] ${hit.text}\n来源: ${hit.source}`,
        )
        .join("\n\n");
      return {
        content: [
          {
            type: "text",
            text: [...evidence].slice(0, 6000).join(""),
          },
        ],
        details: { hitCount: hits.length },
      };
    },
  };

  const webParameters = Type.Object({
    query: Type.String({ minLength: 1 }),
    domains: Type.Optional(
      Type.Array(Type.String({ minLength: 1 }), { maxItems: 8 }),
    ),
    max_results: Type.Optional(Type.Integer({ minimum: 1, maximum: 8 })),
  });
  const webTool: AgentTool<typeof webParameters> = {
    name: "web_search",
    label: "Web Search",
    description:
      "Search current web information. Use domains=['x.com'] for X/Twitter.",
    parameters: webParameters,
    execute: async (_toolCallId, params) => {
      const results = await audited(
        "web_search",
        async () =>
          await options.exa.search(params.query, {
            ...(params.domains ? { domains: params.domains } : {}),
            maxResults: params.max_results ?? 5,
          }),
        (entries) => entries.length,
      );
      return {
        content: [
          {
            type: "text",
            text: results
              .map(
                (result, index) =>
                  `[${index + 1}] ${result.title}\n${result.url}\n${result.text}`,
              )
              .join("\n\n"),
          },
        ],
        details: { resultCount: results.length },
      };
    },
  };

  const timeParameters = Type.Object({
    timezone: Type.Optional(
      Type.String({
        minLength: 1,
        maxLength: 100,
        description: "IANA timezone, for example Asia/Shanghai",
      }),
    ),
  });
  const timeTool: AgentTool<typeof timeParameters> = {
    name: "get_current_time",
    label: "Current Time",
    description: "Get the current date and time in an IANA timezone",
    parameters: timeParameters,
    execute: async (_toolCallId, params) => {
      const result = await audited("get_current_time", () => {
        const timezone = params.timezone?.trim() || options.timezone;
        const now = new Date();
        const formatted = new Intl.DateTimeFormat("zh-CN", {
          timeZone: timezone,
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          weekday: "long",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hourCycle: "h23",
        }).format(now);
        return { timezone, formatted, unixMilliseconds: now.getTime() };
      });
      return {
        content: [{ type: "text", text: JSON.stringify(result) }],
        details: result,
      };
    },
  };

  const weatherParameters = Type.Object({
    location: Type.String({ minLength: 1, maxLength: 100 }),
    forecast_days: Type.Optional(Type.Integer({ minimum: 1, maximum: 7 })),
  });
  const weatherTool: AgentTool<typeof weatherParameters> = {
    name: "get_weather",
    label: "Weather",
    description: "Get current weather and up to seven forecast days",
    parameters: weatherParameters,
    execute: async (_toolCallId, params) => {
      const result = await audited(
        "get_weather",
        async () =>
          await options.openMeteo.weather(
            params.location,
            params.forecast_days ?? 7,
          ),
      );
      return {
        content: [{ type: "text", text: JSON.stringify(result) }],
        details: result,
      };
    },
  };

  const airQualityParameters = Type.Object({
    location: Type.String({ minLength: 1, maxLength: 100 }),
  });
  const airQualityTool: AgentTool<typeof airQualityParameters> = {
    name: "get_air_quality",
    label: "Air Quality",
    description: "Get current US AQI and pollutant measurements",
    parameters: airQualityParameters,
    execute: async (_toolCallId, params) => {
      const result = await audited(
        "get_air_quality",
        async () => await options.openMeteo.airQuality(params.location),
      );
      return {
        content: [{ type: "text", text: JSON.stringify(result) }],
        details: result,
      };
    },
  };

  const calculateParameters = Type.Object({
    expression: Type.String({ minLength: 1, maxLength: 300 }),
  });
  const calculateTool: AgentTool<typeof calculateParameters> = {
    name: "calculate",
    label: "Calculator",
    description: "Evaluate restricted scalar arithmetic and common functions",
    parameters: calculateParameters,
    execute: async (_toolCallId, params) => {
      const result = await audited("calculate", () => ({
        expression: params.expression,
        result: calculateExpression(params.expression),
      }));
      return {
        content: [{ type: "text", text: JSON.stringify(result) }],
        details: result,
      };
    },
  };

  const unitsParameters = Type.Object({
    value: Type.Number(),
    from: Type.String({ minLength: 1, maxLength: 50 }),
    to: Type.String({ minLength: 1, maxLength: 50 }),
  });
  const unitsTool: AgentTool<typeof unitsParameters> = {
    name: "convert_units",
    label: "Unit Conversion",
    description: "Convert a value between compatible physical units",
    parameters: unitsParameters,
    execute: async (_toolCallId, params) => {
      const result = await audited("convert_units", () =>
        convertUnits(params.value, params.from, params.to),
      );
      return {
        content: [{ type: "text", text: JSON.stringify(result) }],
        details: result,
      };
    },
  };

  const currencyParameters = Type.Object({
    amount: Type.Number(),
    from: Type.String({ minLength: 3, maxLength: 3 }),
    to: Type.String({ minLength: 3, maxLength: 3 }),
  });
  const currencyTool: AgentTool<typeof currencyParameters> = {
    name: "convert_currency",
    label: "Currency Conversion",
    description: "Convert currencies using Frankfurter reference rates",
    parameters: currencyParameters,
    execute: async (_toolCallId, params) => {
      const result = await audited(
        "convert_currency",
        async () =>
          await options.frankfurter.convert(params.amount, params.from, params.to),
      );
      return {
        content: [{ type: "text", text: JSON.stringify(result) }],
        details: result,
      };
    },
  };

  return [
    ragTool,
    webTool,
    timeTool,
    weatherTool,
    airQualityTool,
    calculateTool,
    unitsTool,
    currencyTool,
  ];
}
