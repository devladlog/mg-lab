# Microsoft 365 Copilot readiness report

Generated: 2026-11-21

## Licence

**No Microsoft 365 Copilot licence in this tenant.** Copilot Chat with Entra accounts still works (see users below); Copilot in Word, Excel, PowerPoint, Outlook and Teams, and grounding in Microsoft Graph, need the add-on licence.

## Users

| User | Status | Copilot Chat | Mailbox | Microsoft 365 Apps | Notes |
|---|---|---|---|---|---|
| labadmin@contoso.com | Copilot Chat only | yes | yes | yes |  |
| alex.demo@contoso.com | Copilot Chat only | yes | yes | yes |  |
| sam.demo@contoso.com | Copilot Chat only | yes | yes | yes |  |
| jordan.demo@contoso.com | Not ready | yes | yes | yes | account disabled |
| riley.demo@contoso.com | Not ready | no | yes | yes | no Copilot Chat entitlement plan |
| taylor.demo@contoso.com | Copilot Chat only | yes | no | yes | no Exchange Online mailbox plan: mailbox-grounded answers need one |

## Sensitivity labels (4 listed)

- **Medium** NoContainerLabel: No enabled label is applicable to sites or groups (container labels), so a site cannot carry a label.
- **Low** NoAutoLabel: No label applies automatically: labeling depends on people.

## Oversharing review (12 items scanned)

| Severity | Signal | Site | Path | Role |
|---|---|---|---|---|
| High | OrganizationLink | Contoso Marketing | /Board/minutes.docx | read |
| High | AnyoneLink | Contoso Marketing | /HR/salary-bands.xlsx | read |
| Medium | OrganizationLink | Contoso Marketing | /Campaigns/Launch plan.docx | write |
| Medium | EveryoneExceptExternalUsers | Contoso Marketing | /HR | read |

_Sampled walk of the sites searched, limited by `sharing.maxItemsPerDrive` and `maxDepth`. It is not a replacement for the SharePoint Advanced Management data access governance reports, which cover the whole tenant._

