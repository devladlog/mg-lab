// Why one timing proves nothing. Run: node demo/one-run-benchmark.js
import { generateRequests } from "#src/data.js";
import { buildReportFast } from "#src/report.js";
import { stats } from "#src/bench.js";

const requests = generateRequests(3000);
const times = [];
for (let i = 1; i <= 12; i++) {
  const start = performance.now();
  buildReportFast(requests);
  times.push(performance.now() - start);
  console.log(`run ${String(i).padStart(2)}: ${times.at(-1).toFixed(2).padStart(7)} ms`);
}
const s = stats(times);
console.log(`first run ${times[0].toFixed(2)} ms, median ${s.medianMs.toFixed(2)} ms, min ${s.minMs.toFixed(2)} ms`);
console.log(`first run is ${(times[0] / s.medianMs).toFixed(1)}x the median: the first number you see is not the speed of the code`);
