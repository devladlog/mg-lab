# DEVLADLOG Code #9 - JavaScript and Node.js patterns that survive production

Series: `programming-languages` (DEVLADLOG Code). Blog: <https://www.devladlog.com/articles/programming-languages/2025-06-14-javascriptnodejs-patterns-complete-guide-2025/>

The Contoso project requests from the earlier episodes (same rules family: 50,000 EUR or more is High, 250,000 or more
goes to the board) arrive as a CSV. Each valid request needs its approvers from a small HTTP service, and one approval
pack per request is written as NDJSON. The project is plain ES modules on **Node 22, zero npm dependencies**
(`node:test`, `fetch`, `node:stream`, `node:readline`, `node:util`).

- **Streams and async generators** end to end: `readline` -> CSV parser -> validation -> lookups -> NDJSON file, joined
  by `stream/promises` `pipeline` (backpressure, cleanup, abort signal). Nothing reads the whole file.
- **A concurrency limit written by hand** (`mapLimit`): lazy reads from the source, results in completion order,
  fail-fast, and the first error aborts the signal handed to the calls still running.
- **Cache the promise, not the value**: concurrent callers share one call, failures are dropped so the next caller retries.
- **Deadline + cancellation on every call**: `AbortSignal.timeout()` combined with the caller's signal through
  `AbortSignal.any()`. A caller cancel is never retried; timeouts and 429/502/503/504 are, with exponential backoff and jitter.
- **Errors with context**: `RowError` (row number + field) and `ApiError` (status, retryable, original error as `cause`).
- **Ctrl+C that reaches the server**: `SIGINT` aborts the run, exit code 130, and the API logs `ABORTED by the client`.
- **Tests with `node:test` against a real HTTP server** (the approvals API in this folder, started on a free port).
- **Subpath imports** (`"imports": {"#src/*": "./src/*"}`) so modules import `#src/client.js`, not `../../src/client.js`.

| Path | What it is |
|---|---|
| [`package.json`](package.json) | `"type": "module"`, `engines` Node >= 22, `imports` map, scripts (`test`, `check`, `api`, `intake`, `gotchas`) |
| [`src/csv.js`](src/csv.js) | `splitLine` (quotes, doubled quotes) and the lazy `parseCsv` generator |
| [`src/domain.js`](src/domain.js) | `validateRow`: every problem in a row, `"75,000"` accepted, real-date check, priority rules (integer cents) |
| [`src/errors.js`](src/errors.js) | `RowError`, `ApiError` |
| [`src/approvals-api.js`](src/approvals-api.js) | The approvals directory as a real `node:http` service: latency, `failFirst`, call/in-flight/aborted counters, graceful `close()` |
| [`src/client.js`](src/client.js) | `ApprovalsClient`: `fetch`, deadline, caller signal, retry with backoff + jitter, real error causes |
| [`src/promise-cache.js`](src/promise-cache.js) | `createPromiseCache` |
| [`src/pool.js`](src/pool.js) | `mapLimit` |
| [`src/pipeline.js`](src/pipeline.js) | `readLines`, `buildPacks` (async generator), `runIntake` (`stream/promises` `pipeline`) |
| [`src/cli.js`](src/cli.js) | `serve` and `intake` commands, `util.parseArgs`, `SIGINT` handling |
| [`samples/`](samples) | `requests.csv` (14 fictional rows: 9 good, 5 bad), `approvers.json` |
| [`tests/`](tests) | 26 tests in 5 files |
| [`demo/gotchas.js`](demo/gotchas.js) | Four traps, runnable: `forEach(async)`, a floating promise, `fetch failed`, readline losing lines |
| [`demo/expected-output.txt`](demo/expected-output.txt) | Real captured output: tests, gotchas, the three timings, Ctrl+C |

## Build, test, run

```bash
node --version                     # 22 or later (built and tested on v22.23.5, Linux)
npm test                           # node --test "tests/**/*.test.js"  ->  tests 26, pass 26, fail 0 (about 2 s)
npm run check                      # node --check on the CLI and the demo
npm run -s gotchas                 # the four traps

# terminal 1: the approvals API (first call for Operations fails on purpose, to show the retry)
node src/cli.js serve --port 5090 --latency 300 --fail-first operations
# terminal 2
node src/cli.js intake samples/requests.csv --concurrency 1 --no-cache   # 3641 ms here
node src/cli.js intake samples/requests.csv --concurrency 5 --no-cache   #  711 ms
node src/cli.js intake samples/requests.csv --concurrency 5              #  691 ms, 5 API calls, 5 shared
```
There is nothing to `npm install`. The numbers above are from one run on a shared container: they show the shape
(about 5x from the limit, 10 calls down to 5 from the cache), not a benchmark. The tests do not depend on timing.

Passed 26/26 in 15 consecutive runs of the final version (after the test fixes described below). Not run on Windows (the recording laptop):
`SIGINT` on Windows and the `node --test` glob are documented to work, but check once before recording.

## What we learned / gotchas
- **`readline` loses lines that are emitted before something iterates it.** I created the interface, awaited `mkdir`, then
  iterated: 0 lines, and the `for await` loop never finished. This showed up as tests that failed every few runs (the output
  was an empty file) and cost an afternoon. Fix: create and iterate in the same step (`readLines()` is a generator that does
  `yield* rl`). `demo/gotchas.js` number 4 reproduces it and a test pins it.
- **`fetch` refuses some ports** (`TypeError: fetch failed`, cause `Error: bad port`), following the Fetch standard's blocked-port
  list; I hit it using port 9 for a "closed port" test. Use a port you just freed instead (the tests ask the OS for one).
- **`fetch failed` says nothing; the reason is in `error.cause`** (`ECONNREFUSED`, ...). `ApprovalsClient` copies it into its message.
- **`server.close()` waited about 4 seconds after a client aborted a request**, even after `closeIdleConnections()`. The API's
  `close()` now closes what is left after 200 ms with `closeAllConnections()` (graceful first, then firm). Cause not investigated further.
- **`forEach(async ...)` does not wait**, and a floating promise that rejects ends the process (exit code 1) with the default
  unhandled-rejections mode. Both are in `demo/gotchas.js` and in the tests.
- **Timing-based tests are flaky on a shared machine.** First versions slept 50 ms and then asserted; they failed under load.
  The tests now wait for the fact (`eventually(() => api.stats.inFlight === 4)`) and only then abort.
- A caller abort and a timeout look the same to `fetch` (both reject). `AbortSignal.timeout()` rejects with a `TimeoutError`
  `DOMException`; check which signal is `aborted` to tell them apart (see `client.js`).
- Not verified here: Windows behaviour (see above) and anything in Azure. The episode has no cloud part. If the code is deployed
  to Azure, Learn says to use an LTS version of Node.js and align local, CI and host versions.

## References
- [Choose the right Node.js version for Azure (use LTS, align environments)](https://learn.microsoft.com/azure/developer/javascript/choose-nodejs-version)
- [Azure Functions runtime versions: Node.js 22 and 24 GA, Node.js 22 end of support April 30, 2027](https://learn.microsoft.com/azure/azure-functions/functions-versions#languages)
- [Azure Abort Controller library: use the platform `AbortController`/`AbortSignal`, e.g. `AbortSignal.timeout()`, with Azure SDK operations](https://learn.microsoft.com/javascript/api/overview/azure/abort-controller-readme?view=azure-node-latest)
- [Implement a retry policy with JavaScript or TypeScript (Azure Storage: exponential policy, tries, timeouts)](https://learn.microsoft.com/azure/storage/blobs/storage-retry-policy-javascript)
- [Configure a Node.js app for Azure App Service (set the Node version in package.json)](https://learn.microsoft.com/azure/app-service/configure-language-nodejs)
- Node.js API docs (behaviour here was verified by running it): `stream/promises` `pipeline`, `AbortSignal.any`, `node:test`, `readline`
- Blog: [JavaScript/Node.js Patterns - Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-06-14-javascriptnodejs-patterns-complete-guide-2025/)
