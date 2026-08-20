import { EnvHttpProxyAgent, setGlobalDispatcher } from "undici";

const LOCAL_RAG_NO_PROXY = "qdrant,embedding-server,localhost,127.0.0.1,::1";

export function createOutboundProxyDispatcher(proxyUrl: string): EnvHttpProxyAgent {
  return new EnvHttpProxyAgent({
    httpProxy: proxyUrl,
    httpsProxy: proxyUrl,
    noProxy: LOCAL_RAG_NO_PROXY,
  });
}

export function installOutboundProxy(proxyUrl: string | undefined): void {
  if (!proxyUrl) {
    return;
  }
  setGlobalDispatcher(createOutboundProxyDispatcher(proxyUrl));
}
