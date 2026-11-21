import { test } from "node:test";
import assert from "node:assert/strict";
import { PowerBiApiError, PowerBiClient } from "../server/powerbi.js";

interface Call { url: string; method?: string; headers: Record<string, string>; body?: string }

function fakeFetch(status: number, payload: unknown, calls: Call[]): typeof fetch {
  return (async (url: string, init: RequestInit) => {
    calls.push({ url, method: init.method, headers: init.headers as Record<string, string>, body: init.body as string | undefined });
    return new Response(typeof payload === "string" ? payload : JSON.stringify(payload), { status });
  }) as unknown as typeof fetch;
}

const tokens = { getToken: async () => "entra-token" };
const WS = "f089354e-8366-4e18-aea3-4cb4a3a50b48";
const REPORT = "5b218778-e7a5-4d73-8187-f10824047715";
const DS = "cfafbeb1-8037-4d0c-896e-a46fb27ff229";

test("Get Report In Group: right URL, bearer token, Learn's response shape", async () => {
  const calls: Call[] = [];
  const sample = { datasetId: DS, id: REPORT, name: "SalesMarketing", embedUrl: `https://app.powerbi.com/reportEmbed?reportId=${REPORT}&groupId=${WS}` };
  const client = new PowerBiClient(fakeFetch(200, sample, calls), tokens);
  const report = await client.getReport(WS, REPORT);
  assert.equal(report.datasetId, DS);
  assert.equal(calls[0]?.url, `https://api.powerbi.com/v1.0/myorg/groups/${WS}/reports/${REPORT}`);
  assert.equal(calls[0]?.method, "GET");
  assert.equal(calls[0]?.headers["Authorization"], "Bearer entra-token");
});

test("Generate Token: the body is the shape of Learn's RLS example plus a short lifetime", async () => {
  const calls: Call[] = [];
  const client = new PowerBiClient(fakeFetch(200, { token: "H4sI", tokenId: "49ae3742-54c0-4c29-af52-619ff93b5c80", expiration: "2028-07-29T17:58:19Z" }, calls), tokens);
  const out = await client.generateEmbedToken({
    reports: [{ id: REPORT }],
    datasets: [{ id: DS }],
    identities: [{ username: "john@contoso.com", roles: ["sales"], datasets: [DS] }],
    lifetimeInMinutes: 10,
  });
  assert.equal(out.token, "H4sI");
  assert.equal(calls[0]?.url, "https://api.powerbi.com/v1.0/myorg/GenerateToken");
  assert.equal(calls[0]?.method, "POST");
  assert.equal(calls[0]?.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0]?.body ?? "{}"), {
    reports: [{ id: REPORT }],
    datasets: [{ id: DS }],
    identities: [{ username: "john@contoso.com", roles: ["sales"], datasets: [DS] }],
    lifetimeInMinutes: 10,
  });
});

test("an HTTP error becomes a PowerBiApiError with the operation and status, body truncated", async () => {
  const client = new PowerBiClient(fakeFetch(403, "x".repeat(1000), []), tokens);
  await assert.rejects(client.getReport(WS, REPORT), (e: unknown) => {
    assert.ok(e instanceof PowerBiApiError);
    assert.equal(e.status, 403);
    assert.equal(e.operation, "Get Report In Group");
    assert.ok(e.message.length < 400);
    return true;
  });
});

import { probeWithoutIdentity } from "../server/probe.js";

test("probe: reports a refusal and a success differently, and sends an empty identities list", async () => {
  const sent: unknown[] = [];
  const base = { getReport: async () => ({ id: REPORT, name: "r", datasetId: DS, embedUrl: "u" }) };
  const refused = await probeWithoutIdentity(
    { ...base, generateEmbedToken: async (r) => { sent.push(r); throw new PowerBiApiError(400, "Generate Token", '{"error":{"code":"InvalidRequest"}}'); } },
    { workspaceId: WS, reportId: REPORT },
  );
  assert.match(refused, /^refused: Generate Token HTTP 400/);
  const issued = await probeWithoutIdentity(
    { ...base, generateEmbedToken: async () => ({ token: "t", tokenId: "i", expiration: "2030-01-01T00:00:00Z" }) },
    { workspaceId: WS, reportId: REPORT },
  );
  assert.match(issued, /all rows/);
  assert.deepEqual((sent[0] as { identities: unknown[] }).identities, []);
});
