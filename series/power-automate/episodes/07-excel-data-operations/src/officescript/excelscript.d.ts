// The subset of the Office Scripts API (ExcelScript namespace) that UpsertPrices.ts uses,
// with the signatures from the ExcelScript reference on Microsoft Learn. It exists only so
// `npm run typecheck` can compile the script locally with the TypeScript version Office
// Scripts uses (4.0.3). In Excel, the real namespace is provided by the Code Editor.
declare namespace ExcelScript {
  interface Workbook {
    /** Gets a table by name or ID. If the table doesn't exist, then this method returns undefined. */
    getTable(key: string): Table | undefined;
  }
  interface Table {
    getName(): string;
    /** Gets the range object associated with the header row of the table. */
    getHeaderRowRange(): Range;
    /** Gets the range object associated with the data body of the table. */
    getRangeBetweenHeaderAndTotal(): Range;
    /** Gets the number of rows in the table. */
    getRowCount(): number;
    /** Adds one or more rows to the table. -1 or null adds at the end. */
    addRows(index?: number, values?: (boolean | string | number)[][]): void;
  }
  interface Range {
    /** Raw values; a value starting with "+", "-" or "=" is interpreted as a formula. */
    getValues(): (string | number | boolean)[][];
    setValues(values: (string | number | boolean)[][]): void;
    getRowCount(): number;
  }
}
