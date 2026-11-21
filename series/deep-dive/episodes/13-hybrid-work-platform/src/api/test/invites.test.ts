import { strict as assert } from "node:assert";
import { test } from "node:test";
import { InviteError, createInvite, hashCode, looksLikeCode, redeemInvite } from "../src/lib/invites";
import { MemoryInviteStore } from "../src/lib/memoryStore";
import { ValidationError } from "../src/lib/meeting";

const LINK = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_AAA%40thread.v2/0?context=%7b%7d";
const T0 = new Date("2026-12-01T10:00:00Z");

test("createInvite stores only the hash of the code and a 43 character base64url code is returned", async () => {
  const store = new MemoryInviteStore();
  const invite = await createInvite(store, { meetingLink: LINK }, T0);
  assert.ok(looksLikeCode(invite.code));
  assert.equal(invite.code.length, 43);
  const stored = await store.consume(hashCode(invite.code), T0);
  assert.equal(stored.codeHash, hashCode(invite.code));
  assert.notEqual(stored.codeHash, invite.code);
});

test("defaults: 60 minutes, 3 uses; expiry is computed from the supplied clock", async () => {
  const store = new MemoryInviteStore();
  const invite = await createInvite(store, { meetingLink: LINK }, T0);
  assert.equal(invite.maxUses, 3);
  assert.equal(invite.expiresOn, "2026-12-01T11:00:00.000Z");
});

test("limits: validMinutes up to 480, maxUses up to 25; zero, negative, fractional and text are refused", async () => {
  const store = new MemoryInviteStore();
  await createInvite(store, { meetingLink: LINK, validMinutes: 480, maxUses: 25 }, T0);
  for (const bad of [{ validMinutes: 481 }, { validMinutes: 0 }, { validMinutes: -5 }, { validMinutes: 1.5 }, { validMinutes: "60" }, { maxUses: 26 }, { maxUses: 0 }]) {
    await assert.rejects(createInvite(store, { meetingLink: LINK, ...bad }, T0), ValidationError);
  }
});

test("two invites for the same meeting get different codes", async () => {
  const store = new MemoryInviteStore();
  const a = await createInvite(store, { meetingLink: LINK }, T0);
  const b = await createInvite(store, { meetingLink: LINK }, T0);
  assert.notEqual(a.code, b.code);
});

test("redeem: each use is counted and the invite is exhausted after maxUses", async () => {
  const store = new MemoryInviteStore();
  const { code } = await createInvite(store, { meetingLink: LINK, maxUses: 2 }, T0);
  assert.equal((await redeemInvite(store, code, T0)).uses, 1);
  assert.equal((await redeemInvite(store, code, T0)).uses, 2);
  await assert.rejects(redeemInvite(store, code, T0), (e: unknown) => e instanceof InviteError && e.reason === "exhausted");
});

test("redeem: refused at and after the expiry time, allowed one millisecond before", async () => {
  const store = new MemoryInviteStore();
  const { code } = await createInvite(store, { meetingLink: LINK, validMinutes: 10, maxUses: 5 }, T0);
  await redeemInvite(store, code, new Date(T0.getTime() + 10 * 60_000 - 1));
  await assert.rejects(redeemInvite(store, code, new Date(T0.getTime() + 10 * 60_000)), (e: unknown) => e instanceof InviteError && e.reason === "expired");
});

test("redeem: malformed or unknown codes are not_found without touching the store", async () => {
  const store = new MemoryInviteStore();
  for (const bad of [undefined, null, 42, "", "short", "x".repeat(44), "../../etc/passwd", "A".repeat(42) + "="]) {
    await assert.rejects(redeemInvite(store, bad, T0), (e: unknown) => e instanceof InviteError && e.reason === "not_found");
  }
  await assert.rejects(redeemInvite(store, "A".repeat(43), T0), (e: unknown) => e instanceof InviteError && e.reason === "not_found");
});

test("concurrency: a writer that slips in between read and write forces a retry, never a double spend", async () => {
  const store = new MemoryInviteStore();
  const { code } = await createInvite(store, { meetingLink: LINK, maxUses: 2 }, T0);
  let interfered = false;
  store.beforeWrite = (hash) => {
    if (interfered) return;
    interfered = true;
    // a second guest takes a use after our read (same as another request landing between GET and PUT)
    void store.consume(hash, T0);
  };
  const mine = await redeemInvite(store, code, T0);
  assert.equal(mine.uses, 2, "both uses were counted exactly once");
  await assert.rejects(redeemInvite(store, code, T0), (e: unknown) => e instanceof InviteError && e.reason === "exhausted");
});

test("concurrency: ten parallel guests on a 3-use invite: exactly 3 succeed", async () => {
  const store = new MemoryInviteStore();
  const { code } = await createInvite(store, { meetingLink: LINK, maxUses: 3 }, T0);
  const results = await Promise.allSettled(Array.from({ length: 10 }, () => redeemInvite(store, code, T0)));
  assert.equal(results.filter((r) => r.status === "fulfilled").length, 3);
});
