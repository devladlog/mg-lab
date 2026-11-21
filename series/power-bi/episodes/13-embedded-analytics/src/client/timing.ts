// When to ask the server for a new embed token. Shared by the browser and the server cache.

export const REFRESH_MARGIN_MS = 5 * 60 * 1000;

/** Milliseconds to wait before refreshing; 0 when the token is already inside the margin. */
export function msUntilRefresh(expirationIso: string, nowMs: number, marginMs: number = REFRESH_MARGIN_MS): number {
  const expires = Date.parse(expirationIso);
  if (Number.isNaN(expires)) return 0;
  return Math.max(0, expires - marginMs - nowMs);
}
