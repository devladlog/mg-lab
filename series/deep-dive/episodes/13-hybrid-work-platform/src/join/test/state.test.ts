import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import * as path from "node:path";
import { test } from "node:test";
import { classifyRedeemStatus, describeCallState, parseInvite, redeemMessage, CallState } from "../src/state";

const CODE = "A".repeat(43);

test("parseInvite: accepts #i=<43 chars> (with or without the hash), refuses everything else", () => {
  assert.equal(parseInvite(`#i=${CODE}`), CODE);
  assert.equal(parseInvite(`i=${CODE}`), CODE);
  for (const bad of ["", "#", "#i=", "#i=short", `#i=${CODE}x`, `#j=${CODE}`, `#i=${CODE}&x=1`, `?i=${CODE}`, "#i=" + "<script>".padEnd(43, "a")]) {
    assert.equal(parseInvite(bad), undefined, bad);
  }
});

test("lobby is shown as waiting and nothing but Leave is enabled", () => {
  const v = describeCallState("InLobby");
  assert.equal(v.tone, "wait");
  assert.deepEqual([v.canMute, v.canLeave], [false, true]);
  assert.match(v.text, /lobby/i);
});

test("connected enables mute and leave", () => {
  const v = describeCallState("Connected");
  assert.deepEqual([v.tone, v.canMute, v.canLeave], ["ok", true, true]);
});

test("every SDK call state has a view", () => {
  const states: CallState[] = ["None", "Connecting", "Ringing", "Connected", "LocalHold", "RemoteHold", "InLobby", "Disconnecting", "Disconnected", "EarlyMedia"];
  for (const s of states) assert.ok(describeCallState(s).text.length > 0, s);
});

test("disconnected: a normal end is 'left'; a failure shows the codes and says what to do", () => {
  assert.equal(describeCallState("Disconnected", 0).tone, "end");
  assert.equal(describeCallState("Disconnected", undefined).tone, "end");
  const failed = describeCallState("Disconnected", 5854, 0);
  assert.equal(failed.tone, "error");
  assert.match(failed.text, /code 5854, sub-code 0/);
  assert.match(failed.text, /new invitation/);
  assert.deepEqual([failed.canMute, failed.canLeave], [false, false]);
});

test("redeem errors map to one clear sentence each, and 403 never explains why", () => {
  assert.equal(classifyRedeemStatus(403), "invalid");
  assert.equal(classifyRedeemStatus(400), "bad-name");
  assert.equal(classifyRedeemStatus(0), "network");
  assert.equal(classifyRedeemStatus(500), "server");
  assert.ok(!/expired|used|exhausted|unknown/i.test(redeemMessage("invalid")));
});

test("the page source never uses the query string, a key or a connection string, and reads the meeting link only from the broker", () => {
  const src = readFileSync(path.join(__dirname, "..", "..", "src", "join.ts"), "utf8");
  assert.ok(!/location\.search|URLSearchParams/.test(src), "the invite must stay in the fragment");
  assert.ok(!/accesskey|connectionString|AzureKeyCredential/i.test(src));
  assert.match(src, /replaceState/);
  assert.match(src, /meetingLink: grant\.meetingLink/);
});
