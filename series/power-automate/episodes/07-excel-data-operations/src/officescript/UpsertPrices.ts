// Office Script: paste into Excel on the web > Automate > New script, save as "Upsert prices"
// in the Purchasing site's Scripts library, run it from Power Automate with
// "Run script from SharePoint library" (Excel Online (Business) connector).
//
// One call writes the whole price list: read the Catalogue table once, update the changed
// rows in memory, write them back with one setValues and append new SKUs with one addRows.

interface PriceRow {
  sku: string;
  description: string;
  price: number;
  validFrom: string;
}

interface PriceChange {
  sku: string;
  description: string;
  oldPrice: number;
  newPrice: number;
  changePercent: number;
}

interface ImportResult {
  received: number;
  inserted: number;
  updated: number;
  unchanged: number;
  duplicatesInFile: number;
  duplicateRowsInCatalogue: number;
  textsEscaped: number;
  bigChanges: PriceChange[];
}

/**
 * Upserts a supplier price list into the Catalogue table by SKU.
 * @param prices Rows from the supplier file, already shaped by the flow (sku, description, price, validFrom as yyyy-MM-dd).
 * @param supplier Supplier name written on every row this run inserts or updates.
 * @param sourceFile File name of the supplier workbook, written in the Source column.
 * @param changeThreshold Price changes larger than this fraction are returned in bigChanges (0.2 = 20%).
 */
function main(
  workbook: ExcelScript.Workbook,
  prices: PriceRow[],
  supplier: string,
  sourceFile: string,
  changeThreshold: number = 0.2
): ImportResult {
  // 1. Validate everything before writing anything (no half-updated catalogue).
  const table = workbook.getTable("Catalogue");
  if (!table) {
    throw new Error("Table 'Catalogue' wasn't found in this workbook.");
  }
  const headers: string[] = table.getHeaderRowRange().getValues()[0].map((h) => String(h));
  const required: string[] = ["SKU", "Description", "Unit price", "Valid from", "Supplier", "Source"];
  required.forEach((name) => {
    if (headers.indexOf(name) < 0) {
      throw new Error(`Column '${name}' wasn't found in table Catalogue.`);
    }
  });
  const cSku = headers.indexOf("SKU");
  const cDesc = headers.indexOf("Description");
  const cPrice = headers.indexOf("Unit price");
  const cValid = headers.indexOf("Valid from");
  const cSupplier = headers.indexOf("Supplier");
  const cSource = headers.indexOf("Source");

  prices.forEach((p, i) => {
    if (!p.sku || p.sku.trim() === "") {
      throw new Error(`Row ${i + 1}: SKU is empty.`);
    }
    if (typeof p.price !== "number" || !isFinite(p.price) || p.price <= 0) {
      throw new Error(`Row ${i + 1} (${p.sku}): price must be a number greater than zero.`);
    }
    if (isNaN(toSerial(p.validFrom))) {
      throw new Error(`Row ${i + 1} (${p.sku}): valid from '${p.validFrom}' isn't a yyyy-MM-dd date.`);
    }
  });

  // 2. The last row wins when the supplier lists a SKU twice.
  const incoming = new Map<string, PriceRow>();
  let duplicatesInFile = 0;
  prices.forEach((p) => {
    const key = normalise(p.sku);
    if (incoming.has(key)) {
      duplicatesInFile++;
    }
    incoming.set(key, p);
  });

  // 3. Read the catalogue once.
  const rowCount = table.getRowCount();
  const body = rowCount > 0 ? table.getRangeBetweenHeaderAndTotal() : undefined;
  const values: (string | number | boolean)[][] = body ? body.getValues() : [];
  const rowsBySku = new Map<string, number[]>();
  values.forEach((row, i) => {
    const key = normalise(String(row[cSku]));
    const list = rowsBySku.get(key) || [];
    list.push(i);
    rowsBySku.set(key, list);
  });

  const result: ImportResult = {
    received: prices.length,
    inserted: 0,
    updated: 0,
    unchanged: 0,
    duplicatesInFile: duplicatesInFile,
    duplicateRowsInCatalogue: 0,
    textsEscaped: 0,
    bigChanges: [],
  };
  const newRows: (string | number | boolean)[][] = [];
  let changed = false;

  incoming.forEach((p, key) => {
    const price = round4(p.price);
    const serial = toSerial(p.validFrom);
    const description = safeText(p.description, result);
    const matches = rowsBySku.get(key);
    if (!matches) {
      const row: (string | number | boolean)[] = headers.map(() => "");
      row[cSku] = key;
      row[cDesc] = description;
      row[cPrice] = price;
      row[cValid] = serial;
      row[cSupplier] = safeText(supplier, result);
      row[cSource] = safeText(sourceFile, result);
      newRows.push(row);
      result.inserted++;
      return;
    }
    // "Update a row" in the connector changes only the first match; we update every match and say so.
    result.duplicateRowsInCatalogue += matches.length - 1;
    const first = values[matches[0]];
    const oldPrice = Number(first[cPrice]);
    const priceOrTextChanged = round4(oldPrice) !== price || String(first[cDesc]) !== description;
    const needsWrite = priceOrTextChanged || first[cValid] !== serial || String(first[cSource]) !== sourceFile;
    if (needsWrite) {
      matches.forEach((i) => {
        values[i][cDesc] = description;
        values[i][cPrice] = price;
        values[i][cValid] = serial;
        values[i][cSupplier] = safeText(supplier, result);
        values[i][cSource] = safeText(sourceFile, result);
      });
      changed = true;
    }
    if (!priceOrTextChanged) {
      result.unchanged++; // same price and description; valid from and source are still refreshed
      return;
    }
    result.updated++;
    if (oldPrice > 0 && Math.abs(price - oldPrice) / oldPrice > changeThreshold) {
      result.bigChanges.push({
        sku: key,
        description: description,
        oldPrice: round4(oldPrice),
        newPrice: price,
        changePercent: Math.round(((price - oldPrice) / oldPrice) * 1000) / 10,
      });
    }
  });

  // 4. Two writes, whatever the number of rows.
  if (changed && body) {
    body.setValues(values);
  }
  if (newRows.length > 0) {
    table.addRows(-1, newRows);
  }
  return result;
}

function normalise(sku: string): string {
  return sku.trim().toUpperCase();
}

function round4(n: number): number {
  return Math.round(n * 10000) / 10000;
}

// Excel stores dates as serial numbers: days since 30 Dec 1899 (1 Jan 2000 is 36526).
function toSerial(isoDate: string): number {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate || "");
  if (!m) {
    return NaN;
  }
  const ms = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) - Date.UTC(1899, 11, 30);
  return ms / 86400000;
}

// setValues treats a value that starts with "=", "+" or "-" as a formula. Supplier text is data.
function safeText(text: string, result: ImportResult): string {
  const t = (text || "").trim();
  if (/^[=+\-]/.test(t)) {
    result.textsEscaped++;
    return " " + t;
  }
  return t;
}
