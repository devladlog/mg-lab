import { createHash, randomBytes } from "node:crypto";
import { LIMITS } from "./config";
import { ValidationError, validateMeetingLink } from "./meeting";

export interface InviteRecord {
  /** SHA-256 of the code. The code itself is never stored. */
  codeHash: string;
  meetingLink: string;
  expiresOn: string; // ISO 8601, UTC
  maxUses: number;
  uses: number;
  createdOn: string;
}

export type InviteFailure = "not_found" | "expired" | "exhausted" | "conflict";

export class InviteError extends Error {
  constructor(public readonly reason: InviteFailure) {
    super(`Invite refused: ${reason}`);
    this.name = "InviteError";
  }
}

/** Storage port. The production adapter is Azure Table Storage (tableStore.ts); tests use an in-memory twin. */
export interface InviteStore {
  create(record: InviteRecord): Promise<void>;
  /**
   * Atomically add one use. Must fail with `exhausted`/`expired`/`not_found`, and must never let two
   * concurrent callers both take the last use (the table adapter uses optimistic concurrency).
   */
  consume(codeHash: string, now: Date): Promise<InviteRecord>;
}

export const hashCode = (code: string): string => createHash("sha256").update(code, "utf8").digest("hex");

export interface CreateInviteInput {
  meetingLink?: unknown;
  validMinutes?: unknown;
  maxUses?: unknown;
}

export interface CreatedInvite {
  code: string;
  expiresOn: string;
  maxUses: number;
}

function boundedInt(value: unknown, name: string, fallback: number, max: number): number {
  if (value === undefined || value === null) return fallback;
  if (typeof value !== "number" || !Number.isInteger(value) || value < 1 || value > max) {
    throw new ValidationError(`${name} must be a whole number between 1 and ${max}.`);
  }
  return value;
}

export async function createInvite(
  store: InviteStore,
  input: CreateInviteInput,
  now: Date = new Date(),
  random: (n: number) => Buffer = randomBytes,
): Promise<CreatedInvite> {
  const meetingLink = validateMeetingLink(input.meetingLink);
  const validMinutes = boundedInt(input.validMinutes, "validMinutes", LIMITS.invite.defaultValidMinutes, LIMITS.invite.maxValidMinutes);
  const maxUses = boundedInt(input.maxUses, "maxUses", LIMITS.invite.defaultMaxUses, LIMITS.invite.maxMaxUses);
  const code = random(LIMITS.invite.codeBytes).toString("base64url");
  const expiresOn = new Date(now.getTime() + validMinutes * 60_000).toISOString();
  await store.create({
    codeHash: hashCode(code), // only the hash is stored
    meetingLink,
    expiresOn,
    maxUses,
    uses: 0,
    createdOn: now.toISOString(),
  });
  return { code, expiresOn, maxUses };
}

/** Codes are 32 random bytes in base64url (43 characters). Anything else is refused before any lookup. */
export function looksLikeCode(code: unknown): code is string {
  return typeof code === "string" && /^[A-Za-z0-9_-]{43}$/.test(code);
}

export async function redeemInvite(store: InviteStore, code: unknown, now: Date = new Date()): Promise<InviteRecord> {
  if (!looksLikeCode(code)) throw new InviteError("not_found");
  return store.consume(hashCode(code), now);
}
