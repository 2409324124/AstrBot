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

export type GatewayAdminConfig = {
  model: string;
  groupWhitelist: string[];
};

export type AdminStore = {
  getAdminConfig: () => GatewayAdminConfig | undefined;
  saveAdminConfig: (config: GatewayAdminConfig) => void;
};

export type SessionControlAction = "new" | "reset" | "stop" | "stats";

export type SessionControlRequest = {
  schema_version: "1";
  session_id: string;
  action: SessionControlAction;
  chat_type: "group" | "private";
  group_id?: string;
  is_admin: boolean;
};

export type SessionControlResponse = {
  status: SessionControlAction;
  message: string;
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
  reply_context?: {
    sender_id: string;
    text: string;
  };
  force_route?: "external_fact";
  timestamp: number;
  is_admin: boolean;
  owner_takeover_active: boolean;
};

function isReplyContext(
  value: unknown,
): value is NonNullable<GatewayEvent["reply_context"]> {
  if (!value || typeof value !== "object") {
    return false;
  }
  const context = value as { sender_id?: unknown; text?: unknown };
  return (
    typeof context.sender_id === "string" &&
    context.sender_id.length <= 128 &&
    typeof context.text === "string" &&
    context.text.trim().length > 0 &&
    [...context.text].length <= 2000
  );
}

type AppOptions = {
  eventToken: string;
  adminToken?: string;
  handleEvent: (event: GatewayEvent) => Promise<GatewayDecision>;
  decisionStore?: DecisionStore;
  adminStore?: AdminStore;
  initialAdminConfig?: GatewayAdminConfig;
  onModelChange?: (model: string) => Promise<void> | void;
  handleSessionControl?: (
    request: SessionControlRequest,
  ) => Promise<SessionControlResponse>;
};

function bearerMatches(header: string | undefined, expectedToken: string): boolean {
  if (!header?.startsWith("Bearer ")) {
    return false;
  }
  const received = Buffer.from(header.slice(7));
  const expected = Buffer.from(expectedToken);
  return received.length === expected.length && timingSafeEqual(received, expected);
}

function isGatewayEvent(value: unknown): value is GatewayEvent {
  if (!value || typeof value !== "object") {
    return false;
  }
  const event = value as Partial<GatewayEvent>;
  return (
    event.schema_version === "1" &&
    typeof event.message_id === "string" &&
    event.message_id.length > 0 &&
    typeof event.umo === "string" &&
    event.umo.length > 0 &&
    (event.chat_type === "group" || event.chat_type === "private") &&
    (event.chat_type !== "group" ||
      (typeof event.group_id === "string" && event.group_id.length > 0)) &&
    typeof event.sender_id === "string" &&
    typeof event.self_id === "string" &&
    typeof event.text === "string" &&
    event.text.trim().length > 0 &&
    Array.isArray(event.mentions) &&
    event.mentions.every((mention) => typeof mention === "string") &&
    (event.reply_context === undefined || isReplyContext(event.reply_context)) &&
    (event.force_route === undefined || event.force_route === "external_fact") &&
    typeof event.timestamp === "number" &&
    Number.isFinite(event.timestamp) &&
    typeof event.is_admin === "boolean" &&
    typeof event.owner_takeover_active === "boolean"
  );
}

function normalizeAdminConfig(value: unknown): GatewayAdminConfig | undefined {
  if (!value || typeof value !== "object") {
    return undefined;
  }
  const input = value as {
    model?: unknown;
    group_whitelist?: unknown;
  };
  if (
    typeof input.model !== "string" ||
    !input.model.trim() ||
    input.model.length > 128 ||
    !Array.isArray(input.group_whitelist) ||
    !input.group_whitelist.every(
      (group) => typeof group === "string" && /^\d{5,20}$/u.test(group),
    )
  ) {
    return undefined;
  }
  return {
    model: input.model.trim(),
    groupWhitelist: [...new Set(input.group_whitelist)],
  };
}

function isSessionControlRequest(value: unknown): value is SessionControlRequest {
  if (!value || typeof value !== "object") {
    return false;
  }
  const request = value as Partial<SessionControlRequest>;
  return (
    request.schema_version === "1" &&
    typeof request.session_id === "string" &&
    request.session_id.length > 0 &&
    request.session_id.length <= 512 &&
    ["new", "reset", "stop", "stats"].includes(request.action ?? "") &&
    (request.chat_type === "group" || request.chat_type === "private") &&
    (request.chat_type !== "group" ||
      (typeof request.group_id === "string" && /^\d{5,20}$/u.test(request.group_id))) &&
    typeof request.is_admin === "boolean"
  );
}

export function createApp(options: AppOptions): FastifyInstance {
  const app = Fastify({ logger: false });
  const decisions = new Map<string, Promise<GatewayResponse>>();
  let adminConfig =
    options.adminStore?.getAdminConfig() ?? options.initialAdminConfig;

  if (options.adminToken && adminConfig) {
    app.get("/v1/admin/config", async (request, reply) => {
      if (!bearerMatches(request.headers.authorization, options.adminToken!)) {
        return reply.code(401).send({ error: "unauthorized" });
      }
      return {
        model: adminConfig!.model,
        group_whitelist: adminConfig!.groupWhitelist,
      };
    });

    app.patch<{ Body: unknown }>("/v1/admin/config", async (request, reply) => {
      if (!bearerMatches(request.headers.authorization, options.adminToken!)) {
        return reply.code(401).send({ error: "unauthorized" });
      }
      const next = normalizeAdminConfig(request.body);
      if (!next) {
        return reply.code(400).send({ error: "invalid_admin_config" });
      }
      if (next.model !== adminConfig!.model) {
        await options.onModelChange?.(next.model);
      }
      options.adminStore?.saveAdminConfig(next);
      adminConfig = next;
      return {
        model: next.model,
        group_whitelist: next.groupWhitelist,
      };
    });
  }

  const handleSessionControl = options.handleSessionControl;
  if (handleSessionControl) {
    app.post<{ Body: unknown }>("/v1/sessions/control", async (request, reply) => {
      if (!bearerMatches(request.headers.authorization, options.eventToken)) {
        return reply.code(401).send({ error: "unauthorized" });
      }
      if (!isSessionControlRequest(request.body)) {
        return reply.code(400).send({ error: "invalid_session_control" });
      }
      const control = request.body;
      const allowed =
        control.chat_type === "private"
          ? control.is_admin
          : Boolean(
              adminConfig?.groupWhitelist.includes(control.group_id!),
            );
      if (!allowed) {
        return reply.code(403).send({ error: "session_control_forbidden" });
      }
      return await handleSessionControl(control);
    });
  }

  app.post<{ Body: unknown }>("/v1/events", async (request, reply) => {
    if (!bearerMatches(request.headers.authorization, options.eventToken)) {
      return reply.code(401).send({ error: "unauthorized" });
    }
    if (!isGatewayEvent(request.body)) {
      return reply.code(400).send({ error: "invalid_event" });
    }
    const event = request.body;

    const idempotencyKey = `${event.self_id}:${event.message_id}`;
    const stored = options.decisionStore?.getDecision(idempotencyKey);
    if (stored) {
      return stored;
    }
    let pending = decisions.get(idempotencyKey);
    if (!pending) {
      if (
        event.chat_type === "group" &&
        adminConfig &&
        !adminConfig.groupWhitelist.includes(event.group_id!)
      ) {
        const response: GatewayResponse = {
          action: "no_reply",
          messages: [],
          reason_code: "group_not_whitelisted",
          trace_id: randomUUID(),
        };
        options.decisionStore?.saveDecision(idempotencyKey, response);
        return response;
      }
      pending = options
        .handleEvent(event)
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
