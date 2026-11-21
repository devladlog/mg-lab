/** Split one CSV line. Handles quoted fields, commas inside quotes and doubled quotes. No multi-line fields. */
export function splitLine(line) {
  const fields = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { fields.push(field); field = ""; }
    else field += c;
  }
  fields.push(field);
  return fields;
}

/**
 * Turn an async (or sync) iterable of lines into records, lazily: one line in memory at a time.
 * Yields { row, record } where `row` is the 1-based line number in the file (the header is row 1).
 */
export async function* parseCsv(lines) {
  let header;
  let row = 0;
  for await (const line of lines) {
    row++;
    if (line.trim() === "") continue;
    const fields = splitLine(line);
    if (!header) { header = fields.map((h) => h.trim()); continue; }
    yield { row, record: Object.fromEntries(header.map((h, i) => [h, (fields[i] ?? "").trim()])) };
  }
}
