import { LIMITS } from "./config";

export class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
  }
}

/**
 * Only a real Teams meeting link may be stored in an invite. The guest page hands this link to the
 * Calling SDK, so a lookalike host would send guests to an attacker's meeting.
 * Learn: Teams interoperability is not enabled for Teams for personal use (teams.live.com), so that host is refused too.
 */
export function validateMeetingLink(raw: unknown): string {
  if (typeof raw !== "string" || raw.trim() === "") {
    throw new ValidationError("meetingLink is required.");
  }
  const text = raw.trim();
  if (text.length > LIMITS.maxMeetingLinkLength) {
    throw new ValidationError("meetingLink is too long.");
  }
  let url: URL;
  try {
    url = new URL(text);
  } catch {
    throw new ValidationError("meetingLink is not a valid URL.");
  }
  if (url.protocol !== "https:") {
    throw new ValidationError("meetingLink must use https.");
  }
  if (url.username || url.password || url.port) {
    throw new ValidationError("meetingLink must not contain credentials or a port.");
  }
  if (!LIMITS.token.allowedMeetingHosts.includes(url.hostname.toLowerCase())) {
    throw new ValidationError("meetingLink must be a Microsoft Teams work or school meeting link (teams.microsoft.com).");
  }
  if (!/^\/(l\/meetup-join|meet)\//i.test(url.pathname)) {
    throw new ValidationError("meetingLink is not a Teams meeting join link.");
  }
  return url.toString();
}

export function validateDisplayName(raw: unknown): string {
  const fallback = "Guest";
  if (raw === undefined || raw === null || raw === "") return fallback;
  if (typeof raw !== "string") throw new ValidationError("displayName must be text.");
  // eslint-disable-next-line no-control-regex
  const cleaned = raw.replace(/[\u0000-\u001f\u007f]/g, "").trim();
  if (cleaned === "") return fallback;
  if (cleaned.length > LIMITS.maxDisplayNameLength) {
    throw new ValidationError(`displayName is longer than ${LIMITS.maxDisplayNameLength} characters.`);
  }
  return cleaned;
}
