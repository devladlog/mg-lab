import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import type { AddressInfo } from "node:net";
import { createApp, EmbedService } from "../server/app.js";
import { PowerBiApiError, type GenerateTokenRequest } from "../server/powerbi.js";

const DS = "00000000-0000-0000-0000-0000000000d5";
const REPORT = "00000000-0000-0000-0000-0000000000a1";
const cfg = { workspaceId: "00000000-0000-0000-0000-0000000000b2", reportId: REPORT, upnDomain: "contoso.example", tokenLifetimeMinutes: 15 };

function fakeClient(requests: GenerateTokenRequest[], opts: { failToken?: boolean } = {}) {
  let reportCalls = 0;
  return {
    reportCalls: () => reportCalls,
    getReport: async () => {
      reportCalls++;
      return { id: REPORT, name: "Sales", datasetId: DS, embedUrl: "https://app.powerbi.com/reportEmbed?reportId=" + REPORT };
    },
    generateEmbedToken: async (r: GenerateTokenRequest) => {
      if (opts.failToken) throw new PowerBiApiError(403, "Generate Token", "{}");
      requests.push(r);
      return { token: "embed-token", tokenId: "00000000-0000-0000-0000-000000000009", expiration: "2030-01-01T00:00:00Z" };
    },
  };
}

async function withServer(client: ReturnType<typeof fakeClient>, run: (base: string) => Promise<void>) {
  const dir = await mkdtemp(path.join(tmpdir(), "embed-app-"));
  const page = path.join(dir, "index.html");
  await writeFile(page, "<html>ok</html>");
  const server = createApp(new EmbedService(client, cfg), { routes: { "/": { file: page, type: "text/html" } } });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  try {
    await run(`http://127.0.0.1:${(server.address() as AddressInfo).port}`);
  } finally {
    await new Promise<void>((r) => server.close(() => r()));
  }
}

test("Alex gets a token whose identity is his UPN in the Store Managers role, bound to the report's dataset", async () => {
  const requests: GenerateTokenRequest[] = [];
  await withServer(fakeClient(requests), async (base) => {
    const res = await fetch(`${base}/api/embed?user=alex.demo`);
    assert.equal(res.status, 200);
    const body = (await res.json()) as Record<string, unknown>;
    assert.equal(body["accessToken"], "embed-token");
    assert.equal(body["user"], "alex.demo");
    assert.equal(body["reportId"], REPORT);
  });
  assert.equal(requests.length, 1);
  assert.deepEqual(requests[0], {
    reports: [{ id: REPORT }],
    datasets: [{ id: DS }],
    identities: [{ username: "alex.demo@contoso.example", roles: ["Store Managers"], datasets: [DS] }],
    lifetimeInMinutes: 15,
  });
});

test("Jordan is Head Office, and the response never carries the UPN domain", async () => {
  const requests: GenerateTokenRequest[] = [];
  await withServer(fakeClient(requests), async (base) => {
    const text = await (await fetch(`${base}/api/embed?user=jordan.demo`)).text();
    assert.ok(!text.includes("contoso.example"));
  });
  assert.deepEqual(requests[0]?.identities[0]?.roles, ["Head Office"]);
});

test("the browser can't choose roles or a username: extra query parameters are ignored, unknown users are 404", async () => {
  const requests: GenerateTokenRequest[] = [];
  await withServer(fakeClient(requests), async (base) => {
    const res = await fetch(`${base}/api/embed?user=sam.demo&roles=Head%20Office&username=jordan.demo@contoso.example`);
    assert.equal(res.status, 200);
    assert.equal((await fetch(`${base}/api/embed?user=mallory`)).status, 404);
    assert.equal((await fetch(`${base}/api/embed`)).status, 404);
  });
  assert.equal(requests.length, 1);
  assert.equal(requests[0]?.identities[0]?.username, "sam.demo@contoso.example");
  assert.deepEqual(requests[0]?.identities[0]?.roles, ["Store Managers"]);
});

test("the report lookup is made once, not per request", async () => {
  const client = fakeClient([]);
  await withServer(client, async (base) => {
    await fetch(`${base}/api/embed?user=alex.demo`);
    await fetch(`${base}/api/embed?user=sam.demo`);
  });
  assert.equal(client.reportCalls(), 1);
});

test("a Power BI failure is a 502 with a short message, not a stack trace", async () => {
  await withServer(fakeClient([], { failToken: true }), async (base) => {
    const res = await fetch(`${base}/api/embed?user=alex.demo`);
    assert.equal(res.status, 502);
    assert.deepEqual(await res.json(), { error: "Generate Token failed (HTTP 403)" });
  });
});

test("only GET, only listed files, and the user list", async () => {
  await withServer(fakeClient([]), async (base) => {
    assert.equal((await fetch(`${base}/`)).status, 200);
    assert.equal((await fetch(`${base}/package.json`)).status, 404);
    assert.equal((await fetch(`${base}/../etc/passwd`)).status, 404);
    assert.equal((await fetch(`${base}/api/embed?user=alex.demo`, { method: "POST" })).status, 405);
    const users = (await (await fetch(`${base}/api/users`)).json()) as { alias: string }[];
    assert.deepEqual(users.map((u) => u.alias), ["alex.demo", "sam.demo", "riley.demo", "taylor.demo", "jordan.demo", "nobody.demo"]);
  });
});
