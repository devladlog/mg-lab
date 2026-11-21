import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { intake } from "../src/intake.js";

const sample: unknown = JSON.parse(readFileSync(new URL("../samples/requests.json", import.meta.url), "utf8"));

describe("intake of samples/requests.json", () => {
  it("accepts 3, rejects 2, numbers only the accepted ones", () => {
    if (!Array.isArray(sample)) throw new Error("sample must be an array");
    const lines = intake(sample, 2026);
    expect(lines.map((l) => l.kind)).toEqual(["accepted", "accepted", "rejected", "accepted", "rejected"]);

    const ids = lines.flatMap((l) => (l.kind === "accepted" ? [l.request.id] : []));
    expect(ids).toEqual(["PR-2026-0001", "PR-2026-0002", "PR-2026-0003"]);

    const priorities = lines.flatMap((l) => (l.kind === "accepted" ? [l.request.priority] : []));
    expect(priorities).toEqual(["High", "Standard", "High"]);
  });
});
