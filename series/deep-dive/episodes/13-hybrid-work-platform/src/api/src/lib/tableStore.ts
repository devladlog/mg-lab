import { RestError, TableClient, TableEntity } from "@azure/data-tables";
import { TokenCredential } from "@azure/core-auth";
import { InviteError, InviteRecord, InviteStore } from "./invites";

const PARTITION = "invite";
const MAX_ATTEMPTS = 5;

interface InviteEntity extends TableEntity {
  meetingLink: string;
  expiresOn: string;
  maxUses: number;
  uses: number;
  createdOn: string;
}

const toRecord = (e: InviteEntity): InviteRecord => ({
  codeHash: e.rowKey,
  meetingLink: e.meetingLink,
  expiresOn: e.expiresOn,
  maxUses: e.maxUses,
  uses: e.uses,
  createdOn: e.createdOn,
});

/** Azure Table Storage adapter. Authenticates with the function's managed identity (no keys, no connection string). */
export class TableInviteStore implements InviteStore {
  constructor(private readonly table: TableClient) {}

  static connect(endpoint: string, tableName: string, credential: TokenCredential): TableInviteStore {
    return new TableInviteStore(new TableClient(endpoint, tableName, credential));
  }

  async create(record: InviteRecord): Promise<void> {
    await this.table.createEntity<InviteEntity>({
      partitionKey: PARTITION,
      rowKey: record.codeHash,
      meetingLink: record.meetingLink,
      expiresOn: record.expiresOn,
      maxUses: record.maxUses,
      uses: record.uses,
      createdOn: record.createdOn,
    });
  }

  async consume(codeHash: string, now: Date): Promise<InviteRecord> {
    for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
      let entity: InviteEntity & { etag: string };
      try {
        entity = (await this.table.getEntity<InviteEntity>(PARTITION, codeHash)) as InviteEntity & { etag: string };
      } catch (e) {
        if (e instanceof RestError && e.statusCode === 404) throw new InviteError("not_found");
        throw e;
      }
      if (Date.parse(entity.expiresOn) <= now.getTime()) throw new InviteError("expired");
      if (entity.uses >= entity.maxUses) throw new InviteError("exhausted");
      try {
        // If-Match = the etag we read: a concurrent redeem makes this fail with 412 and we re-read.
        await this.table.updateEntity(
          { partitionKey: PARTITION, rowKey: codeHash, uses: entity.uses + 1 },
          "Merge",
          { etag: entity.etag },
        );
        return toRecord({ ...entity, uses: entity.uses + 1 });
      } catch (e) {
        if (e instanceof RestError && e.statusCode === 412) continue;
        throw e;
      }
    }
    throw new InviteError("conflict");
  }
}
