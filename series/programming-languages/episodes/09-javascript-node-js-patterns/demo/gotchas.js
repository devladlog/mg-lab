// Three JavaScript habits that look fine and are not. Run: node demo/gotchas.js
import { spawnSync } from "node:child_process";
import { createServer } from "node:net";
import { setTimeout as sleep } from "node:timers/promises";

const save = async (code) => { await sleep(20); return code; };
const codes = ["PR-1", "PR-2", "PR-3"];

// 1. forEach does not wait for async callbacks.
let saved = 0;
codes.forEach(async (code) => { await save(code); saved++; });
console.log(`1. after forEach(async): saved = ${saved}`);
await sleep(60);
console.log(`   a moment later:       saved = ${saved}`);

saved = 0;
await Promise.all(codes.map(async (code) => { await save(code); saved++; }));
console.log(`   Promise.all(map):     saved = ${saved}   <- waited`);

// 2. A promise nobody awaits: its rejection ends the process (default since Node 15).
const child = spawnSync(process.execPath, ["--input-type=module", "-e",
  'const save = async () => { throw new Error("disk full"); }; save(); setTimeout(() => console.log("never printed"), 200);'],
  { encoding: "utf8" });
const firstError = child.stderr.split("\n").find((l) => l.includes("Error:")) ?? "";
console.log(`2. floating promise: child exit code ${child.status}, stderr says "${firstError.trim()}"`);

// 3. fetch hides the reason one level down.
const probe = createServer();
await new Promise((resolve) => probe.listen(0, "127.0.0.1", resolve));
const { port } = probe.address();
await new Promise((resolve) => probe.close(resolve));      // a port that was free a moment ago: nobody listens
try {
  await fetch(`http://127.0.0.1:${port}/`);
} catch (error) {
  console.log(`3. fetch error: "${error.message}", but error.cause.code is "${error.cause?.code}"`);
}

// 4. readline loses lines that were emitted before anybody iterates.
import { createReadStream } from "node:fs";
import { createInterface } from "node:readline";
const sample = new URL("../samples/requests.csv", import.meta.url);
const count = async (rl) => {
  let n = 0;
  const loop = (async () => { for await (const _ of rl) n++; return "finished"; })();
  const how = await Promise.race([loop, sleep(300, "never finishes")]);   // the late loop waits for a 'close' that already happened
  rl.close();
  return how === "finished" ? `${n} lines` : `${n} lines, and the loop never finishes`;
};

const late = createInterface({ input: createReadStream(sample), crlfDelay: Infinity });
await sleep(50);                                   // any await between creating and iterating
const lateCount = await count(late);
const prompt = await count(createInterface({ input: createReadStream(sample), crlfDelay: Infinity }));
console.log(`4. readline: iterate at once = ${prompt}; after an await = ${lateCount}`);
