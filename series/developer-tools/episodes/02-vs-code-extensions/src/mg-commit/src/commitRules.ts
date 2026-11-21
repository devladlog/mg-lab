// Conventional Commits rules, no `vscode` import: unit-testable with plain Node.
// Same rules as the commit-msg hook from episode 1 (tools/repo_guard/commit_rules.py).

export const DEFAULT_TYPES = [
  "build", "chore", "ci", "docs", "feat", "fix",
  "perf", "refactor", "revert", "style", "test",
] as const;

export const MAX_HEADER = 72;

const HEADER_RE = /^(?<type>[a-z]+)(?:\((?<scope>[a-z0-9][a-z0-9._/-]*)\))?(?<breaking>!)?: (?<subject>\S.*)$/;
const SCOPE_RE = /^[a-z0-9][a-z0-9._/-]*$/;
const PASSTHROUGH = ["Merge ", 'Revert "', "fixup! ", "squash! ", "amend! "];
const SCISSORS = "# ------------------------ >8 ------------------------";

export interface CommitParts {
  type: string;
  scope?: string;
  breaking?: boolean;
  subject: string;
}

export function buildHeader(p: CommitParts): string {
  const scope = p.scope ? `(${p.scope})` : "";
  return `${p.type}${scope}${p.breaking ? "!" : ""}: ${p.subject.trim()}`;
}

/** Live validation for the subject input box: returns a message, or undefined when it's fine. */
export function validateSubject(p: CommitParts): string | undefined {
  const subject = p.subject.trim();
  if (subject === "") return "Describe the change, e.g. add paging to the orders endpoint";
  if (subject.endsWith(".")) return "No period at the end";
  if (/^[A-Z][a-z]/.test(subject)) return "Start with a lower-case verb: add, fix, remove...";
  const length = buildHeader(p).length;
  if (length > MAX_HEADER) return `Header is ${length}/${MAX_HEADER} characters: shorten the subject`;
  return undefined;
}

export function validateScope(scope: string): string | undefined {
  if (scope === "" || SCOPE_RE.test(scope)) return undefined;
  return "Lower case letters, digits and . _ / - only";
}

export interface CheckResult {
  ok: boolean;
  errors: string[];
}

/** Full-message check, identical in behaviour to the episode 1 hook. */
export function checkMessage(message: string, types: readonly string[] = DEFAULT_TYPES): CheckResult {
  const raw = message.replace(/\r\n/g, "\n").split("\n");
  const cut = raw.findIndex((l) => l.startsWith(SCISSORS));
  const lines = (cut >= 0 ? raw.slice(0, cut) : raw)
    .filter((l) => !l.startsWith("#"))
    .map((l) => l.trimEnd());
  while (lines.length && lines[0] === "") lines.shift();
  while (lines.length && lines[lines.length - 1] === "") lines.pop();
  if (lines.length === 0) return { ok: false, errors: ["empty commit message"] };

  const header = lines[0];
  if (PASSTHROUGH.some((p) => header.startsWith(p))) return { ok: true, errors: [] };

  const m = HEADER_RE.exec(header);
  if (!m?.groups) return { ok: false, errors: [`header must look like 'type(scope): subject', got: '${header}'`] };

  const errors: string[] = [];
  if (!types.includes(m.groups.type)) errors.push(`unknown type '${m.groups.type}'; use one of: ${types.join(", ")}`);
  if (header.length > MAX_HEADER) errors.push(`header is ${header.length} characters; keep it to ${MAX_HEADER}`);
  if (m.groups.subject.endsWith(".")) errors.push("subject must not end with a period");
  if (lines.length > 1 && lines[1] !== "") errors.push("leave one blank line between the header and the body");
  return { ok: errors.length === 0, errors };
}

/** Put a new header into the SCM input box, keeping any body the developer already wrote. */
export function replaceHeader(existing: string, header: string): string {
  const lines = existing.replace(/\r\n/g, "\n").split("\n");
  const body = lines.slice(1).join("\n").replace(/^\n+/, "");
  return body ? `${header}\n\n${body}` : header;
}

/** Settings arrive as `unknown`; keep only valid, unique entries and fall back to the defaults. */
export function normaliseTypes(value: unknown): string[] {
  if (!Array.isArray(value)) return [...DEFAULT_TYPES];
  const clean = value.filter((v): v is string => typeof v === "string" && /^[a-z]+$/.test(v));
  return clean.length ? [...new Set(clean)] : [...DEFAULT_TYPES];
}
