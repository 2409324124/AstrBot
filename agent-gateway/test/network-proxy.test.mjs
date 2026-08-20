import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";

import { createOutboundProxyDispatcher } from "../src/network-proxy.ts";

function listen(server) {
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server.address().port)));
}

function close(server) {
  return new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
}

test("outbound proxy routes external requests through the configured HTTP proxy", async () => {
  let proxiedUrl;
  const proxy = http.createServer((request, response) => {
    proxiedUrl = request.url;
    response.writeHead(200, { "content-type": "text/plain" });
    response.end("proxied");
  });
  const port = await listen(proxy);
  const dispatcher = createOutboundProxyDispatcher(`http://127.0.0.1:${port}`);

  const response = await fetch("http://example.test/health", { dispatcher });

  assert.equal(await response.text(), "proxied");
  assert.equal(proxiedUrl, "http://example.test/health");
  await dispatcher.close();
  await close(proxy);
});

test("outbound proxy bypasses local RAG addresses", async () => {
  let proxyCalls = 0;
  const proxy = http.createServer(() => {
    proxyCalls += 1;
  });
  const target = http.createServer((_request, response) => {
    response.writeHead(204);
    response.end();
  });
  const proxyPort = await listen(proxy);
  const targetPort = await listen(target);
  const dispatcher = createOutboundProxyDispatcher(`http://127.0.0.1:${proxyPort}`);

  const response = await fetch(`http://127.0.0.1:${targetPort}/health`, { dispatcher });

  assert.equal(response.status, 204);
  assert.equal(proxyCalls, 0);
  await dispatcher.close();
  await close(target);
  await close(proxy);
});
