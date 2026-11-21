// The app's own users. Embed for your customers lets the app authenticate people any way it likes;
// here the "login" is a dropdown. Who is in which role mirrors episode 5 (src/data/role_members.csv).
// nobody.demo is in no mapping row: the role gives them nothing.

export interface AppUser {
  alias: string;
  displayName: string;
  roles: string[];
}

export const APP_USERS: readonly AppUser[] = [
  { alias: "alex.demo", displayName: "Alex Demo", roles: ["Store Managers"] },
  { alias: "sam.demo", displayName: "Sam Demo", roles: ["Store Managers"] },
  { alias: "riley.demo", displayName: "Riley Demo", roles: ["Store Managers"] },
  { alias: "taylor.demo", displayName: "Taylor Demo", roles: ["Store Managers"] },
  { alias: "jordan.demo", displayName: "Jordan Demo", roles: ["Head Office"] },
  { alias: "nobody.demo", displayName: "Nobody Demo", roles: ["Store Managers"] },
];

export function findUser(alias: string): AppUser | undefined {
  return APP_USERS.find((u) => u.alias === alias);
}

/** The value USERPRINCIPALNAME() returns in the model's role: the same lower case UPN as the mapping table of episode 5. */
export function upnFor(alias: string, upnDomain: string): string {
  return `${alias}@${upnDomain}`.toLowerCase();
}
