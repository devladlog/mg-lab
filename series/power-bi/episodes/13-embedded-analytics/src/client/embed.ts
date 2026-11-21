// Browser side. powerbi.js (the powerbi-client UMD bundle) is loaded by index.html and defines
// window.powerbi (the service) and window["powerbi-client"] (models, factories).
import type { service, Report, models } from "powerbi-client";
import { msUntilRefresh } from "./timing.js";

declare const powerbi: service.Service;
type PbiWindow = Window & { "powerbi-client": { models: typeof models } };

interface EmbedInfo {
  reportId: string;
  embedUrl: string;
  accessToken: string;
  expiration: string;
  user: string;
  roles: string[];
}

const container = document.getElementById("report") as HTMLElement;
const select = document.getElementById("user") as HTMLSelectElement;
const status = document.getElementById("status") as HTMLElement;
let refreshTimer: number | undefined;

async function getEmbedInfo(user: string): Promise<EmbedInfo> {
  const res = await fetch(`/api/embed?user=${encodeURIComponent(user)}`);
  if (!res.ok) throw new Error(`the server said ${res.status}`);
  return (await res.json()) as EmbedInfo;
}

function scheduleRefresh(report: Report, user: string, info: EmbedInfo): void {
  window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(async () => {
    try {
      const next = await getEmbedInfo(user);
      await report.setAccessToken(next.accessToken); // same report, new token, no reload
      status.textContent = `token refreshed for ${user}`;
      scheduleRefresh(report, user, next);
    } catch (e) {
      status.textContent = `token refresh failed: ${String(e)}`;
    }
  }, msUntilRefresh(info.expiration, Date.now()));
}

async function show(user: string): Promise<void> {
  window.clearTimeout(refreshTimer);
  powerbi.reset(container);
  status.textContent = `loading as ${user} ...`;
  const info = await getEmbedInfo(user);
  const { models } = (window as unknown as PbiWindow)["powerbi-client"];
  const report = powerbi.embed(container, {
    type: "report",
    id: info.reportId,
    embedUrl: info.embedUrl,
    accessToken: info.accessToken,
    tokenType: models.TokenType.Embed, // an embed token, not an Entra access token
    permissions: models.Permissions.Read,
    settings: { panes: { filters: { visible: false } } },
  }) as Report;
  report.off("error");
  report.on("error", (event) => {
    status.textContent = `embed error: ${JSON.stringify((event as CustomEvent).detail?.message ?? "unknown")}`;
  });
  report.on("loaded", () => {
    status.textContent = `loaded as ${user} (roles: ${info.roles.join(", ")}), token expires ${info.expiration}`;
  });
  scheduleRefresh(report, user, info);
}

async function init(): Promise<void> {
  const users = (await (await fetch("/api/users")).json()) as { alias: string; displayName: string }[];
  for (const u of users) select.add(new Option(u.displayName, u.alias));
  select.addEventListener("change", () => void show(select.value));
  await show(select.value);
}

void init().catch((e) => {
  status.textContent = String(e);
});
