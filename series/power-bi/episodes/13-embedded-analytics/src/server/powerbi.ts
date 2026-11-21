// The two Power BI REST calls an "embed for your customers" back end needs, over an injected fetch
// so the tests never touch the network.
//   GET  /v1.0/myorg/groups/{groupId}/reports/{reportId}   (Reports - Get Report In Group)
//   POST /v1.0/myorg/GenerateToken                          (Embed Token - Generate Token, V2)

import type { EffectiveIdentity } from "./identity.js";

export const POWER_BI_API = "https://api.powerbi.com";

export interface TokenProvider {
  getToken(): Promise<string>;
}

export interface ReportInfo {
  id: string;
  name: string;
  datasetId: string;
  embedUrl: string;
}

export interface EmbedToken {
  token: string;
  tokenId: string;
  expiration: string;
}

export interface GenerateTokenRequest {
  reports: { id: string }[];
  datasets: { id: string }[];
  identities: EffectiveIdentity[];
  lifetimeInMinutes?: number;
}

export class PowerBiApiError extends Error {
  constructor(
    readonly status: number,
    readonly operation: string,
    readonly body: string,
  ) {
    super(`${operation} failed with HTTP ${status}${body ? `: ${body.slice(0, 300)}` : ""}`);
    this.name = "PowerBiApiError";
  }
}

export class PowerBiClient {
  constructor(
    private readonly fetchFn: typeof fetch,
    private readonly tokens: TokenProvider,
    private readonly baseUrl: string = POWER_BI_API,
  ) {}

  private async call<T>(operation: string, method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
    const accessToken = await this.tokens.getToken();
    const headers: Record<string, string> = { Authorization: `Bearer ${accessToken}` };
    const init: RequestInit = { method, headers };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    const res = await this.fetchFn(`${this.baseUrl}${path}`, init);
    const text = await res.text();
    if (!res.ok) throw new PowerBiApiError(res.status, operation, text);
    return JSON.parse(text) as T;
  }

  getReport(workspaceId: string, reportId: string): Promise<ReportInfo> {
    return this.call<ReportInfo>(
      "Get Report In Group",
      "GET",
      `/v1.0/myorg/groups/${encodeURIComponent(workspaceId)}/reports/${encodeURIComponent(reportId)}`,
    );
  }

  generateEmbedToken(request: GenerateTokenRequest): Promise<EmbedToken> {
    return this.call<EmbedToken>("Generate Token", "POST", "/v1.0/myorg/GenerateToken", request);
  }
}
