import { test } from "node:test";
import assert from "node:assert/strict";
import { writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DataverseClient, DataverseError, idFromEntityIdHeader, type FetchLike } from "../provision/dataverse.ts";
import { emptyEnvironmentFetch, provision, WEBRESOURCE_NAME } from "../provision/provision.ts";

type Rec = { method: string; url: string; body?: any; headers: Record<string, string> };
const ORG = "https://contoso-dev.crm4.dynamics.com";
const path = (r: Rec) => decodeURIComponent(r.url.split("/api/data/v9.2/")[1]);

test("OData-EntityId header -> id", () => {
  assert.equal(idFromEntityIdHeader(`${ORG}/api/data/v9.2/appmodules(00AA00AA-BB11-CC22-DD33-44EE44EE44EE)`), "00aa00aa-bb11-cc22-dd33-44ee44ee44ee");
  assert.equal(idFromEntityIdHeader(null), null);
});

test("empty environment: creates everything in order, inside the solution, then validates and publishes", async () => {
  const rec: Rec[] = [];
  const result = await provision(new DataverseClient(ORG, "t", emptyEnvironmentFetch(rec)));
  const writes = rec.filter((r) => r.method !== "GET").map((r) => `${r.method} ${path(r).split("(")[0]}`);
  assert.deepEqual(writes.slice(0, 3), ["POST publishers", "POST solutions", "POST EntityDefinitions"]);
  assert.deepEqual(writes.slice(-4), ["POST appmodules", "POST sitemaps", "POST AddAppComponents", "POST PublishXml"]);
  assert.equal(rec.filter((r) => r.method === "POST" && path(r) === "EntityDefinitions").length, 2);
  assert.equal(rec.filter((r) => r.method === "POST" && /Attributes$/.test(path(r))).length, 10);

  for (const r of rec.filter((r) => r.method === "POST" && /^(EntityDefinitions|RelationshipDefinitions|appmodules|sitemaps)/.test(path(r)))) {
    assert.equal(r.headers["MSCRM.SolutionUniqueName"], "EquipmentDesk", `${path(r)} must be created in the solution`);
  }
  for (const r of rec) assert.equal(r.headers.Authorization, "Bearer t");
  assert.equal(result.created.length, 17); // publisher, solution, 2 tables, 10 columns, 1 relationship, app, site map
  assert.equal(result.validation.ValidationSuccess, true);
});

test("AddAppComponents sends the site map and both tables by MetadataId", async () => {
  const rec: Rec[] = [];
  await provision(new DataverseClient(ORG, "t", emptyEnvironmentFetch(rec)));
  const add = rec.find((r) => path(r) === "AddAppComponents")!;
  const types = add.body.Components.map((c: any) => c["@odata.type"]);
  assert.deepEqual(types, ["Microsoft.Dynamics.CRM.sitemap", "Microsoft.Dynamics.CRM.entity", "Microsoft.Dynamics.CRM.entity"]);
  assert.ok(add.body.Components.every((c: any) => /^[0-9a-f-]{36}$/.test(c.sitemapid ?? c.entityid)));
});

test("re-run against a provisioned environment creates nothing new", async () => {
  const rec: Rec[] = [];
  const everythingExists: FetchLike = async (url, init) => {
    rec.push({ method: init.method, url, headers: init.headers, body: init.body && JSON.parse(init.body) });
    const p = url.split("/api/data/v9.2/")[1];
    const row = { publisherid: "p", customizationprefix: "contoso", solutionid: "s", appmoduleid: "00000000-0000-0000-0000-0000000000a1", sitemapid: "00000000-0000-0000-0000-0000000000b1" };
    let json: unknown = null;
    if (init.method === "GET") json = p.startsWith("ValidateApp")
      ? { AppValidationResponse: { ValidationSuccess: true, ValidationIssueList: [] } }
      : p.includes("$filter") ? { value: [row] } : { MetadataId: "00000000-0000-0000-0000-0000000000c1" };
    return { status: json ? 200 : 204, headers: { get: () => null }, text: async () => (json ? JSON.stringify(json) : "") };
  };
  const result = await provision(new DataverseClient(ORG, "t", everythingExists));
  assert.deepEqual(result.created, []);
  const creates = rec.filter((r) => r.method === "POST" && !["AddAppComponents", "PublishXml"].includes(path(r)));
  assert.deepEqual(creates, []);
  assert.ok(rec.some((r) => r.method === "PATCH" && path(r).startsWith("sitemaps(")), "site map XML is refreshed");
});

test("a publisher with a different prefix stops the run before any write", async () => {
  const rec: Rec[] = [];
  const wrongPrefix: FetchLike = async (url, init) => {
    rec.push({ method: init.method, url, headers: init.headers });
    return { status: 200, headers: { get: () => null }, text: async () => JSON.stringify({ value: [{ publisherid: "p", customizationprefix: "cr8a3" }] }) };
  };
  await assert.rejects(provision(new DataverseClient(ORG, "t", wrongPrefix)), /prefix 'cr8a3'/);
  assert.equal(rec.filter((r) => r.method !== "GET").length, 0);
});

test("validation errors stop the publish", async () => {
  const rec: Rec[] = [];
  const base = emptyEnvironmentFetch(rec);
  const failingValidate: FetchLike = async (url, init) => {
    if (url.includes("ValidateApp")) return { status: 200, headers: { get: () => null },
      text: async () => JSON.stringify({ AppValidationResponse: { ValidationSuccess: false, ValidationIssueList: [{ ErrorType: "Error", Message: "App does not contain Site Map" }] } }) };
    return base(url, init);
  };
  const lines: string[] = [];
  await assert.rejects(provision(new DataverseClient(ORG, "t", failingValidate), { log: (l) => lines.push(l) }), /not publishing/);
  assert.ok(lines.includes("validate Error: App does not contain Site Map"));
  assert.ok(!rec.some((r) => path(r) === "PublishXml"));
});

test("web resource is uploaded as base64 script (type 3), and the role gets the app", async () => {
  const dir = mkdtempSync(join(tmpdir(), "wr-"));
  const file = join(dir, "loanform.js");
  writeFileSync(file, "var Contoso={};");
  const rec: Rec[] = [];
  await provision(new DataverseClient(ORG, "t", emptyEnvironmentFetch(rec)), { webResourcePath: file, role: "Basic User" });
  const wr = rec.find((r) => r.method === "POST" && path(r) === "webresourceset")!;
  assert.equal(wr.body.name, WEBRESOURCE_NAME);
  assert.equal(wr.body.webresourcetype, 3);
  assert.equal(Buffer.from(wr.body.content, "base64").toString(), "var Contoso={};");
  const ref = rec.find((r) => /appmoduleroles_association\/\$ref$/.test(path(r)))!;
  assert.match(ref.body["@odata.id"], /\/api\/data\/v9\.2\/roles\([0-9a-f-]{36}\)$/);
  assert.match(path(rec.find((r) => path(r).startsWith("roles?"))!), /name eq 'Basic User'/);
});

test("HTTP errors carry the Dataverse message", async () => {
  const failing: FetchLike = async () => ({ status: 403, headers: { get: () => null }, text: async () => JSON.stringify({ error: { message: "Principal user is missing prvCreateEntity privilege" } }) });
  const dv = new DataverseClient(ORG, "t", failing);
  await assert.rejects(dv.request("POST", "EntityDefinitions", {}), (e: unknown) => e instanceof DataverseError && e.status === 403 && /prvCreateEntity/.test(e.message));
});
