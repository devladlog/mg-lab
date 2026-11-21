import { test } from "node:test";
import assert from "node:assert/strict";
import { buildIdentity, IdentityError } from "../server/identity.js";

const DS = "00000000-0000-0000-0000-000000000001";

test("builds the identity Learn shows: username, roles, datasets", () => {
  assert.deepEqual(buildIdentity("alex.demo@contoso.com", ["Store Managers"], DS), {
    username: "alex.demo@contoso.com",
    roles: ["Store Managers"],
    datasets: [DS],
  });
});

test("rejects what Learn says the service rejects", () => {
  const bad: [string, string[]][] = [
    ["", ["r"]],
    ["has space@contoso.com", ["r"]],
    ["x".repeat(257), ["r"]],
    ["café@contoso.com", ["r"]],
    ["a@b.c", []],
    ["a@b.c", ["two,roles"]],
    ["a@b.c", ["r".repeat(51)]],
    ["a@b.c", Array.from({ length: 51 }, (_, i) => `r${i}`)],
  ];
  for (const [user, roles] of bad) {
    assert.throws(() => buildIdentity(user, roles, DS), IdentityError, `${user.slice(0, 12)} / ${roles.length} roles`);
  }
  assert.throws(() => buildIdentity("a@b.c", ["r"], ""), IdentityError);
});

test("accepts the limits themselves", () => {
  assert.doesNotThrow(() => buildIdentity("x".repeat(256), ["r".repeat(50)], DS));
  assert.doesNotThrow(() => buildIdentity("a@b.c", Array.from({ length: 50 }, (_, i) => `r${i}`), DS));
});
