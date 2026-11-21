#!/usr/bin/env node
import { parseArgs } from "node:util";
import { ApprovalsClient } from "#src/client.js";
import { createApprovalsApi } from "#src/approvals-api.js";
import { runIntake } from "#src/pipeline.js";

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    api: { type: "string", default: "http://127.0.0.1:5090" },
    out: { type: "string", default: "out/packs.ndjson" },
    concurrency: { type: "string", default: "4" },
    "no-cache": { type: "boolean", default: false },
    "timeout-ms": { type: "string", default: "2000" },
    port: { type: "string", default: "5090" },
    latency: { type: "string", default: "300" },
    "fail-first": { type: "string", default: "" },
  },
});
const [command, file] = positionals;

if (command === "serve") {
  const api = createApprovalsApi({
    latencyMs: Number(values.latency),
    failFirst: values["fail-first"] ? values["fail-first"].split(",") : [],
    log: (line) => console.log(line),
  });
  const url = await api.listen(Number(values.port));
  console.log(`approvals API on ${url} (latency ${values.latency} ms). Ctrl+C to stop.`);
  const shutdown = async (signalName) => {
    console.log(`${signalName}: closing, ${api.stats.calls} calls served, ${api.stats.aborted} aborted by clients`);
    await api.close();
    process.exit(0);
  };
  process.on("SIGINT", () => void shutdown("SIGINT"));
  process.on("SIGTERM", () => void shutdown("SIGTERM"));
} else if (command === "intake" && file) {
  const abort = new AbortController();
  process.once("SIGINT", () => abort.abort(new Error("interrupted (Ctrl+C)")));
  const client = new ApprovalsClient(values.api, { timeoutMs: Number(values["timeout-ms"]) });
  const started = performance.now();
  try {
    const { counts, cache } = await runIntake({
      file, out: values.out, client, concurrency: Number(values.concurrency), useCache: !values["no-cache"], signal: abort.signal,
    });
    const ms = Math.round(performance.now() - started);
    console.log(`${counts.ready} ready, ${counts.rejected} rejected, ${counts.failed} failed -> ${values.out}`);
    console.log(`concurrency ${values.concurrency}, ${values["no-cache"] ? "no cache" : `cache: ${cache.misses} API calls, ${cache.hits} shared`}, ${ms} ms`);
  } catch (error) {
    console.error(`stopped: ${abort.signal.aborted ? abort.signal.reason.message : error.message}`);
    process.exitCode = 130;
  }
} else {
  console.error("usage: cli.js serve [--port 5090 --latency 300 --fail-first operations]\n       cli.js intake <file.csv> [--api URL --out FILE --concurrency 4 --no-cache --timeout-ms 2000]");
  process.exitCode = 2;
}
