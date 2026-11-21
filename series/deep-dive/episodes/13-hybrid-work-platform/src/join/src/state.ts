// Pure helpers for the join page: no DOM, no SDK, so they run in plain Node tests.

/** Invite codes are 32 random bytes in base64url (43 characters), carried in the URL fragment: #i=<code> */
export function parseInvite(hash: string): string | undefined {
  const match = /^#?i=([A-Za-z0-9_-]{43})$/.exec(hash);
  return match?.[1];
}

export type CallState =
  | "None" | "Connecting" | "Ringing" | "Connected" | "LocalHold" | "RemoteHold"
  | "InLobby" | "Disconnecting" | "Disconnected" | "EarlyMedia";

export interface StatusView {
  text: string;
  tone: "info" | "wait" | "ok" | "end" | "error";
  canMute: boolean;
  canLeave: boolean;
}

export function describeCallState(state: CallState, endCode?: number, endSubCode?: number): StatusView {
  switch (state) {
    case "None":
    case "Connecting":
    case "Ringing":
    case "EarlyMedia":
      return { text: "Connecting to the meeting...", tone: "info", canMute: false, canLeave: true };
    case "InLobby":
      // Learn: a guest is not admitted until a Teams user is present, then waits until someone admits them.
      return { text: "Waiting in the lobby. The host will let you in.", tone: "wait", canMute: false, canLeave: true };
    case "Connected":
      return { text: "You are in the meeting.", tone: "ok", canMute: true, canLeave: true };
    case "LocalHold":
    case "RemoteHold":
      return { text: "The call is on hold.", tone: "info", canMute: false, canLeave: true };
    case "Disconnecting":
      return { text: "Leaving...", tone: "end", canMute: false, canLeave: false };
    case "Disconnected":
      return describeEnd(endCode, endSubCode);
  }
}

function describeEnd(code?: number, subCode?: number): StatusView {
  const base = { canMute: false, canLeave: false } as const;
  if (code === undefined || code === 0 || code === 200) {
    return { text: "You left the meeting.", tone: "end", ...base };
  }
  const detail = subCode === undefined ? `code ${code}` : `code ${code}, sub-code ${subCode}`;
  return { text: `The call ended (${detail}). Ask your host for a new invitation if you were not admitted.`, tone: "error", ...base };
}

export type RedeemError = "invalid" | "bad-name" | "network" | "server";

export function classifyRedeemStatus(status: number): RedeemError {
  if (status === 403) return "invalid";
  if (status === 400) return "bad-name";
  if (status === 0) return "network";
  return "server";
}

export function redeemMessage(error: RedeemError): string {
  switch (error) {
    case "invalid":
      return "This invitation is no longer valid. Ask your host for a new one.";
    case "bad-name":
      return "Please check your name (up to 64 characters).";
    case "network":
      return "Could not reach the service. Check your connection and try again.";
    case "server":
      return "Something went wrong on our side. Try again in a moment.";
  }
}
