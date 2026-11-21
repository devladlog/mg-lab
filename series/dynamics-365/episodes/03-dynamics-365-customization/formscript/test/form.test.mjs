import test from "node:test";
import assert from "node:assert/strict";
import { CONFIG, loadBundle, resolveHandler, fakeWebApi, fakeForm, ACCOUNT } from "./harness.mjs";

const NOTE = "mgl-open-requests";

test("the OnLoad handler named in customization.json exists in the built web resource", () => {
  const ctx = loadBundle(fakeWebApi());
  assert.equal(typeof resolveHandler(ctx, CONFIG.form.onload), "function");
});

test("the web resource name starts with the publisher prefix and an underscore", () => {
  assert.ok(CONFIG.webresource.name.startsWith(`${CONFIG.publisher_prefix}_`));
});

test("onLoad on an existing record locks Request Code", async () => {
  const ctx = loadBundle(fakeWebApi());
  const f = fakeForm({ formType: 2, values: { mgl_requestcode: "PR-0002", mgl_customeraccountid: null } });
  await resolveHandler(ctx, CONFIG.form.onload)(f.executionContext);
  assert.equal(f.disabled.get("mgl_requestcode"), true);
});

test("onLoad on a new record leaves Request Code editable", async () => {
  const ctx = loadBundle(fakeWebApi());
  const f = fakeForm({ formType: 1, id: "", values: { mgl_requestcode: null, mgl_customeraccountid: null } });
  await resolveHandler(ctx, CONFIG.form.onload)(f.executionContext);
  assert.equal(f.disabled.has("mgl_requestcode"), false);
});

test("onLoad doesn't fail when Request Code and the account lookup aren't on the form", async () => {
  const api = fakeWebApi();
  const ctx = loadBundle(api);
  const f = fakeForm({ values: {} });
  const codes = await resolveHandler(ctx, CONFIG.form.onload)(f.executionContext);
  assert.deepEqual([...codes], []);
  assert.equal(api.calls.length, 0);
});

test("no account: no query, no notification", async () => {
  const api = fakeWebApi({ entities: [{ mgl_requestcode: "PR-0009" }] });
  const ctx = loadBundle(api);
  const f = fakeForm({ values: { mgl_customeraccountid: null } });
  await resolveHandler(ctx, CONFIG.form.onload)(f.executionContext);
  assert.equal(api.calls.length, 0);
  assert.equal(f.notifications.size, 0);
});

test("other open requests for the account show a WARNING with their codes", async () => {
  const api = fakeWebApi({ entities: [{ mgl_requestcode: "PR-0004" }, { mgl_requestcode: "PR-0011" }] });
  const ctx = loadBundle(api);
  const f = fakeForm({ values: { mgl_customeraccountid: ACCOUNT } });
  const codes = await resolveHandler(ctx, CONFIG.form.onload)(f.executionContext);
  assert.deepEqual([...codes], ["PR-0004", "PR-0011"]);
  assert.deepEqual(f.notifications.get(NOTE), {
    level: "WARNING",
    message: "Contoso Ltd already has 2 open requests: PR-0004, PR-0011.",
  });
});

test("the query filters by account, active state and excludes the current record (bare, lower-case GUIDs)", async () => {
  const api = fakeWebApi();
  const ctx = loadBundle(api);
  const f = fakeForm({ id: "{BBBBBBBB-0000-0000-0000-00000000000B}", values: { mgl_customeraccountid: ACCOUNT } });
  await resolveHandler(ctx, CONFIG.form.onload)(f.executionContext);
  assert.equal(api.calls.length, 1);
  const { table, options, maxPageSize } = api.calls[0];
  assert.equal(table, "mgl_projectrequest");
  assert.equal(maxPageSize, 6);
  const filter = decodeURIComponent(options.match(/\$filter=([^&]*)/)[1]);
  assert.equal(filter, "_mgl_customeraccountid_value eq aaaaaaaa-0000-0000-0000-00000000000a and statecode eq 0 " +
    "and mgl_projectrequestid ne bbbbbbbb-0000-0000-0000-00000000000b");
  assert.ok(options.startsWith("?$select=mgl_requestcode&"));
  assert.ok(!options.includes(" "), "OData options must be encoded");
});

test("on a new record (no id yet) the query has no 'ne' clause", async () => {
  const api = fakeWebApi();
  const ctx = loadBundle(api);
  const f = fakeForm({ formType: 1, id: "", values: { mgl_customeraccountid: ACCOUNT } });
  await resolveHandler(ctx, CONFIG.form.onload)(f.executionContext);
  assert.ok(!decodeURIComponent(api.calls[0].options).includes(" ne "));
});

test("more than five open requests: lists five and says 5+", async () => {
  const entities = Array.from({ length: 6 }, (_, i) => ({ mgl_requestcode: `PR-00${10 + i}` }));
  const ctx = loadBundle(fakeWebApi({ entities }));
  const f = fakeForm({ values: { mgl_customeraccountid: ACCOUNT } });
  await resolveHandler(ctx, CONFIG.form.onload)(f.executionContext);
  assert.equal(f.notifications.get(NOTE).message,
    "Contoso Ltd already has 5+ open requests: PR-0010, PR-0011, PR-0012, PR-0013, PR-0014 and more.");
});

test("changing the account re-runs the check and clears a stale warning", async () => {
  const api = fakeWebApi({ entities: [{ mgl_requestcode: "PR-0004" }] });
  const ctx = loadBundle(api);
  const f = fakeForm({ values: { mgl_customeraccountid: ACCOUNT } });
  await resolveHandler(ctx, CONFIG.form.onload)(f.executionContext);
  assert.ok(f.notifications.has(NOTE));
  assert.equal(f.onChange.get("mgl_customeraccountid").length, 1, "onLoad registers exactly one OnChange handler");

  await f.change("mgl_customeraccountid", null);          // user clears the lookup
  assert.equal(f.notifications.has(NOTE), false);
  assert.equal(api.calls.length, 1);
});

test("a failing Web API call shows an INFO notification and never throws", async () => {
  const ctx = loadBundle(fakeWebApi({ error: { errorCode: 2147746611, message: "Principal user is missing prvReadmgl_ProjectRequest" } }));
  const f = fakeForm({ values: { mgl_customeraccountid: ACCOUNT } });
  const codes = await resolveHandler(ctx, CONFIG.form.onload)(f.executionContext);
  assert.deepEqual([...codes], []);
  assert.equal(f.notifications.get(NOTE).level, "INFO");
  assert.match(f.notifications.get(NOTE).message, /^Couldn't check open requests: Principal user/);
});

test("cleanId strips braces and lower-cases", () => {
  const ctx = loadBundle(fakeWebApi());
  const { cleanId } = ctx.MGL.ProjectRequest;
  assert.equal(cleanId("{ABCDEF00-0000-0000-0000-000000000000}"), "abcdef00-0000-0000-0000-000000000000");
  assert.equal(cleanId(null), "");
});
