# Demo shot list - Copilot & AI #8 Copilot in Dynamics 365 Sales and Customer Service

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Tenant | Momento Galático lab tenant, account `labadmin` (Global Administrator, System Administrator in the environments below) |
| Sales | The existing **Dynamics 365 Sales trial environment** ("Sales trial", EMEA, expires about 21 Dec 2026). Record the Sales screens before it expires. **Check first which licence the trial gives `labadmin`**: Sales Professional has no Copilot (pricing page, below), Enterprise and Premium do. If Copilot does not appear, record that (screen `copilot-settings` shows the real state) and stop the Sales screens: that is the honest take, and the price of the licence that would unlock it goes on the slide |
| Customer Service | **Not provisioned yet. Owner decision:** start a **Dynamics 365 Customer Service trial** (Learn mentions a 30-day trial; confirm length and Copilot content on the sign-up page) in its own environment, region matching the Sales trial (EMEA). Cost 0 EUR during the trial. Paid reference prices (USD per user per month, paid yearly, read 21 Nov 2026 on the Microsoft pricing pages): Customer Service Professional 50 (no Copilot), Enterprise 105, Premium 195 (Copilot). Do not buy a licence for this episode |
| Sales agent in Microsoft 365 Copilot | **Not recorded.** It needs a Microsoft 365 Copilot licence for Graph data (Enterprise or Premium Sales alone gives CRM data only, per Learn). The lab has no Microsoft 365 Copilot licence. The narration only states the licence rule |
| Copilot Credits | Not needed for the screens in this episode. Do not turn on pay-as-you-go billing |
| Admin settings (changed on camera, listed for tear-down) | Power Platform admin center: Copilot settings for the environment (Sales: Copilot on; Customer Service: *Enable AI-powered Copilot features*); data movement across regions if the admin center says it is required. Sales Hub > App Settings > Copilot: turn on, *Turn audit on* (audit on lead, opportunity and account). Copilot Service admin center: *Opt in*, Copilot help pane with *Use your organization's knowledge base*, experience profile with Copilot features; Dataverse search on |
| Azure resources | None |
| Recording machine | Windows lab laptop: Edge/Chrome profile for `labadmin`, Windows Terminal with Python 3.10+ (and Azure CLI for the token step). Mask the organisation URL and tenant name on every screen |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the lab tenant |
|---|---|---|
| Rules and the sample result (7 errors, 11 warnings, 9 info) | yes, 29 pytest tests | - |
| Paging, headers, error handling of the Web API client | yes, against a local test server (tests only) | - |
| **Live queries** (entity sets, `$select` columns, annotation and email filters, `languagelocale`) | no | **first real run: do this before recording** and fix the column list if the org rejects one |
| Token flow with Azure CLI | no | yes |
| Every Copilot screen | no | yes |

Open points to settle on the tenant (each can change the script):
1. Does the trial licence expose Copilot in Sales / Customer Service? If not, rewrite the matching scenes (`opp-screen`,
   `case-screen`, `kb-screen`) as "the licence is missing", show the real message, and show the price.
2. The 38 word rule: which fields count is not spelled out by Learn. Take the two cases below and record what really
   happens. If CAS-1002 still gets a summary, the rule text in the script and README must change.
3. Whether Ask a question answers from the draft article (it should not) and what it says: record the real text.
4. Opportunity summaries use audit history of the last two months: create the records **after** turning audit on, and
   change the stage of the Tailspin opportunity once so there is a stage update to read.

## Prerequisites
- `python -m pip install -r src/requirements.txt`; `python -m pytest` -> `29 passed`.
- Terminal: dark theme, 18 pt, 1600x900. Browser dark theme, 125 %.
- Customer Service trial provisioned at least a day before recording (Knowledge indexing and Dataverse search need time).

## Setup
1. **Admin settings** (screen `copilot-settings`): do the settings of the environment table above, once per environment.
2. **Create the Contoso records by hand** in the Sales / Customer Service apps. The sample JSON ids are not imported;
   create these records with the same field values as `src/data/sample/*.json` (a handful of records, 20 minutes).
   Use only `Alex Demo` as the contact and fictional account names, all marked `(sample)`.

   | Entity | Record | Fields to set |
   |---|---|---|
   | Opportunity | `Tailspin fleet: 40 e-bikes` | account Tailspin Tours (sample), contact Alex Demo, est. revenue 48,000, est. close date within 3 months, budget 52,000, 2 products, 1 quote |
   | Opportunity | `Proseware courier trial` | **no account**, contact Alex Demo, est. revenue 9,000, no products, no quote |
   | Opportunity | `Litware rental refresh` | account Litware Rentals (sample) with **empty industry**, **no contact, no revenue, no close date**, 1 product, no quote |
   | Opportunity | `Woodgrove lobby bikes` (won, 12,500) and `Tailspin spares contract` (won, 7,300) | give the two accounts closed history |
   | Case | `CAS-1001` | the long description of the sample (hub clicking under load), customer, product, subject, type |
   | Case | `CAS-1002` | title `Battery issue`, description `Battery does not charge.`, nothing else |
   | Case | `CAS-1003` | short description `Pads worn after one month.`, plus the two notes and the email of the sample |
   | Knowledge | `KA-0001` | published, English, content as in the sample (reset error E21) |
   | Knowledge | `KA-0002` | **draft**, English (hub warranty terms) |
   | Knowledge | `KA-0004` | published, Portuguese (pt-PT) |
   | Knowledge | `KA-0005` | published, English, content = a table only |
3. **Token and live run** (terminal, never saved to a file):
   ```bash
   export DATAVERSE_TOKEN="$(az account get-access-token --resource https://<org>.crm4.dynamics.com --query accessToken -o tsv)"
   python -m d365_copilot_ready check --org https://<org>.crm4.dynamics.com --ui-language 1033
   ```
   (`az login` is done by the recorder, not by this episode's tooling.) The tool prints the masked org URL
   (`https://***.crm4.dynamics.com`). Close the terminal afterwards so the token disappears.
   The expected findings are the ones in the sample list for the records you created; anything else is real data.
4. Rehearse every prompt once and write the exact prompts down.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `setup-screen` | `screens/copilot-settings.jpg` | Sales Hub > App Settings > Copilot (Copilot on, audit setting) next to Copilot Service admin center > Copilot settings (opt in, data movement status). Real state, whatever it is. Mask org URL and tenant |
| `opp-screen` | `screens/opportunity-summary.jpg` | `Tailspin fleet: 40 e-bikes`: summary banner expanded, then `Proseware courier trial`: summary expanded. Side window with the Learn attribute list. Record exactly what appears |
| `case-screen` | `screens/case-summary.jpg` | Copilot Service workspace: `CAS-1001` with the summary card expanded, then `CAS-1002` and what the card does. If a message appears, show it |
| `kb-screen` | `screens/ask-a-question.jpg` | Copilot help pane, Ask a question: "How do I reset error E21 on the Contoso Volt display?" with *Check sources* open, then "What does the hub warranty cover?" and the real response |

Optional extra take (not in the script): terminal with the live `check` output on the real records, next to the case
and article lists, to show that the findings match the screens.

## Masking
Organisation URL (`https://<org>.crm4.dynamics.com`), tenant name and domain, user principal names (use `labadmin` and
`Alex Demo`), environment ids. Fictional data only; nothing from a real customer. Never show the token.

## Tear-down
1. Unset the token (close the terminal). `az logout` only if the recorder logged in for this episode.
2. Delete the demo records (opportunities, accounts, contacts, cases, knowledge articles marked `(sample)`).
3. Revert the admin settings you changed if they were off before (audit can stay on; Learn notes turning audit off is manual per table).
4. Customer Service trial environment: let it expire or delete it in the Power Platform admin center. The Sales trial
   stays for the Dynamics 365 category episodes.
