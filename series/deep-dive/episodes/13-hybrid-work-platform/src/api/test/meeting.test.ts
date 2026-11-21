import { strict as assert } from "node:assert";
import { test } from "node:test";
import { ValidationError, validateDisplayName, validateMeetingLink } from "../src/lib/meeting";

const ok = [
  "https://teams.microsoft.com/l/meetup-join/19%3ameeting_AAA%40thread.v2/0?context=%7b%22Tid%22%3a%2200000000-0000-0000-0000-000000000000%22%7d",
  "https://teams.microsoft.com/meet/1234567890123?p=AbCdEfGhIjK",
  "https://TEAMS.microsoft.com/l/meetup-join/x/0",
];
for (const link of ok) {
  test(`meeting link accepted: ${link.slice(0, 48)}...`, () => {
    assert.ok(validateMeetingLink(link).startsWith("https://teams.microsoft.com/"));
  });
}

const bad: Array<[string, unknown]> = [
  ["not a string", 42],
  ["empty", "   "],
  ["not a url", "teams.microsoft.com/l/meetup-join/x"],
  ["http", "http://teams.microsoft.com/l/meetup-join/x/0"],
  ["lookalike host", "https://teams.microsoft.com.evil.example/l/meetup-join/x/0"],
  ["userinfo trick", "https://teams.microsoft.com@evil.example/l/meetup-join/x/0"],
  ["personal Teams (not supported for interop)", "https://teams.live.com/meet/1234567890123"],
  ["port", "https://teams.microsoft.com:8443/l/meetup-join/x/0"],
  ["wrong path", "https://teams.microsoft.com/l/chat/0/0"],
  ["too long", "https://teams.microsoft.com/l/meetup-join/" + "a".repeat(2100)],
];
for (const [name, link] of bad) {
  test(`meeting link refused: ${name}`, () => {
    assert.throws(() => validateMeetingLink(link), ValidationError);
  });
}

test("display name: default, control characters stripped, length capped", () => {
  assert.equal(validateDisplayName(undefined), "Guest");
  assert.equal(validateDisplayName("   "), "Guest");
  assert.equal(validateDisplayName("Alex\u0000 Demo\n"), "Alex Demo");
  assert.throws(() => validateDisplayName("x".repeat(65)), ValidationError);
  assert.throws(() => validateDisplayName({}), ValidationError);
});
