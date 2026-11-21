// Limits mirror contract/hybrid.json (a test keeps both equal). Everything else comes from app settings.
export const LIMITS = {
  invite: {
    defaultValidMinutes: 60,
    maxValidMinutes: 480,
    defaultMaxUses: 3,
    maxMaxUses: 25,
    codeBytes: 32,
  },
  token: {
    scopes: ["voip"] as const,
    expiresInMinutes: 60,
    allowedMeetingHosts: ["teams.microsoft.com"] as readonly string[],
  },
  maxMeetingLinkLength: 2048,
  maxDisplayNameLength: 64,
} as const;

export interface AppConfig {
  /** https://<resource>.communication.azure.com/ */
  acsEndpoint: string;
  /** https://<storage>.table.core.windows.net */
  tableEndpoint: string;
  tableName: string;
}

export function loadConfig(env: Record<string, string | undefined>): AppConfig {
  const missing = ["Acs__Endpoint", "Invites__TableEndpoint"].filter((k) => !env[k]?.trim());
  if (missing.length > 0) {
    throw new Error(`Missing app settings: ${missing.join(", ")}`);
  }
  const acsEndpoint = env["Acs__Endpoint"]!.trim();
  if (!/^https:\/\/[a-z0-9-]+\.[a-z.]*communication\.azure\.com\/?$/i.test(acsEndpoint)) {
    throw new Error("Acs__Endpoint must be https://<resource>.<geo>.communication.azure.com/ (no keys, no connection string).");
  }
  return {
    acsEndpoint,
    tableEndpoint: env["Invites__TableEndpoint"]!.trim(),
    tableName: env["Invites__TableName"]?.trim() || "invites",
  };
}
