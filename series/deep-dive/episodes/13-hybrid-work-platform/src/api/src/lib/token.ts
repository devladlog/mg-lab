import { LIMITS } from "./config";

/** The slice of CommunicationIdentityClient we use, so tests can pass a recording fake. */
export interface IdentityClientLike {
  createUserAndToken(
    scopes: Array<"voip" | "chat">,
    options?: { tokenExpiresInMinutes?: number },
  ): Promise<{ user: { communicationUserId: string }; token: string; expiresOn: Date }>;
}

export interface GuestToken {
  userId: string;
  token: string;
  expiresOn: string;
}

/**
 * One ephemeral ACS identity per join (Learn, identity model: ephemeral identity scenario), voip scope only
 * (least privilege), the shortest lifetime the guest session needs.
 */
export async function issueGuestToken(client: IdentityClientLike): Promise<GuestToken> {
  const result = await client.createUserAndToken([...LIMITS.token.scopes], {
    tokenExpiresInMinutes: LIMITS.token.expiresInMinutes,
  });
  return {
    userId: result.user.communicationUserId,
    token: result.token,
    expiresOn: result.expiresOn.toISOString(),
  };
}
