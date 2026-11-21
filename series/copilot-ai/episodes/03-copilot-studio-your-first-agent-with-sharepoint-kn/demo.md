# Demo shot list - Copilot & AI #3 Copilot Studio: Your First Agent with SharePoint Knowledge

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Tenant | Momento Galático lab tenant: Microsoft 365 E5 trial (SharePoint Online, Microsoft Search), Power Platform environment `DEV` (Dataverse) |
| Accounts | `labadmin` (Global Administrator, **Copilot Studio trial licence**): builds the agent, owns the SharePoint site, runs the evaluation. `sam.demo` (**Copilot Studio trial licence**): the second user for the "no answer" take, a member of the site's Visitors group but **without** access to the Restricted library. `alex.demo` is not needed |
| Licences / purchases | **Nothing bought. Cost 0.** The Copilot Studio trial licence can build and test but **not publish** (Learn: *Licensing for agents powered by the standard harness*), so the whole demo runs in the test chat and the Evaluation page; nothing is published. Test chat usage is not billed (Learn FAQ). Evaluation runs may show a *Uses Copilot Credits* badge in the newer experience: read it before pressing Run and tell the owner if it asks for a pay-as-you-go plan (not set in the lab). For the script's pricing slide (published agents): classic answer 1 Copilot Credit, generative answer 2, tenant graph grounding 10; pay-as-you-go US$0.01 per credit; users holding a Microsoft 365 Copilot licence are not charged for those answers (Learn *Billing rates and management*). The lab has **no** Microsoft 365 Copilot licence, so do **not** turn on *Tenant graph grounding with semantic search* (needs one) and keep every file under **7 MB** |
| Azure | none |
| Entra | One app registration for PnP PowerShell (needed for interactive sign-in since 9 Sep 2024, PnP docs). Create it once: `Register-PnPEntraIDApp -ApplicationName "MGLab PnP" -Tenant <tenant>.onmicrosoft.com -Interactive` and keep the app id out of the repo and off camera. Delete the app registration in tear-down |
| Recording machine | Windows lab laptop: browser profiles for `labadmin` and `sam.demo`, PowerShell 7 with `PnP.PowerShell` 3.x (`Install-Module PnP.PowerShell -Scope CurrentUser`), Python 3.10+ with `pip install -r src/requirements.txt` |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the lab tenant |
|---|---|---|
| `kbpack build`, `check`, `testset`: documents, limits checks, test-set CSV (format per Learn) | yes: 26 pytest tests; the five generated .docx open with python-docx | - |
| `New-VendorKnowledgeSite.ps1`: parameters, order of calls, permissions before upload, tear-down | yes: parsed and executed under `pwsh` with stand-ins for the PnP cmdlets (7 tests, test only) | **first real run**; the cmdlet names and parameters were checked against the PnP PowerShell docs, not against a live site |
| Everything Copilot Studio shows (create agent, knowledge, answers, trimming, evaluation) | no | **record it** |
| The exact wording the agent gives when it has no answer, and how long SharePoint takes to index | no | **record whatever really happens** |

Open points to confirm on the tenant (each can change a scene):
1. Whether the create-agent page offers the standard experience: Learn says to turn off *New experience* to get the
   agent type documented in this episode. If only the new experience exists, say so on camera and record what it shows.
2. What the agent answers when it has no result (Learn: it may say *I'm not sure how to help with that. Can you try
   rephrasing?*). The `trimmed` scene and the out-of-scope test questions use whatever the real text is.
3. Whether the *Compare meaning* and *General quality* methods are available in `DEV` (Learn: available methods can
   vary by environment).
4. How long the new documents take to appear in SharePoint search (see Setup, step 5).
5. That the test chat really uses the signed-in maker's SharePoint access (Learn says the agent surfaces only what the
   user can read, and that evaluations use the signed-in user). If Sam's take answers anyway, stop and rewrite `trimmed`.

## Prerequisites
- Terminal: dark theme, 18 pt, window 1600x900, short prompt (`function prompt { 'PS> ' }`). Browser dark theme, 125 %.
- `cd series/copilot-ai/episodes/03-copilot-studio-your-first-agent-with-sharepoint-kn`
- `python -m pip install -r src/requirements.txt` and `python -m pytest -q` -> `33 passed`.

## Setup (do all of it the day before; the index needs time)
1. `cd src; python -m kbpack build --out ../out/docs` (5 files). `python -m kbpack check ../out/docs/Policies` -> READY.
2. Open `src/scripts/New-VendorKnowledgeSite.ps1` in the terminal and run it as the **site owner** (labadmin):
   ```powershell
   ./scripts/New-VendorKnowledgeSite.ps1 -TenantUrl https://<tenant>.sharepoint.com -ClientId <app id> `
       -OwnerUpn <labadmin UPN> -RestrictedUserUpn <labadmin UPN> -ReaderUpns <sam.demo UPN> -DocsPath ../out/docs
   ```
   Sign in on camera or off camera; never paste a password. Run with `-WhatIf` first to show the plan.
3. In SharePoint as `sam.demo`: open the site, confirm **Policies** opens and **Restricted** shows "access denied".
   As `labadmin` confirm both open.
4. `python -m kbpack testset --docs ../out/docs --out ../out/eval` -> two CSV files.
5. Indexing: in the site's search box, as `labadmin`, search a word that only the Restricted file has ("walk-away")
   and one from Policies ("Thursday"). Both must return the file before you record. If not after a few hours, use
   Site Information > View all site settings > Search and offline availability > **Re-index site** (Learn:
   *SharePoint knowledge sources don't return results*). Note how long it really took: it is a good on-camera aside.
6. In Copilot Studio (labadmin, environment `DEV`) build the agent as in the scenes below, once off camera, to know the
   real wording. Then delete it and record, or record straight away if it worked.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `create-agent` | `screens/create-agent.jpg` | copilotstudio.microsoft.com as labadmin, `DEV`. Describe the agent: *Answer Contoso employees' questions about vendor onboarding, payment terms, security requirements and renewals. Use only the knowledge sources.* Then the Overview page: name **Contoso Vendor Desk**, generated instructions (edit them to say: answer only from the knowledge sources; if there is no answer say so and suggest asking the Vendor Management Office). Mask tenant, email domain |
| `add-knowledge` | `screens/add-knowledge.jpg` | **Knowledge > Add knowledge > SharePoint** in the *Featured* section (not the one under *Upload file*). Paste `<tenant>.sharepoint.com/sites/contoso-vmo/Policies` (mask the tenant), name *Vendor policies*, description *Contoso vendor onboarding, approval tiers, payment terms, security requirements, renewals and offboarding.* After adding, the source in the list. Then **Settings > Generative AI**: Web Search off, *Use general knowledge* off |
| `ask` | `screens/ask.jpg` | Test panel as labadmin: *Who has to approve a new vendor that costs 12,000 euros a year?* Expected: procurement manager, 5,000 to 24,999 euros, citation to the onboarding policy. Open the citation |
| `trimmed` | `screens/trimmed.jpg` | Test panel, question *What discount does Contoso aim for when it negotiates a hosting renewal?* **First as sam.demo** (sign in to Copilot Studio as him, open the same agent: he needs edit access or the agent shared with him; share the agent for edit with him in Overview > Share before this take): record the real non-answer. **Then as labadmin**: expected 12 percent |
| `eval` | `screens/evaluation.jpg` | Agent > **Evaluation** > New evaluation > Single responses > Import > `out/eval/vendor-desk-testset.csv`. Review the 11 test cases (9 from the documents, 2 out of scope: the capital of Australia, vacation days). Test methods: General quality and Compare meaning. Run as labadmin. Show the results, keep real scores. Optional second take: `vendor-desk-restricted.csv` run as sam.demo (expected: no answer) |

Optional extra take (not in the script): the agent with *Use general knowledge* on, asked the capital of Australia, to
show it answering from the model instead of the documents (turn it off again).

Masking: tenant name and org URL in every address bar and in the knowledge URL; email domains in the account menu;
the PnP app id; never show a password prompt.

## Tear-down
1. Delete the agent in Copilot Studio (Agents > ... > Delete) and its evaluation test sets (deleted with the agent).
2. `./scripts/New-VendorKnowledgeSite.ps1 -TenantUrl ... -ClientId ... -OwnerUpn ... -Remove` (deletes the site, skips
   the recycle bin).
3. Delete the Entra app registration "MGLab PnP" in the Entra admin center.
4. Remove `out/` (generated documents) and the browser profile sign-ins you do not need.
