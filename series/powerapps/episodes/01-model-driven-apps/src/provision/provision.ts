// Provision "Equipment Desk" in a Dataverse environment through the Web API.
// Every step checks first and only creates what is missing, so the script can be re-run safely.
//
//   DATAVERSE_URL=https://contoso-dev.crm4.dynamics.com \
//   DATAVERSE_TOKEN=$(az account get-access-token --resource $DATAVERSE_URL --query accessToken -o tsv) \
//   node provision/provision.ts [--role "Basic User"] [--webresource dist/contoso_/scripts/loanform.js]
//
//   node provision/provision.ts --dry-run     # prints every request, sends nothing
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import * as model from "../model/equipmentDesk.ts";
import { DataverseClient, odataString, type FetchLike } from "./dataverse.ts";
import {
  appModulePayload, columnPayload, logicalName, lookupPayload, publishAppXml, publisherPayload,
  sitemapXml, solutionPayload, tablePayload,
} from "./metadata.ts";

export const WEBRESOURCE_NAME = "contoso_/scripts/loanform.js";

export interface ProvisionOptions {
  role?: string;
  webResourcePath?: string;
  log?: (line: string) => void;
}

export interface ProvisionResult {
  created: string[];
  existing: string[];
  appId: string;
  validation: { ValidationSuccess: boolean; ValidationIssueList: Array<{ ErrorType: string; Message: string }> };
}

export async function provision(dv: DataverseClient, opts: ProvisionOptions = {}): Promise<ProvisionResult> {
  const log = opts.log ?? (() => {});
  const created: string[] = [];
  const existing: string[] = [];
  const note = (made: boolean, what: string) => {
    (made ? created : existing).push(what);
    log(`${made ? "created " : "exists  "} ${what}`);
  };
  const inSolution = { "MSCRM.SolutionUniqueName": model.solution.uniqueName };
  const pub = model.publisher;

  // 1. Publisher + solution: everything else is created inside this solution.
  const publisher = await dv.first(`publishers?$select=publisherid,customizationprefix&$filter=uniquename eq ${odataString(pub.uniqueName)}`);
  if (publisher && publisher.customizationprefix !== pub.prefix) {
    throw new Error(`Publisher '${pub.uniqueName}' exists with prefix '${publisher.customizationprefix}', expected '${pub.prefix}'`);
  }
  const publisherId: string = publisher?.publisherid ?? (await dv.request("POST", "publishers", publisherPayload(pub))).entityId!;
  note(!publisher, `publisher ${pub.uniqueName}`);

  const solution = await dv.first(`solutions?$select=solutionid&$filter=uniquename eq ${odataString(model.solution.uniqueName)}`);
  if (!solution) await dv.request("POST", "solutions", solutionPayload(model.solution, publisherId));
  note(!solution, `solution ${model.solution.uniqueName}`);

  // 2. Tables and columns.
  const tableIds = new Map<string, string>();
  for (const table of model.tables) {
    const t = logicalName(table.schemaName);
    let def = await dv.tryGet(`EntityDefinitions(LogicalName=${odataString(t)})?$select=MetadataId`);
    const tableExisted = def !== null;
    if (!tableExisted) {
      await dv.request("POST", "EntityDefinitions", tablePayload(table, pub), inSolution);
      // Read it back: AddAppComponents needs the table's MetadataId.
      def = await dv.tryGet(`EntityDefinitions(LogicalName=${odataString(t)})?$select=MetadataId`);
    }
    note(!tableExisted, `table ${t}`);
    tableIds.set(t, def?.MetadataId);

    for (const col of table.columns) {
      const c = logicalName(col.schemaName);
      const attr = await dv.tryGet(`EntityDefinitions(LogicalName=${odataString(t)})/Attributes(LogicalName=${odataString(c)})?$select=MetadataId`);
      if (!attr) await dv.request("POST", `EntityDefinitions(LogicalName=${odataString(t)})/Attributes`, columnPayload(col, pub), inSolution);
      note(!attr, `column ${t}.${c}`);
    }
  }

  // 3. Relationships (the lookup column is created with the relationship).
  for (const lk of model.lookups) {
    const rel = await dv.tryGet(`RelationshipDefinitions(SchemaName=${odataString(lk.relationshipSchemaName)})?$select=MetadataId`);
    if (!rel) await dv.request("POST", "RelationshipDefinitions", lookupPayload(lk, pub), inSolution);
    note(!rel, `relationship ${lk.relationshipSchemaName}`);
  }

  // 4. Optional: the compiled form script as a JavaScript web resource (type 3 = Script (JScript)).
  if (opts.webResourcePath) {
    const content = readFileSync(opts.webResourcePath).toString("base64");
    const wr = await dv.first(`webresourceset?$select=webresourceid&$filter=name eq ${odataString(WEBRESOURCE_NAME)}`);
    if (wr) {
      await dv.request("PATCH", `webresourceset(${wr.webresourceid})`, { content });
      log(`updated  web resource ${WEBRESOURCE_NAME}`);
    } else {
      await dv.request("POST", "webresourceset", { name: WEBRESOURCE_NAME, displayname: "Loan form script", webresourcetype: 3, content }, inSolution);
      note(true, `web resource ${WEBRESOURCE_NAME}`);
    }
  }

  // 5. The app: app module, site map, components, validate, publish.
  const tableNames = model.tables.map((t) => logicalName(t.schemaName));
  const appFilter = `uniquename eq ${odataString(model.app.uniqueName)} or uniquename eq ${odataString(`${pub.prefix}_${model.app.uniqueName}`)}`;
  // New apps are unpublished, and a plain GET on appmodules only returns published ones.
  const appRow = await dv.first(`appmodules/Microsoft.Dynamics.CRM.RetrieveUnpublishedMultiple()?$select=appmoduleid&$filter=${appFilter}`);
  const appId: string = appRow?.appmoduleid ?? (await dv.request("POST", "appmodules", appModulePayload(model.app), inSolution)).entityId!;
  note(!appRow, `app ${model.app.name}`);

  const sitemapUnique = `${pub.prefix}_${model.app.uniqueName}`;
  const sitemap = await dv.first(`sitemaps/Microsoft.Dynamics.CRM.RetrieveUnpublishedMultiple()?$select=sitemapid&$filter=sitemapnameunique eq ${odataString(sitemapUnique)}`);
  const xml = sitemapXml(model.app, tableNames);
  let sitemapId: string;
  if (sitemap) {
    sitemapId = sitemap.sitemapid;
    await dv.request("PATCH", `sitemaps(${sitemapId})`, { sitemapxml: xml });
    log(`updated  site map ${sitemapUnique}`);
  } else {
    sitemapId = (await dv.request("POST", "sitemaps", { sitemapname: model.app.name, sitemapnameunique: sitemapUnique, isappaware: true, sitemapxml: xml }, inSolution)).entityId!;
    note(true, `site map ${sitemapUnique}`);
  }

  await dv.request("POST", "AddAppComponents", {
    AppId: appId,
    Components: [
      { "@odata.type": "Microsoft.Dynamics.CRM.sitemap", sitemapid: sitemapId },
      ...tableNames.map((t) => ({ "@odata.type": "Microsoft.Dynamics.CRM.entity", entityid: tableIds.get(t) })),
    ],
  });
  log(`added    site map + ${tableNames.length} tables to the app`);

  const validation = (await dv.request("GET", `ValidateApp(AppModuleId=${appId})`)).body?.AppValidationResponse ?? {
    ValidationSuccess: false, ValidationIssueList: [{ ErrorType: "Error", Message: "No ValidateApp response" }],
  };
  for (const issue of validation.ValidationIssueList) log(`validate ${issue.ErrorType}: ${issue.Message}`);
  if (validation.ValidationIssueList.some((i: { ErrorType: string }) => i.ErrorType === "Error")) {
    throw new Error("ValidateApp returned errors; not publishing.");
  }

  await dv.request("POST", "PublishXml", { ParameterXml: publishAppXml(appId, tableNames) });
  log("published tables and app");

  // 6. Optional: give a security role access to the app.
  if (opts.role) {
    const bu = await dv.first("businessunits?$select=businessunitid&$filter=_parentbusinessunitid_value eq null");
    const role = await dv.first(`roles?$select=roleid&$filter=name eq ${odataString(opts.role)} and _businessunitid_value eq ${bu.businessunitid}`);
    if (!role) throw new Error(`Security role '${opts.role}' not found in the root business unit`);
    await dv.request("POST", `appmodules(${appId})/appmoduleroles_association/$ref`, { "@odata.id": `${dvBase(dv)}roles(${role.roleid})` });
    log(`granted  app to role '${opts.role}'`);
  }

  return { created, existing, appId, validation };
}

function dvBase(dv: DataverseClient): string {
  return (dv as unknown as { base: string }).base;
}

/** A fetch that answers like an empty environment and records every request: used by --dry-run and tests. */
export function emptyEnvironmentFetch(record: Array<{ method: string; url: string; body?: any; headers: Record<string, string> }>): FetchLike {
  let n = 0;
  const fakeId = () => `00000000-0000-0000-0000-${String(++n).padStart(12, "0")}`;
  const created = new Set<string>();
  return async (url, init) => {
    const body = init.body ? JSON.parse(init.body) : undefined;
    record.push({ method: init.method, url, body, headers: init.headers });
    const path = url.split("/api/data/v9.2/")[1] ?? url;
    const reply = (status: number, json: unknown = null, entityId?: string) => ({
      status,
      headers: { get: (h: string) => (h.toLowerCase() === "odata-entityid" && entityId ? `${url}(${entityId})` : null) },
      text: async () => (json === null ? "" : JSON.stringify(json)),
    });
    if (init.method === "GET") {
      if (path.startsWith("ValidateApp")) return reply(200, { AppValidationResponse: { ValidationSuccess: true, ValidationIssueList: [] } });
      if (path.startsWith("businessunits")) return reply(200, { value: [{ businessunitid: fakeId() }] });
      if (path.startsWith("roles")) return reply(200, { value: [{ roleid: fakeId() }] });
      const def = /^EntityDefinitions\(LogicalName='([^']+)'\)\?/.exec(path);
      if (def && created.has(def[1])) return reply(200, { MetadataId: fakeId() });
      if (path.includes("?$select") && path.includes("$filter")) return reply(200, { value: [] });
      return reply(404, { error: { message: "Does Not Exist" } });
    }
    if (init.method === "POST" && path === "EntityDefinitions") created.add(String(body.SchemaName).toLowerCase());
    return reply(204, null, fakeId());
  };
}

async function main(argv: string[]) {
  const dryRun = argv.includes("--dry-run");
  const arg = (name: string) => {
    const i = argv.indexOf(name);
    return i >= 0 ? argv[i + 1] : undefined;
  };
  const opts: ProvisionOptions = { role: arg("--role"), webResourcePath: arg("--webresource"), log: (l) => console.log(l) };

  if (dryRun) {
    const record: Array<{ method: string; url: string; body?: any; headers: Record<string, string> }> = [];
    const dv = new DataverseClient("https://contoso-dev.crm4.dynamics.com", "dry-run", emptyEnvironmentFetch(record));
    await provision(dv, { ...opts, log: () => {} });
    for (const r of record) {
      const sol = r.headers["MSCRM.SolutionUniqueName"] ? `  [solution ${r.headers["MSCRM.SolutionUniqueName"]}]` : "";
      console.log(`${r.method.padEnd(5)} ${decodeURIComponent(r.url.split("/api/data/v9.2/")[1])}${sol}`);
    }
    console.log(`\n${record.length} requests, ${record.filter((r) => r.method !== "GET").length} writes (dry run: nothing sent)`);
    return;
  }

  const url = process.env.DATAVERSE_URL;
  const token = process.env.DATAVERSE_TOKEN;
  if (!url || !token) {
    console.error("Set DATAVERSE_URL and DATAVERSE_TOKEN (see README), or use --dry-run.");
    process.exit(2);
  }
  const result = await provision(new DataverseClient(url, token, fetch as unknown as FetchLike), opts);
  console.log(`\nDone: ${result.created.length} created, ${result.existing.length} already there. App id ${result.appId}`);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  main(process.argv.slice(2)).catch((e) => {
    console.error(e instanceof Error ? e.message : e);
    process.exit(1);
  });
}
