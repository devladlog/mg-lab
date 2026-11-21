// Effective identity for row-level security in an embed token (GenerateToken, "identities").
// The limits are the ones in Learn's EffectiveIdentity definition:
// https://learn.microsoft.com/en-us/rest/api/power-bi/embed-token/generate-token#effectiveidentity

export interface EffectiveIdentity {
  username: string;
  roles: string[];
  datasets: string[];
}

export class IdentityError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "IdentityError";
  }
}

const MAX_USERNAME = 256;
const MAX_ROLES = 50;
const MAX_ROLE_LENGTH = 50;

export function buildIdentity(username: string, roles: readonly string[], datasetId: string): EffectiveIdentity {
  if (!username) throw new IdentityError("username is required");
  if (username.length > MAX_USERNAME) throw new IdentityError(`username is longer than ${MAX_USERNAME} characters`);
  if (/\s/.test(username)) throw new IdentityError("username must not contain spaces");
  // eslint-disable-next-line no-control-regex
  if (/[^\x21-\x7e]/.test(username)) throw new IdentityError("username must be printable ASCII (cloud models)");
  // With a service principal, Learn says token generation fails when RLS applies and no role is sent.
  if (roles.length === 0) throw new IdentityError("at least one role is required");
  if (roles.length > MAX_ROLES) throw new IdentityError(`an identity can hold at most ${MAX_ROLES} roles`);
  for (const role of roles) {
    if (!role) throw new IdentityError("a role name is empty");
    if (role.includes(",")) throw new IdentityError(`role "${role}" contains a comma`);
    if (role.length > MAX_ROLE_LENGTH) throw new IdentityError(`role "${role}" is longer than ${MAX_ROLE_LENGTH} characters`);
  }
  if (!datasetId) throw new IdentityError("the dataset id is required");
  return { username, roles: [...roles], datasets: [datasetId] };
}
