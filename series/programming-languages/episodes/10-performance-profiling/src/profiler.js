import { Session } from "node:inspector/promises";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

/**
 * Run `fn` under the V8 sampling CPU profiler (the same profiler behind `node --cpu-prof`) and write a
 * `.cpuprofile` file that VS Code, Chrome DevTools and Edge DevTools can open.
 * @param {() => unknown | Promise<unknown>} fn
 * @param {string} file
 * @param {{ intervalUs?: number }} [options] sampling interval in microseconds (1000; `node --cpu-prof-interval` sets the same thing)
 * @returns {Promise<{ result: unknown, profile: object }>}
 */
export async function profileToFile(fn, file, { intervalUs = 1000 } = {}) {
  const session = new Session();
  session.connect();
  try {
    await session.post("Profiler.enable");
    await session.post("Profiler.setSamplingInterval", { interval: intervalUs });
    await session.post("Profiler.start");
    let result;
    try {
      result = await fn();
    } finally {
      // stop even when fn throws, so the profiler is never left running
      var { profile } = await session.post("Profiler.stop");
    }
    await mkdir(dirname(file), { recursive: true });
    await writeFile(file, JSON.stringify(profile));
    return { result, profile };
  } finally {
    session.disconnect();
  }
}
