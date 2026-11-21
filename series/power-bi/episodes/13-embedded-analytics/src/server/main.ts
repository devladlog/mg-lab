import path from "node:path";
import { fileURLToPath } from "node:url";
import { createApp, defaultStaticFiles, EmbedService } from "./app.js";
import { loadConfig } from "./config.js";
import { createTokenProvider } from "./msal.js";
import { PowerBiClient } from "./powerbi.js";

const cfg = loadConfig(process.env);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const client = new PowerBiClient(fetch, createTokenProvider(cfg));
const server = createApp(new EmbedService(client, cfg), defaultStaticFiles(root), (m) => console.error(m));
server.listen(cfg.port, "127.0.0.1", () => console.log(`Contoso embed app on http://localhost:${cfg.port}/`));
