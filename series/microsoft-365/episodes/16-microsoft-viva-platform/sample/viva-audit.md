# Viva Engage audit

Generated: 2026-11-20 09:30 UTC | communities: 4

**Findings:** High 3 | Medium 4 | Low 1 | Info 2

| Severity | Subject | Rule | Detail |
|---|---|---|---|
| High | Falcon Hackathon | NoOwner | No owner. Nobody can manage this community, and requests for help have nowhere to go. |
| High | jordan.demo@contoso.com | UnexpectedNetworkAdmin | Network Administrator who is not in settings.allowedNetworkAdmins. |
| High | sam.demo@contoso.com | UnexpectedNetworkAdmin | Network Administrator who is not in settings.allowedNetworkAdmins. |
| Medium | Contoso Ask Anything | PrivacyDrift | Privacy is private, config says public. |
| Medium | Falcon Customer Stories | MissingCommunity | In the config, not in the tenant. Run -Apply. |
| Medium | Network Administrator | TooManyNetworkAdmins | 4 Network Administrators, policy allows 3. |
| Medium | Project Falcon - Launch | FewOwners | 1 owner(s), policy asks for 2. |
| Low | Lunch Club | NoMembers | Only owners are members. |
| Info | Falcon Hackathon | NotInConfig | Not described in communities.json. The script leaves it alone. |
| Info | Lunch Club | NotInConfig | Not described in communities.json. The script leaves it alone. |

## Communities

| Name | Privacy | Owners | Members |
|---|---|---|---|
| Project Falcon - Launch | private | 1 | 4 |
| Contoso Ask Anything | private | 2 | 4 |
| Falcon Hackathon | public | 0 | 1 |
| Lunch Club | public | 2 | 2 |

## Viva Engage roles

| Role | Members |
|---|---|
| Network Administrator | 4 |
| Verified Administrator | 1 |

