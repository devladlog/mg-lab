import { createReadStream, createWriteStream } from "node:fs";
import { mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { createInterface } from "node:readline";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { parseCsv } from "#src/csv.js";
import { validateRow } from "#src/domain.js";
import { ApiError } from "#src/errors.js";
import { mapLimit } from "#src/pool.js";
import { createPromiseCache } from "#src/promise-cache.js";

/**
 * Lines of a file, one at a time. The readline interface is created and iterated in the same step on purpose:
 * readline starts emitting as soon as it exists, and lines emitted before something iterates are lost
 * (see demo/gotchas.js, number 4).
 */
export async function* readLines(file) {
  const rl = createInterface({ input: createReadStream(file, { encoding: "utf8" }), crlfDelay: Infinity });
  yield* rl;
}

/**
 * Turn lines of CSV into approval packs, as an async generator: parse, validate, look the approvers up
 * (bounded, cached), and yield one output record per input row, in the order they finish.
 * Bad rows and failed lookups become records with status "rejected" or "failed": one bad row never stops the batch.
 */
export async function* buildPacks(lines, { client, concurrency = 4, useCache = true, signal, stats = {} }) {
  const cache = createPromiseCache((department, opts) => client.approversFor(department, opts));
  stats.cache = cache.stats;
  const lookup = (department, opts) => (useCache ? cache.get(department.toLowerCase(), opts) : client.approversFor(department, opts));

  async function* rows() {
    for await (const parsed of parseCsv(lines)) {
      const checked = validateRow(parsed);
      if (checked.ok) yield checked.request;
      else yield { rejected: checked.errors };
    }
  }

  async function enrich(item, { signal: callSignal }) {
    if (item.rejected) return { row: item.rejected[0].row, status: "rejected", errors: item.rejected.map((e) => e.message) };
    const { code, title, department, budgetCents, priority, row } = item;
    try {
      const people = await lookup(department, { signal: callSignal });
      const route = [people.manager, people.finance, ...(priority === "Board" ? [people.board] : [])];
      return { row, status: "ready", code, title, department: people.department, budget: budgetCents / 100, priority, route };
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;   // aborts and programming errors stop the batch
      return { row, status: error.status === 404 ? "rejected" : "failed", code, errors: [`${department}: ${error.message}`] };
    }
  }

  yield* mapLimit(rows(), concurrency, enrich, { signal });
}

/** File in, NDJSON file out, through stream.pipeline: backpressure, cleanup on error, cancel with a signal. */
export async function runIntake({ file, out, client, concurrency, useCache, signal }) {
  const counts = { ready: 0, rejected: 0, failed: 0 };
  const stats = {};
  await mkdir(dirname(out), { recursive: true });
  await pipeline(
    Readable.from(buildPacks(readLines(file), { client, concurrency, useCache, signal, stats })),
    async function* toNdjson(records) {
      for await (const record of records) { counts[record.status]++; yield `${JSON.stringify(record)}\n`; }
    },
    createWriteStream(out),
    { signal },
  );
  return { counts, cache: stats.cache };
}
