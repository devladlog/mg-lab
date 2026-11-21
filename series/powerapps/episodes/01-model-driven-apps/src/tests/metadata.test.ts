import { test } from "node:test";
import assert from "node:assert/strict";
import * as model from "../model/equipmentDesk.ts";
import {
  appModulePayload, assertPrefixed, columnPayload, lookupPayload, optionValue, publishAppXml, sitemapXml, tablePayload,
} from "../provision/metadata.ts";

const pub = model.publisher;

test("every schema name in the model carries the publisher prefix", () => {
  for (const t of model.tables) {
    assertPrefixed(t.schemaName, pub.prefix);
    for (const c of t.columns) assertPrefixed(c.schemaName, pub.prefix);
  }
  assert.throws(() => assertPrefixed("new_Thing", "contoso"), /contoso_/);
});

test("table payload has the required properties and exactly one primary name column", () => {
  const p = tablePayload(model.equipment, pub) as any;
  for (const k of ["SchemaName", "DisplayName", "DisplayCollectionName", "OwnershipType", "IsActivity", "HasActivities", "HasNotes"]) {
    assert.ok(k in p, `missing ${k}`);
  }
  assert.equal(p.Attributes.length, 1);
  assert.equal(p.Attributes[0].IsPrimaryName, true);
  assert.equal(p.Attributes[0].FormatName.Value, "Text");
  assert.equal(p.DisplayName.LocalizedLabels[0].LanguageCode, 1033);
});

test("choice values use the publisher option value prefix", () => {
  assert.equal(optionValue(41500, 0), 415000000);
  assert.throws(() => optionValue(9999, 0));
  const status = model.equipment.columns.find((c) => c.schemaName === "contoso_Status")!;
  const p = columnPayload(status, pub) as any;
  assert.deepEqual(p.OptionSet.Options.map((o: any) => o.Value), [415000000, 415000001, 415000002, 415000003]);
  assert.equal(p.DefaultFormValue, 415000000);
  assert.equal(p.OptionSet.IsGlobal, false);
});

test("a bad default option fails before any request is sent", () => {
  assert.throws(() => columnPayload({ kind: "choice", schemaName: "contoso_X", displayName: "X", description: "", options: ["A"], defaultOption: "B" }, pub), /Default option/);
});

test("date columns are created DateOnly (not the UserLocal default)", () => {
  const due = model.loan.columns.find((c) => c.schemaName === "contoso_DueDate")!;
  const p = columnPayload(due, pub) as any;
  assert.equal(p.Format, "DateOnly");
  assert.deepEqual(p.DateTimeBehavior, { Value: "DateOnly" });
  assert.equal(p.RequiredLevel.Value, "ApplicationRequired");
});

test("email column uses the Email format", () => {
  const email = model.loan.columns.find((c) => c.schemaName === "contoso_BorrowerEmail")!;
  assert.equal((columnPayload(email, pub) as any).FormatName.Value, "Email");
});

test("lookup: one-to-many with restrict delete and the lookup created inline", () => {
  const p = lookupPayload(model.loanEquipment, pub) as any;
  assert.equal(p["@odata.type"], "Microsoft.Dynamics.CRM.OneToManyRelationshipMetadata");
  assert.equal(p.ReferencedEntity, "contoso_equipment");
  assert.equal(p.ReferencedAttribute, "contoso_equipmentid");
  assert.equal(p.ReferencingEntity, "contoso_loan");
  assert.equal(p.CascadeConfiguration.Delete, "Restrict");
  assert.equal(p.Lookup.SchemaName, "contoso_EquipmentId");
});

test("site map lists each table once, inside one area and group", () => {
  const xml = sitemapXml({ ...model.app, groupTitle: "Lending & returns" }, ["contoso_loan", "contoso_equipment"]);
  assert.match(xml, /<Area Id="area_main" ShowGroups="true">/);
  assert.equal(xml.match(/<SubArea /g)?.length, 2);
  assert.match(xml, /Entity="contoso_loan"/);
  assert.match(xml, /Title="Lending &amp; returns"/);
});

test("app module payload uses the documented default icon and a letters-only unique name", () => {
  const p = appModulePayload(model.app);
  assert.equal(p.webresourceid, "953b9fac-1e5e-e611-80d6-00155ded156f");
  assert.throws(() => appModulePayload({ ...model.app, uniqueName: "contoso_EquipmentDesk" }), /letters and numbers/);
});

test("publish xml covers the tables and the app", () => {
  const id = "00000000-0000-0000-0000-000000000000";
  assert.equal(publishAppXml(id, ["contoso_equipment"]),
    `<importexportxml><entities><entity>contoso_equipment</entity></entities><appmodules><appmodule>${id}</appmodule></appmodules></importexportxml>`);
});
