// App-only token for the Power BI REST API: service principal, client credentials, MSAL's own cache.
// Learn: https://learn.microsoft.com/en-us/power-bi/developer/embedded/embed-service-principal
import { ConfidentialClientApplication } from "@azure/msal-node";
import type { Config } from "./config.js";
import type { TokenProvider } from "./powerbi.js";

export const POWER_BI_SCOPE = "https://analysis.windows.net/powerbi/api/.default";

export function createTokenProvider(cfg: Pick<Config, "tenantId" | "clientId" | "clientSecret">): TokenProvider {
  const app = new ConfidentialClientApplication({
    auth: {
      clientId: cfg.clientId,
      clientSecret: cfg.clientSecret,
      authority: `https://login.microsoftonline.com/${cfg.tenantId}`,
    },
  });
  return {
    async getToken() {
      const result = await app.acquireTokenByClientCredential({ scopes: [POWER_BI_SCOPE] });
      if (!result?.accessToken) throw new Error("Microsoft Entra returned no access token");
      return result.accessToken;
    },
  };
}
