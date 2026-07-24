import { randomUUID, timingSafeEqual } from "node:crypto";

import Fastify, { type FastifyInstance } from "fastify";

export type GatewayMessage = {
  type: "text";
  text: string;
};

export type GatewayDecision = {
  action: "reply" | "no_reply";
  messages: GatewayMessage[];
  reason_code: string;
};

export type GatewayResponse = GatewayDecision & {
  trace_id: string;
};

export type DecisionStore = {
  getDecision: (key: string) => GatewayResponse | undefined;
  saveDecision: (key: string, response: GatewayResponse) => void;
};

export type GatewayEvent = {
  schema_version: "1";
  message_id: string;
  umo: string;
  chat_type: "group" | "private";
  group_id?: string;
  sender_id: string;
  self_id: string;
  text: string;
  mentions: string[];
  reply_to_sender_id?: string;
  timestamp: number;
  is_admin: boolean;
  owner_takeover_active: boolean;
};

type AppOptions = {
  eventToken: string;
  handleEvent: (event: GatewayEvent) => Promise<GatewayDecision>;
  decisionStore?: DecisionStore;
};

function bearerMatches(header: string | undefined, expectedToken: string): boolean {
  if (!header?.startsWith("Bearer ")) {
    return false;
  }
  const received = Buffer.from(header.slice(7));
  const expected = Buffer.from(expectedToken);
  return received.length === expected.length && timingSafeEqual(received, expected);
}

export function createApp(options: AppOptions): FastifyInstance {
  const app = Fastify({ logger: false });
  const decisions = new Map<string, Promise<GatewayResponse>>();

  app.post<{ Body: GatewayEvent }>("/v1/events", async (request, reply) => {
    if (!bearerMatches(request.headers.authorization, options.eventToken)) {
      return reply.code(401).send({ error: "unauthorized" });
    }

    const idempotencyKey = `${request.body.self_id}:${request.body.message_id}`;
    const stored = options.decisionStore?.getDecision(idempotencyKey);
    if (stored) {
      return stored;
    }
    let pending = decisions.get(idempotencyKey);
    if (!pending) {
      pending = options
        .handleEvent(request.body)
        .then((decision) => ({
          ...decision,
          trace_id: randomUUID(),
        }))
        .catch((error: unknown) => {
          request.log.error(
            { error_type: error instanceof Error ? error.name : "unknown" },
            "Gateway event handling failed",
          );
          return {
            action: "no_reply" as const,
            messages: [],
            reason_code: "gateway_error",
            trace_id: randomUUID(),
          };
        });
      pending = pending.then((response) => {
        options.decisionStore?.saveDecision(idempotencyKey, response);
        return response;
      });
      decisions.set(idempotencyKey, pending);
    }
    return await pending;
  });

  return app;
}
