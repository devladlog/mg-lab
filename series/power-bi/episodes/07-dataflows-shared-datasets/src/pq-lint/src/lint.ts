// pq-lint: rules for Power Query M, on top of Microsoft's open-source parser (@microsoft/powerquery-parser).
// It parses; it does not evaluate. Every rule is a static check on the syntax tree.
import { DefaultSettings, TaskUtils } from "@microsoft/powerquery-parser";

export type Severity = "error" | "warning";

export interface Finding {
    rule: string;
    severity: Severity;
    query: string;
    line: number; // 1-based
    message: string;
}

export const RULES: Record<string, { severity: Severity; title: string }> = {
    PQ001: { severity: "error", title: "syntax error" },
    PQ002: { severity: "error", title: "unresolved name (not a step, parameter, function argument or query)" },
    PQ003: { severity: "warning", title: "hard-coded path in a data source function: use a parameter" },
    PQ004: { severity: "warning", title: "Table.Distinct on a sorted table without Table.Buffer" },
    PQ005: { severity: "warning", title: "Table.TransformColumnTypes without a culture" },
    PQ006: { severity: "warning", title: "Folder.Files without a filter on [Extension]" },
    PQ007: { severity: "warning", title: "generated step name: say what the step does" },
    PQ008: { severity: "warning", title: "unquoted '/' or ':' in a date format with a culture" },
};

// Step names the Power Query editor generates (optionally followed by a number).
const GENERATED_STEP = new RegExp(
    "^(Changed Type|Promoted Headers|Filtered Rows|Filtered Hidden Files|Removed Columns|Removed Other Columns|" +
        "Renamed Columns|Merged Queries|Appended Query|Expanded .+|Removed Duplicates|Sorted Rows|Added Index|" +
        "Added Custom|Added Conditional Column|Replaced Value|Grouped Rows|Invoke Custom Function|Removed Top Rows|" +
        "Removed Blank Rows|Trimmed Text|Uppercased Text|Reordered Columns|Kept First Rows)\\d*$",
);
const DATA_SOURCE_FUNCTIONS = new Set(["File.Contents", "Folder.Files", "Folder.Contents"]);
const FROM_TEXT = new Set(["Date.FromText", "DateTime.FromText", "DateTimeZone.FromText", "Time.FromText"]);
const SKIP_KEYS = new Set(["tokenRange", "id", "attributeIndex", "maybeAttributeIndex"]);

type Node = any; // the parser's Ast.TNode union; we only read kind/literal/children

/** `#"Changed Type"` -> `Changed Type`; plain identifiers unchanged. */
export function unquote(identifier: string): string {
    return identifier.startsWith('#"') ? identifier.slice(2, -1).replace(/""/g, '"') : identifier;
}

function textValue(node: Node): string | undefined {
    if (node?.kind === "LiteralExpression" && node.literalKind === "Text") {
        return String(node.literal).slice(1, -1).replace(/""/g, '"');
    }
    return undefined;
}

function line(node: Node): number {
    return (node?.tokenRange?.positionStart?.lineNumber ?? 0) + 1;
}

/** `Table.Sort(x, ...)` -> { fn: "Table.Sort", args: [x, ...] } */
function asCall(node: Node): { fn: string; args: Node[] } | undefined {
    if (node?.kind !== "RecursivePrimaryExpression" || node.head?.kind !== "IdentifierExpression") return undefined;
    const first = node.recursiveExpressions?.elements?.[0];
    if (first?.kind !== "InvokeExpression" || node.recursiveExpressions.elements.length !== 1) return undefined;
    return { fn: node.head.identifier.literal, args: first.content.elements.map((c: Node) => c.node) };
}

function children(node: Node): Node[] {
    const out: Node[] = [];
    for (const [k, v] of Object.entries(node)) {
        if (SKIP_KEYS.has(k) || v === null || typeof v !== "object") continue;
        if (Array.isArray(v)) v.forEach((x) => x && typeof x === "object" && out.push(x));
        else out.push(v);
    }
    return out;
}

function recordFields(node: Node): Map<string, Node> {
    const fields = new Map<string, Node>();
    if (node?.kind !== "RecordExpression") return fields;
    for (const csv of node.content.elements) fields.set(unquote(csv.node.key.literal), csv.node.value);
    return fields;
}

/** True when a .NET-style date format has a '/' or ':' that isn't quoted or escaped. */
export function hasUnquotedSeparator(format: string): boolean {
    let quote: string | undefined;
    for (let i = 0; i < format.length; i++) {
        const c = format[i];
        if (quote) {
            if (c === quote) quote = undefined;
        } else if (c === "\\") {
            i++;
        } else if (c === "'" || c === '"') {
            quote = c;
        } else if (c === "/" || c === ":") {
            return true;
        }
    }
    return false;
}

export async function lintQuery(query: string, text: string, knownQueries: Set<string>): Promise<Finding[]> {
    const findings: Finding[] = [];
    const add = (rule: string, node: Node | number, message: string) =>
        findings.push({ rule, severity: RULES[rule].severity, query, line: typeof node === "number" ? node : line(node), message });

    const task: any = await TaskUtils.tryLexParse(DefaultSettings, text);
    if (task.resultKind !== "Ok") {
        const pos = task.error?.innerError?.foundToken?.token?.positionStart ?? task.error?.innerError?.positionStart;
        add("PQ001", (pos?.lineNumber ?? 0) + 1, String(task.error?.message ?? "could not parse"));
        return findings;
    }

    const steps = new Map<string, Node>(); // let step name -> value expression (for PQ004)
    let usesFolderFiles: Node | undefined;
    let filtersExtension = false;

    const visit = (node: Node, scopes: Set<string>[]): void => {
        switch (node.kind) {
            case "LetExpression": {
                const names = new Set<string>();
                for (const csv of node.variableList.elements) {
                    const key = unquote(csv.node.key.literal);
                    names.add(key);
                    steps.set(key, csv.node.value);
                    if (GENERATED_STEP.test(key)) add("PQ007", csv.node.key, `step #"${key}": rename it after what it does`);
                }
                const inner = [...scopes, names];
                for (const csv of node.variableList.elements) visit(csv.node.value, inner);
                visit(node.expression, inner);
                return;
            }
            case "FunctionExpression": {
                const names = new Set<string>(
                    node.parameters.content.elements.map((csv: Node) => unquote(csv.node.name.literal)),
                );
                visit(node.expression, [...scopes, names]);
                return;
            }
            case "EachExpression":
                visit(node.paired, [...scopes, new Set(["_"])]);
                return;
            case "RecordExpression": {
                const inner = [...scopes, new Set(recordFields(node).keys())];
                for (const csv of node.content.elements) visit(csv.node.value, inner);
                return;
            }
            case "IdentifierExpression": {
                const literal: string = node.identifier.literal;
                // #date, #duration, #table... reach us as identifiers: they're hash keywords, not names.
                if (literal.startsWith("#") && !literal.startsWith('#"')) return;
                const name = unquote(literal);
                const local = scopes.some((s) => s.has(name));
                // The standard library is all dotted names (Table.Sort, Int64.Type...); anything else must resolve.
                if (!local && !name.includes(".") && !knownQueries.has(name)) {
                    add("PQ002", node, `"${name}" is not a step, a function argument or a query in this folder`);
                }
                return;
            }
            case "FieldSelector":
                if (node.content?.literal === "Extension") filtersExtension = true;
                return;
        }

        const call = asCall(node);
        if (call) checkCall(call, node);
        for (const child of children(node)) visit(child, scopes);
    };

    const checkCall = (call: { fn: string; args: Node[] }, node: Node) => {
        if (DATA_SOURCE_FUNCTIONS.has(call.fn)) {
            const path = textValue(call.args[0]);
            if (path !== undefined && /^([A-Za-z]:\\|\\\\|\/)/.test(path)) {
                add("PQ003", node, `${call.fn}("${path}"): move the path into a parameter`);
            }
            if (call.fn === "Folder.Files") usesFolderFiles = node;
        }
        if (call.fn === "Table.Distinct") {
            const input = call.args[0];
            const source =
                input?.kind === "IdentifierExpression" ? steps.get(unquote(input.identifier.literal)) : input;
            if (asCall(source)?.fn === "Table.Sort") {
                add("PQ004", node, "Table.Distinct keeps an unspecified duplicate; buffer the sorted table first (Table.Buffer)");
            }
        }
        if (call.fn === "Table.TransformColumnTypes" && call.args.length < 3) {
            add("PQ005", node, 'pass the culture of the source text, e.g. Table.TransformColumnTypes(t, {...}, "en-US")');
        }
        if (FROM_TEXT.has(call.fn)) {
            const options = recordFields(call.args[1]);
            const format = textValue(options.get("Format"));
            if (format !== undefined && options.has("Culture") && hasUnquotedSeparator(format)) {
                add("PQ008", node, `Format "${format}": "/" and ":" are the culture's separators; quote them ('/')`);
            }
        }
    };

    visit(task.ast, []);
    if (usesFolderFiles && !filtersExtension) {
        add("PQ006", usesFolderFiles, "filter the file list on [Extension] so a stray file can't break the combine");
    }
    return findings.sort((a, b) => a.line - b.line || a.rule.localeCompare(b.rule));
}

/** Lints every .pq file of a folder; each file name (without .pq) is a query the others can reference. */
export async function lintFiles(files: Map<string, string>): Promise<Finding[]> {
    const known = new Set(files.keys());
    const all: Finding[] = [];
    for (const [name, text] of [...files].sort(([a], [b]) => a.localeCompare(b))) {
        all.push(...(await lintQuery(name, text, known)));
    }
    return all;
}
