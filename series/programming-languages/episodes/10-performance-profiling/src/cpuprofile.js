import { readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

/**
 * Self and total time per function from a `.cpuprofile` (the format written by `node --cpu-prof`
 * and by the inspector). `samples[i]` is the node that was running at sample i and `timeDeltas[i]` is the
 * time since the previous sample, in microseconds, so a sample is charged with the delta that follows it.
 * @param {{ nodes: any[], samples: number[], timeDeltas: number[] }} profile
 * @returns {{ rows: object[], totalMs: number }} rows sorted by self time, descending
 */
export function summarize(profile) {
  const { nodes, samples, timeDeltas } = profile;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const parent = new Map();
  for (const node of nodes) for (const child of node.children ?? []) parent.set(child, node.id);

  const selfUs = new Map();
  for (let i = 0; i < samples.length; i++) {
    const us = timeDeltas[i + 1] ?? timeDeltas[i] ?? 0;
    selfUs.set(samples[i], (selfUs.get(samples[i]) ?? 0) + us);
  }

  const keyOf = (node) => {
    const f = node.callFrame;
    return `${f.functionName || "(anonymous)"}\u0000${f.url}\u0000${f.lineNumber + 1}`;
  };
  const rows = new Map();
  const rowFor = (node) => {
    const key = keyOf(node);
    let row = rows.get(key);
    if (!row) {
      const f = node.callFrame;
      row = { name: f.functionName || "(anonymous)", url: f.url, line: f.lineNumber + 1, selfMs: 0, totalMs: 0 };
      rows.set(key, row);
    }
    return row;
  };

  let totalUs = 0;
  for (const [id, us] of selfUs) {
    totalUs += us;
    rowFor(byId.get(id)).selfMs += us / 1000;
    // total time: charge every distinct function on the stack once
    const seen = new Set();
    for (let at = id; at !== undefined; at = parent.get(at)) {
      const node = byId.get(at);
      const key = keyOf(node);
      if (seen.has(key)) continue;
      seen.add(key);
      rowFor(node).totalMs += us / 1000;
    }
  }
  return { rows: [...rows.values()].sort((a, b) => b.selfMs - a.selfMs), totalMs: totalUs / 1000 };
}

export async function loadProfile(file) {
  return JSON.parse(await readFile(file, "utf8"));
}

/** Short location for printing: file name and line, or nothing for V8 pseudo-frames like (garbage collector). */
export function where(row) {
  if (!row.url) return "";
  const name = row.url.split(/[\\/]/).pop();
  return `${name}:${row.line}`;
}

/** Plain-text table of the top rows by self time. */
export function formatTop(summary, count = 8) {
  const lines = [`total sampled time: ${summary.totalMs.toFixed(0)} ms`, `${"self ms".padStart(9)} ${"self %".padStart(7)} ${"total ms".padStart(9)}  function`];
  for (const row of summary.rows.slice(0, count)) {
    const pct = summary.totalMs > 0 ? (100 * row.selfMs) / summary.totalMs : 0;
    lines.push(`${row.selfMs.toFixed(1).padStart(9)} ${pct.toFixed(1).padStart(6)}% ${row.totalMs.toFixed(1).padStart(9)}  ${row.name}  ${where(row)}`.trimEnd());
  }
  return lines.join("\n");
}

/**
 * Hottest source lines. V8 records `positionTicks` (line, ticks) on every node: how many samples landed on which line
 * of that function. The time of a node is shared between its lines in proportion to the ticks. This is the view that
 * names the guilty line when a builtin such as Array.prototype.some or toLocaleString is inlined into its caller.
 * @returns {{ url: string, line: number, selfMs: number }[]} sorted by self time, descending
 */
export function hotLines(profile) {
  const { nodes, samples, timeDeltas } = profile;
  const nodeUs = new Map();
  for (let i = 0; i < samples.length; i++) nodeUs.set(samples[i], (nodeUs.get(samples[i]) ?? 0) + (timeDeltas[i + 1] ?? timeDeltas[i] ?? 0));
  const lines = new Map();
  for (const node of nodes) {
    const ticks = node.positionTicks ?? [];
    const sum = ticks.reduce((a, t) => a + t.ticks, 0);
    if (sum === 0) continue;
    const ms = (nodeUs.get(node.id) ?? 0) / 1000;
    for (const t of ticks) {
      const key = `${node.callFrame.url}\u0000${t.line}`;
      const row = lines.get(key) ?? { url: node.callFrame.url, line: t.line, selfMs: 0 };
      row.selfMs += (ms * t.ticks) / sum;
      lines.set(key, row);
    }
  }
  return [...lines.values()].sort((a, b) => b.selfMs - a.selfMs);
}

const sourceCache = new Map();
function sourceLine(url, line) {
  try {
    const path = url.startsWith("file:") ? fileURLToPath(url) : url;
    if (!sourceCache.has(path)) sourceCache.set(path, readFileSync(path, "utf8").split(/\r?\n/));
    return (sourceCache.get(path)[line - 1] ?? "").trim();
  } catch {
    return "";
  }
}

/** Plain-text table of the hottest lines with the source text, so the slide shows the code and not just a number. */
export function formatHotLines(rows, totalMs, count = 5) {
  const out = [`${"self ms".padStart(9)} ${"self %".padStart(7)}  line`];
  for (const row of rows.slice(0, count)) {
    const pct = totalMs > 0 ? (100 * row.selfMs) / totalMs : 0;
    out.push(`${row.selfMs.toFixed(1).padStart(9)} ${pct.toFixed(1).padStart(6)}%  ${where(row)}  ${sourceLine(row.url, row.line)}`);
  }
  return out.join("\n");
}
