// Minimal Dataverse Web API client. fetch is injected so tests (and --dry-run) never touch the network.

export type FetchLike = (url: string, init: { method: string; headers: Record<string, string>; body?: string }) => Promise<{
  status: number;
  headers: { get(name: string): string | null };
  text(): Promise<string>;
}>;

export interface DvResponse {
  status: number;
  entityId: string | null; // GUID parsed from the OData-EntityId header on create
  body: any;
}

export class DataverseError extends Error {
  readonly status: number;
  constructor(status: number, method: string, path: string, detail: string) {
    super(`${method} ${path} -> ${status}: ${detail}`);
    this.status = status;
  }
}

const GUID = /\(([0-9a-fA-F-]{36})\)\s*$/;

export function idFromEntityIdHeader(header: string | null): string | null {
  if (!header) return null;
  const m = GUID.exec(header);
  return m ? m[1].toLowerCase() : null;
}

export class DataverseClient {
  private readonly base: string;
  private readonly token: string;
  private readonly fetchFn: FetchLike;

  constructor(orgUrl: string, token: string, fetchFn: FetchLike, apiVersion = "v9.2") {
    this.base = `${orgUrl.replace(/\/+$/, "")}/api/data/${apiVersion}/`;
    this.token = token;
    this.fetchFn = fetchFn;
  }

  async request(method: string, path: string, body?: unknown, extraHeaders: Record<string, string> = {}): Promise<DvResponse> {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.token}`,
      Accept: "application/json",
      "OData-MaxVersion": "4.0",
      "OData-Version": "4.0",
      ...extraHeaders,
    };
    if (body !== undefined) headers["Content-Type"] = "application/json; charset=utf-8";
    const res = await this.fetchFn(this.base + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    const text = await res.text();
    const parsed = text ? safeJson(text) : null;
    if (res.status >= 400) {
      const detail = parsed?.error?.message ?? text.slice(0, 300);
      throw new DataverseError(res.status, method, path, detail);
    }
    return { status: res.status, entityId: idFromEntityIdHeader(res.headers.get("OData-EntityId")), body: parsed };
  }

  /** GET that returns null on 404 instead of throwing (used to make every step idempotent). */
  async tryGet(path: string): Promise<any | null> {
    try {
      return (await this.request("GET", path)).body;
    } catch (e) {
      if (e instanceof DataverseError && e.status === 404) return null;
      throw e;
    }
  }

  /** First row of a collection query, or null. */
  async first(path: string): Promise<any | null> {
    const body = await this.request("GET", path);
    return body.body?.value?.[0] ?? null;
  }
}

function safeJson(text: string): any {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export const odataString = (s: string) => `'${s.replace(/'/g, "''")}'`;
