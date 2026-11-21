import { readFile } from "node:fs/promises";
import * as path from "node:path";

/** The only files the page function will ever serve. No path from the request reaches the file system. */
const ASSETS: Record<string, { file: string; type: string }> = {
  "join.js": { file: "join.js", type: "text/javascript; charset=utf-8" },
  "join.css": { file: "join.css", type: "text/css; charset=utf-8" },
};

export const PAGE = { file: "index.html", type: "text/html; charset=utf-8" };

export function resolveAsset(name: string): { file: string; type: string } | undefined {
  return Object.prototype.hasOwnProperty.call(ASSETS, name) ? ASSETS[name] : undefined;
}

export async function readSiteFile(siteDir: string, file: string): Promise<Buffer> {
  return readFile(path.join(siteDir, file));
}
