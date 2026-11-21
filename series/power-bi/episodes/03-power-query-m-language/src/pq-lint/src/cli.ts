#!/usr/bin/env node
// pq-lint <folder of .pq files> [--strict]
// Exit code: 1 when there are errors (or warnings with --strict), 0 otherwise, 2 on bad usage.
import * as fs from "fs";
import * as path from "path";
import { lintFiles } from "./lint";

async function main(): Promise<number> {
    const args = process.argv.slice(2);
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
