// Settings come from environment variables. Nothing secret is ever in a file of this repo.

export interface Config {
  tenantId: string;
  clientId: string;
  clientSecret: string;
  workspaceId: string;
  reportId: string;
  upnDomain: string;
  port: number;
  tokenLifetimeMinutes: number;
}

const GUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function loadConfig(env: Record<string, string | undefined>): Config {
  const problems: string[] = [];
  const need = (name: string): string => {
    const v = env[name]?.trim();
    if (!v) problems.push(`${name} is not set`);
    return v ?? "";
  };
  const guid = (name: string): string => {
    const v = need(name);
    if (v && !GUID.test(v)) problems.push(`${name} is not a GUID`);
    return v;
  };

  const cfg: Config = {
    tenantId: guid("PBI_TENANT_ID"),
    clientId: guid("PBI_CLIENT_ID"),
    clientSecret: need("PBI_CLIENT_SECRET"),
    workspaceId: guid("PBI_WORKSPACE_ID"),
    reportId: guid("PBI_REPORT_ID"),
    upnDomain: need("PBI_UPN_DOMAIN").replace(/^@/, ""),
    port: Number(env["PORT"] ?? "5173"),
    tokenLifetimeMinutes: Number(env["EMBED_LIFETIME_MINUTES"] ?? "15"),
  };
  if (!Number.isInteger(cfg.port) || cfg.port < 0 || cfg.port > 65535) problems.push("PORT is not a port number");
  // Learn: lifetimeInMinutes is a positive integer and can only shorten the default.
  if (!Number.isInteger(cfg.tokenLifetimeMinutes) || cfg.tokenLifetimeMinutes < 1) {
    problems.push("EMBED_LIFETIME_MINUTES must be a positive integer");
  }
  if (problems.length > 0) throw new Error(`Configuration problem(s):\n - ${problems.join("\n - ")}`);
  return cfg;
}
