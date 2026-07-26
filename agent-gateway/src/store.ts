import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { DatabaseSync } from "node:sqlite";

import type {
  AdminStore,
  DecisionStore,
  GatewayAdminConfig,
  GatewayResponse,
} from "./app.ts";
import type { SessionUsage, UsagePort } from "./gateway-agent.ts";
import type { ConversationState, ConversationStore } from "./memory.ts";

export class SqliteGatewayStore
  implements DecisionStore, AdminStore, ConversationStore, UsagePort
{
  readonly #database: DatabaseSync;

  constructor(path: string) {
    mkdirSync(dirname(path), { recursive: true });
    this.#database = new DatabaseSync(path);
    this.#database.exec("PRAGMA journal_mode=WAL");
    this.#database.exec("PRAGMA synchronous=NORMAL");
    this.#database.exec(`
      CREATE TABLE IF NOT EXISTS event_decisions (
        idempotency_key TEXT PRIMARY KEY,
        response_json TEXT NOT NULL,
        created_at INTEGER NOT NULL
      ) STRICT
    `);
    this.#database.exec(`
      CREATE TABLE IF NOT EXISTS conversation_state (
        session_id TEXT PRIMARY KEY,
        state_json TEXT NOT NULL,
        updated_at INTEGER NOT NULL
      ) STRICT
    `);
    this.#database.exec(`
      CREATE TABLE IF NOT EXISTS gateway_settings (
        setting_key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at INTEGER NOT NULL
      ) STRICT
    `);
    this.#database.exec(`
      CREATE TABLE IF NOT EXISTS session_usage (
        session_id TEXT PRIMARY KEY,
        requests INTEGER NOT NULL,
        input_tokens INTEGER NOT NULL,
        output_tokens INTEGER NOT NULL,
        cache_read_tokens INTEGER NOT NULL,
        cache_write_tokens INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
      ) STRICT
    `);
  }

  getDecision(key: string): GatewayResponse | undefined {
    const row = this.#database
      .prepare(
        "SELECT response_json FROM event_decisions WHERE idempotency_key = ?",
      )
      .get(key) as { response_json: string } | undefined;
    return row ? (JSON.parse(row.response_json) as GatewayResponse) : undefined;
  }

  saveDecision(key: string, response: GatewayResponse): void {
    this.#database
      .prepare(
        `INSERT OR IGNORE INTO event_decisions
         (idempotency_key, response_json, created_at) VALUES (?, ?, ?)`,
      )
      .run(key, JSON.stringify(response), Date.now());
  }

  getAdminConfig(): GatewayAdminConfig | undefined {
    const row = this.#database
      .prepare(
        "SELECT value_json FROM gateway_settings WHERE setting_key = 'admin_config'",
      )
      .get() as { value_json: string } | undefined;
    return row
      ? (JSON.parse(row.value_json) as GatewayAdminConfig)
      : undefined;
  }

  saveAdminConfig(config: GatewayAdminConfig): void {
    this.#database
      .prepare(
        `INSERT INTO gateway_settings (setting_key, value_json, updated_at)
         VALUES ('admin_config', ?, ?)
         ON CONFLICT(setting_key) DO UPDATE SET
           value_json = excluded.value_json,
           updated_at = excluded.updated_at`,
      )
      .run(JSON.stringify(config), Date.now());
  }

  getConversation(sessionId: string): ConversationState | undefined {
    const row = this.#database
      .prepare(
        "SELECT state_json FROM conversation_state WHERE session_id = ?",
      )
      .get(sessionId) as { state_json: string } | undefined;
    return row ? (JSON.parse(row.state_json) as ConversationState) : undefined;
  }

  saveConversation(sessionId: string, state: ConversationState): void {
    this.#database
      .prepare(
        `INSERT INTO conversation_state (session_id, state_json, updated_at)
         VALUES (?, ?, ?)
         ON CONFLICT(session_id) DO UPDATE SET
           state_json = excluded.state_json,
           updated_at = excluded.updated_at`,
      )
      .run(sessionId, JSON.stringify(state), Date.now());
  }

  deleteConversation(sessionId: string): void {
    this.#database
      .prepare("DELETE FROM conversation_state WHERE session_id = ?")
      .run(sessionId);
  }

  add(
    sessionId: string,
    usage: {
      input: number;
      output: number;
      cacheRead: number;
      cacheWrite: number;
    },
  ): void {
    this.#database
      .prepare(
        `INSERT INTO session_usage (
           session_id, requests, input_tokens, output_tokens,
           cache_read_tokens, cache_write_tokens, updated_at
         ) VALUES (?, 1, ?, ?, ?, ?, ?)
         ON CONFLICT(session_id) DO UPDATE SET
           requests = requests + 1,
           input_tokens = input_tokens + excluded.input_tokens,
           output_tokens = output_tokens + excluded.output_tokens,
           cache_read_tokens = cache_read_tokens + excluded.cache_read_tokens,
           cache_write_tokens = cache_write_tokens + excluded.cache_write_tokens,
           updated_at = excluded.updated_at`,
      )
      .run(
        sessionId,
        usage.input,
        usage.output,
        usage.cacheRead,
        usage.cacheWrite,
        Date.now(),
      );
  }

  get(sessionId: string): SessionUsage | undefined {
    const row = this.#database
      .prepare(
        `SELECT requests, input_tokens, output_tokens,
                cache_read_tokens, cache_write_tokens
         FROM session_usage WHERE session_id = ?`,
      )
      .get(sessionId) as
      | {
          requests: number;
          input_tokens: number;
          output_tokens: number;
          cache_read_tokens: number;
          cache_write_tokens: number;
        }
      | undefined;
    return row
      ? {
          requests: row.requests,
          input: row.input_tokens,
          output: row.output_tokens,
          cacheRead: row.cache_read_tokens,
          cacheWrite: row.cache_write_tokens,
        }
      : undefined;
  }

  clear(sessionId: string): void {
    this.#database
      .prepare("DELETE FROM session_usage WHERE session_id = ?")
      .run(sessionId);
  }

  close(): void {
    this.#database.close();
  }
}
