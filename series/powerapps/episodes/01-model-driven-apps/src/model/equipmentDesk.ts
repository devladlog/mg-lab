// The data model and app for "Equipment Desk", described as plain data.
// provision/metadata.ts turns this into Dataverse Web API payloads.
// Everything is fictional (Contoso); no tenant-specific values live here.

export interface Publisher {
  uniqueName: string;
  friendlyName: string;
  prefix: string;            // 2-8 chars, becomes contoso_ on every schema name
  optionValuePrefix: number; // 10000-99999, choice values start at prefix * 10000
}

export interface Solution {
  uniqueName: string;
  friendlyName: string;
  version: string;
}

interface ColumnBase {
  schemaName: string;
  displayName: string;
  description: string;
  required?: boolean;
}

export type ColumnDef =
  | (ColumnBase & { kind: "string"; maxLength: number; format?: "Text" | "Email" })
  | (ColumnBase & { kind: "memo"; maxLength: number })
  | (ColumnBase & { kind: "date" })
  | (ColumnBase & { kind: "choice"; options: string[]; defaultOption?: string });

export interface TableDef {
  schemaName: string;
  displayName: string;
  pluralName: string;
  description: string;
  primaryName: { schemaName: string; displayName: string; maxLength: number };
  columns: ColumnDef[];
}

export interface LookupDef {
  relationshipSchemaName: string;
  referencedTable: string;  // the "one" side (logical name)
  referencingTable: string; // the "many" side (logical name)
  lookupSchemaName: string;
  displayName: string;
  description: string;
  required: boolean;
  deleteBehavior: "Restrict" | "Cascade" | "RemoveLink";
}

export interface AppDef {
  uniqueName: string;
  name: string;
  description: string;
  areaTitle: string;
  groupTitle: string;
}

export const publisher: Publisher = {
  uniqueName: "contoso",
  friendlyName: "Contoso",
  prefix: "contoso",
  optionValuePrefix: 41500,
};

export const solution: Solution = {
  uniqueName: "EquipmentDesk",
  friendlyName: "Equipment Desk",
  version: "1.0.0.0",
};

export const equipment: TableDef = {
  schemaName: "contoso_Equipment",
  displayName: "Equipment",
  pluralName: "Equipment",
  description: "A laptop, monitor, phone or accessory that can be lent to an employee.",
  primaryName: { schemaName: "contoso_Name", displayName: "Name", maxLength: 100 },
  columns: [
    { kind: "string", schemaName: "contoso_AssetTag", displayName: "Asset tag", description: "Label on the device, e.g. CT-0042.", maxLength: 20, required: true },
    { kind: "choice", schemaName: "contoso_Category", displayName: "Category", description: "Kind of equipment.", options: ["Laptop", "Monitor", "Phone", "Accessory"] },
    { kind: "string", schemaName: "contoso_SerialNumber", displayName: "Serial number", description: "Manufacturer serial number.", maxLength: 50 },
    { kind: "choice", schemaName: "contoso_Status", displayName: "Status", description: "Where the device is right now.", options: ["Available", "On loan", "In repair", "Retired"], defaultOption: "Available" },
    { kind: "date", schemaName: "contoso_PurchaseDate", displayName: "Purchase date", description: "Date the device was bought." },
  ],
};

export const loan: TableDef = {
  schemaName: "contoso_Loan",
  displayName: "Loan",
  pluralName: "Loans",
  description: "One device lent to one employee for a period.",
  primaryName: { schemaName: "contoso_Name", displayName: "Loan", maxLength: 100 },
  columns: [
    { kind: "string", schemaName: "contoso_BorrowerEmail", displayName: "Borrower email", description: "Work email of the employee.", maxLength: 100, format: "Email", required: true },
    { kind: "date", schemaName: "contoso_LoanDate", displayName: "Loan date", description: "Day the device left the desk.", required: true },
    { kind: "date", schemaName: "contoso_DueDate", displayName: "Due date", description: "Day the device must be back.", required: true },
    { kind: "date", schemaName: "contoso_ReturnedOn", displayName: "Returned on", description: "Day the device came back. Empty while on loan." },
    { kind: "memo", schemaName: "contoso_Notes", displayName: "Notes", description: "Condition on return, accessories, etc.", maxLength: 2000 },
  ],
};

export const loanEquipment: LookupDef = {
  relationshipSchemaName: "contoso_equipment_contoso_loan",
  referencedTable: "contoso_equipment",
  referencingTable: "contoso_loan",
  lookupSchemaName: "contoso_EquipmentId",
  displayName: "Equipment",
  description: "The device that is lent.",
  required: true,
  // A device with loan history can't be deleted: retire it instead.
  deleteBehavior: "Restrict",
};

export const app: AppDef = {
  // English letters and numbers only; Dataverse adds the publisher prefix (contoso_EquipmentDesk).
  uniqueName: "EquipmentDesk",
  name: "Equipment Desk",
  description: "Lend and track Contoso equipment.",
  areaTitle: "Equipment Desk",
  groupTitle: "Lending",
};

export const tables: TableDef[] = [equipment, loan];
export const lookups: LookupDef[] = [loanEquipment];
