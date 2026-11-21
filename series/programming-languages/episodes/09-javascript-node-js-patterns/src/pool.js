/**
 * Run `fn` over a (sync or async) iterable with at most `limit` calls in flight.
 * The source is read lazily, so a big file is never loaded whole. Results are yielded as they finish.
 * The first error stops the pool and aborts the signal that was given to the calls still running.
 * @template T, R
 * @param {AsyncIterable<T> | Iterable<T>} source
 * @param {number} limit
 * @param {(item: T, ctx: { index: number, signal: AbortSignal }) => Promise<R>} fn
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {AsyncGenerator<R>}
 */
export async function* mapLimit(source, limit, fn, { signal } = {}) {
  if (!Number.isInteger(limit) || limit < 1) throw new RangeError("limit must be a whole number of at least 1");
  const stop = new AbortController();
  const callSignal = signal ? AbortSignal.any([signal, stop.signal]) : stop.signal;
  const iterator = source[Symbol.asyncIterator]?.() ?? source[Symbol.iterator]();
  const running = new Map();
  let index = 0;
  let exhausted = false;
  try {
    while (true) {
      while (!exhausted && running.size < limit) {
        signal?.throwIfAborted();
        const next = await iterator.next();
        if (next.done) { exhausted = true; break; }
        const id = index++;
        // Wrap every call so a rejection is delivered through the race below, never as an unhandled rejection.
        running.set(id, Promise.resolve()
          .then(() => fn(next.value, { index: id, signal: callSignal }))
          .then((value) => ({ id, value }), (error) => ({ id, error, failed: true })));
      }
      if (running.size === 0) return;
      const settled = await Promise.race(running.values());
      running.delete(settled.id);
      if (settled.failed) throw settled.error;
      yield settled.value;
    }
  } finally {
    stop.abort();                    // cancel whatever is still in flight
    await iterator.return?.();
  }
}
