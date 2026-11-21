import { monitorEventLoopDelay } from "node:perf_hooks";
import { setTimeout as sleep } from "node:timers/promises";

/**
 * How long was the event loop unable to run timers while `work` ran? Uses perf_hooks.monitorEventLoopDelay,
 * which samples a timer every `resolutionMs` and records how late it fired (nanoseconds, reported here in ms).
 * A synchronous 400 ms loop inside `work` shows up as one sample of about 400 ms.
 * @param {() => unknown | Promise<unknown>} work
 */
export async function measureLoopLag(work, { resolutionMs = 10 } = {}) {
  const histogram = monitorEventLoopDelay({ resolution: resolutionMs });
  histogram.enable();
  await sleep(resolutionMs * 5);                 // a quiet baseline first
  const started = performance.now();
  const result = await work();
  const workMs = performance.now() - started;
  await sleep(resolutionMs * 5);                 // the late timer fires only after the work returned: let it record
  histogram.disable();
  return {
    result,
    workMs,
    maxMs: histogram.max / 1e6,
    p99Ms: histogram.percentile(99) / 1e6,
    meanMs: histogram.mean / 1e6,
    resolutionMs,
  };
}
