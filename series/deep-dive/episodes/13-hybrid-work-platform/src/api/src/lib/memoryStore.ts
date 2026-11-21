import { InviteError, InviteRecord, InviteStore } from "./invites";

/**
 * In-memory twin of the table adapter with the same optimistic-concurrency contract.
 * Used by the unit tests only; the demo always runs against the real table.
 */
export class MemoryInviteStore implements InviteStore {
  private readonly rows = new Map<string, { record: InviteRecord; version: number }>();
  /** Test hook: runs between the read and the conditional write, to force a concurrent writer. */
  public beforeWrite?: (codeHash: string) => void;

  async create(record: InviteRecord): Promise<void> {
    if (this.rows.has(record.codeHash)) throw new Error("duplicate invite");
    this.rows.set(record.codeHash, { record: { ...record }, version: 1 });
  }

  async consume(codeHash: string, now: Date): Promise<InviteRecord> {
    for (let attempt = 0; attempt < 5; attempt++) {
      const row = this.rows.get(codeHash);
      if (!row) throw new InviteError("not_found");
      if (Date.parse(row.record.expiresOn) <= now.getTime()) throw new InviteError("expired");
      if (row.record.uses >= row.record.maxUses) throw new InviteError("exhausted");
      const readVersion = row.version;
      this.beforeWrite?.(codeHash);
      const current = this.rows.get(codeHash)!;
      if (current.version !== readVersion) continue; // 412 Precondition Failed in Table Storage
      current.record = { ...current.record, uses: current.record.uses + 1 };
      current.version += 1;
      return { ...current.record };
    }
    throw new InviteError("conflict");
  }
}
