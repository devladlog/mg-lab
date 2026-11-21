import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";

const DIRECTORY = JSON.parse(readFileSync(new URL("../samples/approvers.json", import.meta.url), "utf8"));
const BY_DEPARTMENT = new Map(Object.entries(DIRECTORY.departments).map(([name, people]) => [name.toLowerCase(), { department: name, ...people, board: DIRECTORY.board }]));

/**
 * The Contoso approvals directory as a small real HTTP service: GET /approvers/:department.
 * It counts calls, the highest number of calls in flight at once, and calls the client gave up on.
 * @param {{ latencyMs?: number, failFirst?: string[], log?: (line: string) => void }} [options]
 */
export function createApprovalsApi({ latencyMs = 100, failFirst = [], log = () => {} } = {}) {
  const stats = { calls: 0, inFlight: 0, maxInFlight: 0, aborted: 0, byDepartment: {} };
  const failOnce = new Set(failFirst.map((d) => d.toLowerCase()));

  const server = createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    const match = /^\/approvers\/([^/]+)$/.exec(url.pathname);
    const send = (status, body) => {
      res.writeHead(status, { "content-type": "application/json" });
      res.end(JSON.stringify(body));
    };
    if (req.method !== "GET" || !match) return send(404, { error: "not found" });

    const key = decodeURIComponent(match[1]).toLowerCase();
    stats.calls++;
    stats.byDepartment[key] = (stats.byDepartment[key] ?? 0) + 1;
    stats.maxInFlight = Math.max(stats.maxInFlight, ++stats.inFlight);

    // Stop waiting when the client goes away before we answered: that is how a cancelled fetch shows up here.
    const gone = new AbortController();
    res.on("close", () => { if (!res.writableEnded) gone.abort(); });
    try {
      await sleep(latencyMs, undefined, { signal: gone.signal });
    } catch {
      stats.aborted++;
      log(`${key}: ABORTED by the client`);
      res.destroy();                 // nobody is listening: free the socket so close() does not wait for it
      return;
    } finally {
      stats.inFlight--;
    }

    if (failOnce.delete(key)) { log(`${key}: 503 (first call fails on purpose)`); return send(503, { error: "try again" }); }
    const entry = BY_DEPARTMENT.get(key);
    if (!entry) { log(`${key}: 404`); return send(404, { error: `unknown department ${key}` }); }
    log(`${key}: 200 after ${latencyMs} ms`);
    send(200, entry);
  });

  return {
    stats,
    /** Start on a free port (or the one given) and return the base URL. */
    listen(port = 0, host = "127.0.0.1") {
      return new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(port, host, () => resolve(`http://${host}:${server.address().port}`));
      });
    },
    /**
     * Graceful, then firm: stop accepting, let running requests finish, drop idle keep-alive sockets, and
     * after `graceMs` close whatever is left. Without the last step close() waited about 4 s after a client abort.
     */
    close({ graceMs = 200 } = {}) {
      return new Promise((resolve, reject) => {
        const force = setTimeout(() => server.closeAllConnections(), graceMs);
        server.close((err) => { clearTimeout(force); if (err) reject(err); else resolve(); });
        server.closeIdleConnections();
      });
    },
  };
}
