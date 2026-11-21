export interface RawRequest {
  readonly code: string;
  readonly title: string;
  readonly department: string;
  readonly budget: number;
  readonly requestedBy: string;
}

// The boundary: JSON is `unknown` until a guard says otherwise. No `any`.
export function isRawRequest(value: unknown): value is RawRequest {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v["code"] === "string" &&
    typeof v["title"] === "string" &&
    typeof v["department"] === "string" &&
    typeof v["budget"] === "number" &&
    Number.isFinite(v["budget"]) &&
    typeof v["requestedBy"] === "string"
  );
}

export function parseRequests(json: string): RawRequest[] {
  const data: unknown = JSON.parse(json);
  if (!Array.isArray(data)) throw new TypeError("expected a JSON array of requests");
  const bad = data.findIndex((item: unknown) => !isRawRequest(item));
  if (bad >= 0) throw new TypeError(`element ${bad} is not a valid request`);
  return data.filter(isRawRequest);
}
