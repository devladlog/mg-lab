// Runs TableInviteStore against Azurite (Microsoft's open-source Azure Storage emulator, a devDependency) so the
// optimistic-concurrency path is exercised by a real Table service implementation, not by a hand-written fake.
import { strict as assert } from "node:assert";
import { ChildProcess, spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { createConnection } from "node:net";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { after, before, test } from "node:test";
import { TableClient } from "@azure/data-tables";
import { InviteError, createInvite, redeemInvite } from "../src/lib/invites";
import { TableInviteStore } from "../src/lib/tableStore";

const PORT = 10152;
// The public developer account that Azurite documents (not a secret of ours).
const DEV_ACCOUNT = "devstoreaccount1";
const DEV_KEY = ["Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq", "K1SZFPTOtr/KBHBeksoGMGw=="].join("/");
const CONNECTION = `DefaultEndpointsProtocol=http;AccountName=${DEV_ACCOUNT};AccountKey=${DEV_KEY};TableEndpoint=http://127.0.0.1:${PORT}/${DEV_ACCOUNT};`;
const LINK = "https://teams.microsoft.com/meet/1234567890123?p=AbCdEfGhIjK";

let azurite: ChildProcess;
let dir: string;

function waitForPort(port: number, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const attempt = (): void => {
      const socket = createConnection({ port, host: "127.0.0.1" }, () => {
        socket.end();
        resolve();
      });
      socket.on("error", () => {
        socket.destroy();
        if (Date.now() > deadline) reject(new Error("Azurite did not start"));
        else setTimeout(attempt, 200);
      });
    };
    attempt();
  });
}

before(async () => {
  dir = mkdtempSync(path.join(tmpdir(), "azurite-"));
  const bin = path.join(__dirname, "..", "..", "node_modules", ".bin", "azurite-table");
  azurite = spawn(bin, ["--tableHost", "127.0.0.1", "--tablePort", String(PORT), "--location", dir, "--skipApiVersionCheck", "--silent"], { stdio: "ignore" });
  await waitForPort(PORT, 30_000);
});

after(() => {
  azurite?.kill("SIGKILL");
  if (dir) rmSync(dir, { recursive: true, force: true });
});

async function newStore(): Promise<TableInviteStore> {
  const table = TableClient.fromConnectionString(CONNECTION, `invites${Date.now()}${Math.floor(Math.random() * 1e6)}`, { allowInsecureConnection: true });
  await table.createTable();
  return new TableInviteStore(table);
}

test("azurite: create, redeem until exhausted, then refused", async () => {
  const store = await newStore();
  const { code } = await createInvite(store, { meetingLink: LINK, maxUses: 2 });
  assert.equal((await redeemInvite(store, code)).uses, 1);
  assert.equal((await redeemInvite(store, code)).uses, 2);
  await assert.rejects(redeemInvite(store, code), (e: unknown) => e instanceof InviteError && e.reason === "exhausted");
});

test("azurite: unknown code is not_found (404 from the table)", async () => {
  const store = await newStore();
  await assert.rejects(redeemInvite(store, "A".repeat(43)), (e: unknown) => e instanceof InviteError && e.reason === "not_found");
});

test("azurite: expired invite is refused", async () => {
  const store = await newStore();
  const { code } = await createInvite(store, { meetingLink: LINK, validMinutes: 5 }, new Date("2026-01-01T00:00:00Z"));
  await assert.rejects(redeemInvite(store, code, new Date("2026-01-01T00:05:00Z")), (e: unknown) => e instanceof InviteError && e.reason === "expired");
});

test("azurite: the stored row holds the hash, not the code", async () => {
  const table = TableClient.fromConnectionString(CONNECTION, `rows${Date.now()}`, { allowInsecureConnection: true });
  await table.createTable();
  const store = new TableInviteStore(table);
  const { code } = await createInvite(store, { meetingLink: LINK });
  const rows: Array<Record<string, unknown>> = [];
  for await (const row of table.listEntities()) rows.push(row as Record<string, unknown>);
  assert.equal(rows.length, 1);
  assert.ok(!JSON.stringify(rows).includes(code));
  assert.match(String(rows[0]!["rowKey"]), /^[0-9a-f]{64}$/);
});

test("azurite: ten guests race for a 3-use invite: exactly 3 get in, 7 are refused (If-Match / 412 retry works for real)", async () => {
  const store = await newStore();
  const { code } = await createInvite(store, { meetingLink: LINK, maxUses: 3 });
  const results = await Promise.allSettled(Array.from({ length: 10 }, () => redeemInvite(store, code)));
  const ok = results.filter((r) => r.status === "fulfilled").length;
  const refused = results.filter((r) => r.status === "rejected" && r.reason instanceof InviteError).length;
  assert.equal(ok, 3);
  assert.equal(refused, 7);
  const final = await redeemInvite(store, code).catch((e: unknown) => e);
  assert.ok(final instanceof InviteError && final.reason === "exhausted");
});
