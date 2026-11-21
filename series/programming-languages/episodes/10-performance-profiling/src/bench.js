/** Median, minimum and 95th percentile of a list of timings (ms). */
export function stats(times) {
  const sorted = [...times].sort((a, b) => a - b);
  const at = (q) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))];
  const median = sorted.length % 2 ? sorted[(sorted.length - 1) / 2] : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
  return { runs: sorted.length, minMs: sorted[0], medianMs: median, p95Ms: at(0.95), maxMs: sorted.at(-1) };
}

let sink;   // every result is stored here, so the engine cannot throw the work away as dead code

/**
 * Time `fn` the careful way: warm-up runs first (the JIT needs them), then `runs` timed runs, and report the
 * median and the spread, never a single run.
 * @param {() => unknown} fn
 * @param {{ warmup?: number, runs?: number }} [options]
 */
export function bench(fn, { warmup = 3, runs = 11 } = {}) {
  for (let i = 0; i < warmup; i++) sink = fn();
  const times = [];
  for (let i = 0; i < runs; i++) {
    const start = performance.now();
    sink = fn();
    times.push(performance.now() - start);
  }
  return stats(times);
}

export const lastResult = () => sink;
