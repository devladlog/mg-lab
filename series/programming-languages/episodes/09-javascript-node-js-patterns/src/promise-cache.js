/**
 * Cache the promise, not the value. Concurrent callers for the same key share one in-flight call,
 * and a failed call is removed so the next caller tries again instead of getting a cached failure.
 */
export function createPromiseCache(load) {
  const entries = new Map();
  const stats = { hits: 0, misses: 0 };
  return {
    stats,
    get(key, ...rest) {
      const existing = entries.get(key);
      if (existing) { stats.hits++; return existing; }
      stats.misses++;
      const pending = load(key, ...rest);
      entries.set(key, pending);
      pending.catch(() => { if (entries.get(key) === pending) entries.delete(key); });
      return pending;
    },
  };
}
