import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { DatabaseSync } from "node:sqlite";

import type { DecisionStore, GatewayResponse } from "./app.ts";

export class SqliteGatewayStore implements DecisionStore {
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

  close(): void {
    this.#database.close();
  }
}
