// Pure functions: model definition -> Dataverse Web API JSON payloads.
// Shapes follow Microsoft Learn:
//   create-update-entity-definitions-using-web-api, create-update-column-definitions-using-web-api,
//   create-update-entity-relationships-using-web-api, create-manage-model-driven-apps-using-code.
import type { AppDef, ColumnDef, LookupDef, Publisher, Solution, TableDef } from "../model/equipmentDesk.ts";

export const LCID = 1033;
// Default app icon web resource documented on Learn ("create-manage-model-driven-apps-using-code").
export const DEFAULT_APP_ICON = "953b9fac-1e5e-e611-80d6-00155ded156f";

export function label(text: string) {
  return {
    "@odata.type": "Microsoft.Dynamics.CRM.Label",
    LocalizedLabels: [{ "@odata.type": "Microsoft.Dynamics.CRM.LocalizedLabel", Label: text, LanguageCode: LCID }],
  };
}

function requiredLevel(required?: boolean) {
  return {
    Value: required ? "ApplicationRequired" : "None",
    CanBeChanged: true,
    ManagedPropertyLogicalName: "canmodifyrequirementlevelsettings",
  };
}

export const logicalName = (schemaName: string) => schemaName.toLowerCase();

/** Every schema name must carry the publisher prefix, or Dataverse rejects it. */
export function assertPrefixed(schemaName: string, prefix: string): void {
  if (!schemaName.toLowerCase().startsWith(`${prefix.toLowerCase()}_`)) {
    throw new Error(`${schemaName} must start with the publisher prefix '${prefix}_'`);
  }
}

/** Choice values: optionValuePrefix * 10000 + index (e.g. 41500 -> 415000000, 415000001, ...). */
export function optionValue(prefix: number, index: number): number {
  if (prefix < 10000 || prefix > 99999) throw new Error("optionValuePrefix must be between 10000 and 99999");
  return prefix * 10000 + index;
}

export function columnPayload(col: ColumnDef, pub: Publisher): Record<string, unknown> {
  assertPrefixed(col.schemaName, pub.prefix);
  const common = {
    SchemaName: col.schemaName,
    DisplayName: label(col.displayName),
    Description: label(col.description),
    RequiredLevel: requiredLevel(col.required),
  };
  switch (col.kind) {
    case "string":
      return {
        "@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata",
        AttributeType: "String",
        AttributeTypeName: { Value: "StringType" },
        ...common,
        MaxLength: col.maxLength,
        FormatName: { Value: col.format ?? "Text" },
      };
    case "memo":
      return {
        "@odata.type": "Microsoft.Dynamics.CRM.MemoAttributeMetadata",
        AttributeType: "Memo",
        AttributeTypeName: { Value: "MemoType" },
        ...common,
        Format: "TextArea",
        MaxLength: col.maxLength,
      };
    case "date":
      // Without DateTimeBehavior the column is created as UserLocal, and a "date only" value
      // can then show as the previous day for users in another time zone.
      return {
        "@odata.type": "Microsoft.Dynamics.CRM.DateTimeAttributeMetadata",
        AttributeType: "DateTime",
        AttributeTypeName: { Value: "DateTimeType" },
        ...common,
        Format: "DateOnly",
        DateTimeBehavior: { Value: "DateOnly" },
      };
    case "choice": {
      const options = col.options.map((text, i) => ({ Value: optionValue(pub.optionValuePrefix, i), Label: label(text) }));
      const payload: Record<string, unknown> = {
        "@odata.type": "Microsoft.Dynamics.CRM.PicklistAttributeMetadata",
        AttributeType: "Picklist",
        AttributeTypeName: { Value: "PicklistType" },
        ...common,
        OptionSet: {
          "@odata.type": "Microsoft.Dynamics.CRM.OptionSetMetadata",
          IsGlobal: false,
          OptionSetType: "Picklist",
          Options: options,
        },
      };
      if (col.defaultOption !== undefined) {
        const i = col.options.indexOf(col.defaultOption);
        if (i < 0) throw new Error(`Default option '${col.defaultOption}' is not one of ${col.options.join(", ")}`);
        payload.DefaultFormValue = optionValue(pub.optionValuePrefix, i);
      }
      return payload;
    }
  }
}

/** POST /EntityDefinitions body: the table plus its primary name column (the only column allowed inline here). */
export function tablePayload(table: TableDef, pub: Publisher): Record<string, unknown> {
  assertPrefixed(table.schemaName, pub.prefix);
  assertPrefixed(table.primaryName.schemaName, pub.prefix);
  return {
    "@odata.type": "Microsoft.Dynamics.CRM.EntityMetadata",
    SchemaName: table.schemaName,
    DisplayName: label(table.displayName),
    DisplayCollectionName: label(table.pluralName),
    Description: label(table.description),
    OwnershipType: "UserOwned",
    IsActivity: false,
    HasActivities: false,
    HasNotes: true,
    Attributes: [
      {
        "@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata",
        AttributeType: "String",
        AttributeTypeName: { Value: "StringType" },
        SchemaName: table.primaryName.schemaName,
        DisplayName: label(table.primaryName.displayName),
        Description: label(`Primary name of the ${table.displayName.toLowerCase()} row.`),
        RequiredLevel: requiredLevel(true),
        MaxLength: table.primaryName.maxLength,
        FormatName: { Value: "Text" },
        IsPrimaryName: true,
      },
    ],
  };
}

/** POST /RelationshipDefinitions body: one-to-many with the lookup created by deep insert. */
export function lookupPayload(lk: LookupDef, pub: Publisher): Record<string, unknown> {
  assertPrefixed(lk.relationshipSchemaName, pub.prefix);
  assertPrefixed(lk.lookupSchemaName, pub.prefix);
  const keep = "NoCascade";
  return {
    "@odata.type": "Microsoft.Dynamics.CRM.OneToManyRelationshipMetadata",
    SchemaName: lk.relationshipSchemaName,
    ReferencedEntity: lk.referencedTable,
    ReferencedAttribute: `${lk.referencedTable}id`,
    ReferencingEntity: lk.referencingTable,
    AssociatedMenuConfiguration: { Behavior: "UseCollectionName", Group: "Details", Order: 10000 },
    CascadeConfiguration: {
      Assign: keep, Delete: lk.deleteBehavior, Merge: keep, Reparent: keep, Share: keep, Unshare: keep,
    },
    Lookup: {
      "@odata.type": "Microsoft.Dynamics.CRM.LookupAttributeMetadata",
      AttributeType: "Lookup",
      AttributeTypeName: { Value: "LookupType" },
      SchemaName: lk.lookupSchemaName,
      DisplayName: label(lk.displayName),
      Description: label(lk.description),
      RequiredLevel: requiredLevel(lk.required),
    },
  };
}

const xmlEscape = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** Site map: one area, one group, one subarea per table (Area > Group > SubArea). */
export function sitemapXml(app: AppDef, tableLogicalNames: string[]): string {
  const subAreas = tableLogicalNames
    .map((t) => `      <SubArea Id="sub_${t}" Entity="${xmlEscape(t)}" />`)
    .join("\n");
  return [
    "<SiteMap>",
    `  <Area Id="area_main" ShowGroups="true">`,
    `    <Titles><Title LCID="${LCID}" Title="${xmlEscape(app.areaTitle)}" /></Titles>`,
    `    <Group Id="grp_main">`,
    `      <Titles><Title LCID="${LCID}" Title="${xmlEscape(app.groupTitle)}" /></Titles>`,
    subAreas,
    "    </Group>",
    "  </Area>",
    "</SiteMap>",
  ].join("\n");
}

export function publisherPayload(pub: Publisher) {
  return {
    uniquename: pub.uniqueName,
    friendlyname: pub.friendlyName,
    customizationprefix: pub.prefix,
    customizationoptionvalueprefix: pub.optionValuePrefix,
  };
}

export function solutionPayload(sol: Solution, publisherId: string) {
  return {
    uniquename: sol.uniqueName,
    friendlyname: sol.friendlyName,
    version: sol.version,
    "publisherid@odata.bind": `/publishers(${publisherId})`,
  };
}

export function appModulePayload(app: AppDef) {
  // Learn: uniquename "can only have English characters and numbers"; the publisher prefix is added on create.
  if (!/^[A-Za-z0-9]+$/.test(app.uniqueName)) throw new Error(`App unique name '${app.uniqueName}' may only contain English letters and numbers`);
  return { name: app.name, uniquename: app.uniqueName, description: app.description, webresourceid: DEFAULT_APP_ICON };
}

export function publishAppXml(appId: string, tableLogicalNames: string[]): string {
  const entities = tableLogicalNames.map((t) => `<entity>${t}</entity>`).join("");
  return `<importexportxml><entities>${entities}</entities><appmodules><appmodule>${appId}</appmodule></appmodules></importexportxml>`;
}
