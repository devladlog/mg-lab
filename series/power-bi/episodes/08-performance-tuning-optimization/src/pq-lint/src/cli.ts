#!/usr/bin/env node
// pq-lint <folder of .pq files> [--strict]
// pq-lint --section <mashup.pq>      parse a whole section document (the Dataflow Gen2 mashup.pq) and report syntax errors
// Exit code: 1 when there are errors (or warnings with --strict), 0 otherwise, 2 on bad usage.
import * as fs from "fs";
import * as path from "path";
import { DefaultSettings, TaskUtils } from "@microsoft/powerquery-parser";
import { lintFiles } from "./lint";

async function checkSection(file: string): Promise<number> {
    const text = fs.readFileSync(file, "utf8");
    const task: any = await TaskUtils.tryLexParse(DefaultSettings, text);
    if (task.resultKind !== "Ok") {
        const pos = task.error?.innerError?.foundToken?.token?.positionStart ?? task.error?.innerError?.positionStart;
        console.log(`  ERROR    PQ001  ${path.basename(file)}:${(pos?.lineNumber ?? 0) + 1}  ${String(task.error?.message ?? "could not parse")}`);
        return 1;
    }
    const members = text.split("\n").filter((l) => l.startsWith("shared ")).length;
    console.log(`  PASS     ${path.basename(file)} parses as a section document (${members} shared members)`);
    return 0;
}

async function main(): Promise<number> {
    const args = process.argv.slice(2);
    if (args[0] === "--section") return args[1] ? checkSection(args[1]) : 2;
    const strict = args.includes("--strict");
    const folder = args.find((a) => !a.startsWith("--"));
    if (!folder || !fs.existsSync(folder) || !fs.statSync(folder).isDirectory()) {
        console.error("usage: pq-lint <folder of .pq files> [--strict]");
        return 2;
    }
    const files = new Map<string, string>();
    for (const f of fs.readdirSync(folder).filter((f) => f.endsWith(".pq")).sort()) {
        files.set(path.basename(f, ".pq"), fs.readFileSync(path.join(folder, f), "utf8"));
    }
    const findings = await lintFiles(files);
    for (const name of files.keys()) {
        const mine = findings.filter((f) => f.query === name);
        if (mine.length === 0) console.log(`  PASS     ${name}.pq`);
        for (const f of mine) {
            console.log(`  ${f.severity.toUpperCase().padEnd(7)}  ${f.rule}  ${name}.pq:${f.line}  ${f.message}`);
        }
    }
    const errors = findings.filter((f) => f.severity === "error").length;
    const warnings = findings.length - errors;
    console.log(`${files.size} queries: ${errors} error(s), ${warnings} warning(s)`);
    return errors > 0 || (strict && warnings > 0) ? 1 : 0;
}

main().then((code) => process.exit(code));
