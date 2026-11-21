import { InviteError, InviteStore, createInvite, redeemInvite } from "./invites";
import { ValidationError, validateDisplayName } from "./meeting";
import { GuestToken, IdentityClientLike, issueGuestToken } from "./token";

export interface HttpResult {
  status: number;
  body: unknown;
  headers?: Record<string, string>;
}

const NO_STORE = { "Cache-Control": "no-store" };

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

/** POST /api/invites (function key): host side. Returns the URL to send to the guest. */
export async function handleCreateInvite(
  store: InviteStore,
  body: unknown,
  publicBaseUrl: string,
  now: Date = new Date(),
): Promise<HttpResult> {
  if (!isObject(body)) return { status: 400, body: { error: "JSON body required." }, headers: NO_STORE };
  try {
    const invite = await createInvite(store, body, now);
    // The code goes in the URL fragment: browsers never send it to the server, to logs or in Referer headers.
    const inviteUrl = `${publicBaseUrl.replace(/\/$/, "")}/join#i=${invite.code}`;
    return { status: 201, body: { inviteUrl, expiresOn: invite.expiresOn, maxUses: invite.maxUses }, headers: NO_STORE };
  } catch (e) {
    if (e instanceof ValidationError) return { status: 400, body: { error: e.message }, headers: NO_STORE };
    throw e;
  }
}

export interface RedeemResponse extends GuestToken {
  meetingLink: string;
  displayName: string;
}

/**
 * POST /api/token (anonymous): guest side. An unknown, expired or used-up invite all look the same
 * from outside (403, one message), so the endpoint cannot be used to probe which codes exist.
 */
export async function handleRedeem(
  store: InviteStore,
  identity: IdentityClientLike,
  body: unknown,
  now: Date = new Date(),
  log: (message: string) => void = () => {},
): Promise<HttpResult> {
  if (!isObject(body)) return { status: 400, body: { error: "JSON body required." }, headers: NO_STORE };
  let displayName: string;
  try {
    displayName = validateDisplayName(body["displayName"]);
  } catch (e) {
    if (e instanceof ValidationError) return { status: 400, body: { error: e.message }, headers: NO_STORE };
    throw e;
  }
  try {
    const invite = await redeemInvite(store, body["code"], now);
    const token = await issueGuestToken(identity);
    const payload: RedeemResponse = { ...token, meetingLink: invite.meetingLink, displayName };
    return { status: 200, body: payload, headers: NO_STORE };
  } catch (e) {
    if (e instanceof InviteError) {
      log(`invite refused: ${e.reason}`);
      return { status: 403, body: { error: "This invitation is not valid." }, headers: NO_STORE };
    }
    throw e;
  }
}
