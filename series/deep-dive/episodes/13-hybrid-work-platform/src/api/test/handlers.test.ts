import { strict as assert } from "node:assert";
import { test } from "node:test";
import { handleCreateInvite, handleRedeem, RedeemResponse } from "../src/lib/handlers";
import { MemoryInviteStore } from "../src/lib/memoryStore";
import { IdentityClientLike } from "../src/lib/token";

const LINK = "https://teams.microsoft.com/meet/1234567890123?p=AbCdEfGhIjK";
const T0 = new Date("2026-12-01T10:00:00Z");

function fakeIdentity() {
  const calls: Array<{ scopes: string[]; minutes?: number }> = [];
  const client: IdentityClientLike = {
    async createUserAndToken(scopes, options) {
      calls.push({ scopes: [...scopes], minutes: options?.tokenExpiresInMinutes });
      return { user: { communicationUserId: `8:acs:00000000-0000-0000-0000-00000000000${calls.length}` }, token: "eyJ.fake.token", expiresOn: new Date(T0.getTime() + 3_600_000) };
    },
  };
  return { client, calls };
}

async function newInvite(store: MemoryInviteStore, extra: object = {}) {
  const res = await handleCreateInvite(store, { meetingLink: LINK, ...extra }, "https://func-hyb-abc.azurewebsites.net/", T0);
  assert.equal(res.status, 201);
  const url = (res.body as { inviteUrl: string }).inviteUrl;
  return { url, code: url.split("#i=")[1]! };
}

test("create: the invite URL carries the code in the fragment, not in the query string", async () => {
  const { url } = await newInvite(new MemoryInviteStore());
  assert.match(url, /^https:\/\/func-hyb-abc\.azurewebsites\.net\/join#i=[A-Za-z0-9_-]{43}$/);
  assert.ok(!url.includes("?"));
});

test("create: validation errors are 400 and explain the problem; non-object bodies are 400", async () => {
  const store = new MemoryInviteStore();
  const r1 = await handleCreateInvite(store, { meetingLink: "https://example.com/x" }, "https://x", T0);
  assert.equal(r1.status, 400);
  assert.match((r1.body as { error: string }).error, /teams\.microsoft\.com/);
  assert.equal((await handleCreateInvite(store, undefined, "https://x", T0)).status, 400);
  assert.equal((await handleCreateInvite(store, [1], "https://x", T0)).status, 400);
});

test("redeem: success returns an ACS token (voip only, 60 minutes), the meeting link and the display name", async () => {
  const store = new MemoryInviteStore();
  const { code } = await newInvite(store);
  const { client, calls } = fakeIdentity();
  const res = await handleRedeem(store, client, { code, displayName: "Riley Demo" }, T0);
  assert.equal(res.status, 200);
  const body = res.body as RedeemResponse;
  assert.equal(body.token, "eyJ.fake.token");
  assert.equal(body.meetingLink, LINK);
  assert.equal(body.displayName, "Riley Demo");
  assert.deepEqual(calls, [{ scopes: ["voip"], minutes: 60 }]);
  assert.equal(res.headers?.["Cache-Control"], "no-store");
});

test("redeem: unknown, expired and exhausted invites are the same 403 and no ACS identity is created", async () => {
  const store = new MemoryInviteStore();
  const { code } = await newInvite(store, { maxUses: 1, validMinutes: 5 });
  const { client, calls } = fakeIdentity();
  const logs: string[] = [];
  const unknown = await handleRedeem(store, client, { code: "A".repeat(43) }, T0, (m) => logs.push(m));
  await handleRedeem(store, client, { code }, T0); // takes the only use
  const exhausted = await handleRedeem(store, client, { code }, T0, (m) => logs.push(m));
  const expired = await handleRedeem(store, client, { code }, new Date(T0.getTime() + 600_000), (m) => logs.push(m));
  for (const r of [unknown, exhausted, expired]) {
    assert.equal(r.status, 403);
    assert.deepEqual(r.body, { error: "This invitation is not valid." });
  }
  assert.equal(calls.length, 1, "only the successful redeem created an identity");
  assert.deepEqual(logs, ["invite refused: not_found", "invite refused: exhausted", "invite refused: expired"]);
});

test("redeem: an error response never contains the meeting link or a token", async () => {
  const store = new MemoryInviteStore();
  const { code } = await newInvite(store, { maxUses: 1 });
  const { client } = fakeIdentity();
  await handleRedeem(store, client, { code }, T0);
  const res = await handleRedeem(store, client, { code }, T0);
  const text = JSON.stringify(res);
  assert.ok(!text.includes("teams.microsoft.com") && !text.includes("eyJ"));
});

test("redeem: a bad display name is a 400 and does not burn a use", async () => {
  const store = new MemoryInviteStore();
  const { code } = await newInvite(store, { maxUses: 1 });
  const { client } = fakeIdentity();
  assert.equal((await handleRedeem(store, client, { code, displayName: "x".repeat(100) }, T0)).status, 400);
  assert.equal((await handleRedeem(store, client, { code }, T0)).status, 200);
});

test("redeem: if ACS fails after the use was counted the error propagates (the guest retries with a new invite use)", async () => {
  const store = new MemoryInviteStore();
  const { code } = await newInvite(store, { maxUses: 2 });
  const failing: IdentityClientLike = { async createUserAndToken() { throw new Error("ACS 503"); } };
  await assert.rejects(handleRedeem(store, failing, { code }, T0), /ACS 503/);
  const { client } = fakeIdentity();
  assert.equal((await handleRedeem(store, client, { code }, T0)).status, 200, "one use is left");
});
