// The gotcha, run for real: ask for an embed token for an RLS model WITHOUT an identity.
// Learn (embed a report with RLS): for a service principal, token generation fails when no username and role are given;
// for a master user it succeeds and the data isn't filtered. This probe sends the request and reports what came back.
import { loadConfig, type Config } from "./config.js";
import { createTokenProvider } from "./msal.js";
import { PowerBiApiError, PowerBiClient } from "./powerbi.js";

export async function probeWithoutIdentity(
  client: Pick<PowerBiClient, "getReport" | "generateEmbedToken">,
  cfg: Pick<Config, "workspaceId" | "reportId">,
): Promise<string> {
  const report = await client.getReport(cfg.workspaceId, cfg.reportId);
  try {
    await client.generateEmbedToken({ reports: [{ id: report.id }], datasets: [{ id: report.datasetId }], identities: [] });
    return "token issued WITHOUT an identity: the report would show all rows";
  } catch (e) {
    if (e instanceof PowerBiApiError) return `refused: ${e.operation} HTTP ${e.status} ${e.body.slice(0, 200)}`;
    throw e;
  }
}

// Run directly: node dist/server/probe.js
if (import.meta.url === `file://${process.argv[1]}`) {
  const cfg = loadConfig(process.env);
  const client = new PowerBiClient(fetch, createTokenProvider(cfg));
  console.log(await probeWithoutIdentity(client, cfg));
}
