import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import type { Config } from "./config.js";
import { buildIdentity, IdentityError } from "./identity.js";
import { APP_USERS, findUser, upnFor } from "./lab-users.js";
import { PowerBiApiError, type PowerBiClient, type ReportInfo } from "./powerbi.js";

export interface EmbedInfo {
  reportId: string;
  embedUrl: string;
  accessToken: string;
  expiration: string;
  user: string;
  roles: string[];
}

export class UnknownUserError extends Error {}

/**
 * The whole point of embed for your customers: the server decides the identity, the browser never does.
 * The alias comes from the app's own session (here a dropdown); roles come from the server's table, never from the request.
 */
export class EmbedService {
  private report?: Promise<ReportInfo>;

  constructor(
    private readonly client: Pick<PowerBiClient, "getReport" | "generateEmbedToken">,
    private readonly cfg: Pick<Config, "workspaceId" | "reportId" | "upnDomain" | "tokenLifetimeMinutes">,
  ) {}

  private getReport(): Promise<ReportInfo> {
    this.report ??= this.client.getReport(this.cfg.workspaceId, this.cfg.reportId).catch((e: unknown) => {
      this.report = undefined; // don't cache a failure
      throw e;
    });
    return this.report;
  }

  async embedInfoFor(alias: string): Promise<EmbedInfo> {
    const user = findUser(alias);
    if (!user) throw new UnknownUserError(alias);
    const report = await this.getReport();
    const identity = buildIdentity(upnFor(user.alias, this.cfg.upnDomain), user.roles, report.datasetId);
    const token = await this.client.generateEmbedToken({
      reports: [{ id: report.id }],
      datasets: [{ id: report.datasetId }],
      identities: [identity],
      lifetimeInMinutes: this.cfg.tokenLifetimeMinutes,
    });
    return {
      reportId: report.id,
      embedUrl: report.embedUrl,
      accessToken: token.token,
      expiration: token.expiration,
      user: user.alias,
      roles: user.roles,
    };
  }
}

export interface StaticFiles {
  /** URL path -> absolute file path. Anything not listed is a 404. */
  routes: Record<string, { file: string; type: string }>;
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  const text = JSON.stringify(body);
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
  res.end(text);
}

export function createApp(service: Pick<EmbedService, "embedInfoFor">, files: StaticFiles, log: (m: string) => void = () => {}): Server {
  return createServer((req: IncomingMessage, res: ServerResponse) => {
    void handle(req, res).catch((e: unknown) => {
      log(`unhandled: ${e instanceof Error ? e.message : String(e)}`);
      if (!res.headersSent) sendJson(res, 500, { error: "internal error" });
    });
  });

  async function handle(req: IncomingMessage, res: ServerResponse): Promise<void> {
    if (req.method !== "GET") return sendJson(res, 405, { error: "GET only" });
    const url = new URL(req.url ?? "/", "http://localhost");

    if (url.pathname === "/api/users") {
      return sendJson(res, 200, APP_USERS.map((u) => ({ alias: u.alias, displayName: u.displayName })));
    }
    if (url.pathname === "/api/embed") {
      const alias = url.searchParams.get("user") ?? "";
      try {
        return sendJson(res, 200, await service.embedInfoFor(alias));
      } catch (e) {
        if (e instanceof UnknownUserError) return sendJson(res, 404, { error: "unknown user" });
        if (e instanceof IdentityError) {
          log(`identity: ${e.message}`);
          return sendJson(res, 500, { error: "identity rejected" });
        }
        if (e instanceof PowerBiApiError) {
          log(e.message);
          return sendJson(res, 502, { error: `${e.operation} failed (HTTP ${e.status})` });
        }
        throw e;
      }
    }
    const entry = files.routes[url.pathname];
    if (entry) {
      const data = await readFile(entry.file);
      res.writeHead(200, { "Content-Type": entry.type, "Cache-Control": "no-store" });
      return void res.end(data);
    }
    sendJson(res, 404, { error: "not found" });
  }
}

export function defaultStaticFiles(root: string): StaticFiles {
  return {
    routes: {
      "/": { file: path.join(root, "public", "index.html"), type: "text/html; charset=utf-8" },
      "/embed.js": { file: path.join(root, "dist", "client", "embed.js"), type: "text/javascript; charset=utf-8" },
      "/timing.js": { file: path.join(root, "dist", "client", "timing.js"), type: "text/javascript; charset=utf-8" },
      "/vendor/powerbi.js": {
        file: path.join(root, "node_modules", "powerbi-client", "dist", "powerbi.min.js"),
        type: "text/javascript; charset=utf-8",
      },
    },
  };
}
