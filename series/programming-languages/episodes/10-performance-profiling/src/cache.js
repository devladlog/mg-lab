/** A cache that only grows: every distinct key stays in memory for the life of the process. */
export function createUnboundedCache() {
  const map = new Map();
  return {
    get size() { return map.size; },
    getOrCompute(key, compute) {
      if (!map.has(key)) map.set(key, compute(key));
      return map.get(key);
    },
  };
}

/** Least-recently-used cache. A Map iterates in insertion order, so the first key is the oldest use. */
export function createLruCache(max) {
  if (!Number.isInteger(max) || max < 1) throw new RangeError("max must be a whole number of at least 1");
  const map = new Map();
  return {
    get size() { return map.size; },
    getOrCompute(key, compute) {
      if (map.has(key)) {
        const value = map.get(key);
        map.delete(key);
        map.set(key, value);                      // move to the newest position
        return value;
      }
      const value = compute(key);
      map.set(key, value);
      if (map.size > max) map.delete(map.keys().next().value);
      return value;
    },
  };
}

/** Heap in use after a forced collection. Needs `node --expose-gc`. */
export function heapUsedMb() {
  if (typeof globalThis.gc !== "function") throw new Error("run with node --expose-gc");
  globalThis.gc();
  return process.memoryUsage().heapUsed / 1024 / 1024;
}

/** Push `keys` distinct keys through a cache and report how much heap it holds afterwards. */
export function measureCache(cache, keys) {
  const before = heapUsedMb();
  for (let i = 0; i < keys; i++) cache.getOrCompute(`pack:${i}`, (k) => ({ key: k, text: `${k} `.repeat(20) + i }));
  const after = heapUsedMb();
  return { entries: cache.size, growthMb: after - before };
}
