# Demo shot list — DEVLADLOG Deep Dive #2, Enterprise AI copilot

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | none |
| Tenant | Power Platform environment **`DEV`** (custom connector, Copilot Studio agent `HR Policy Copilot`). **SharePoint**: lab site `/sites/hr-lab` with libraries *Policies* and *Managers* (created in setup, deleted in tear-down). **Entra**: groups `HR Copilot - Employees`, `HR Copilot - Managers`; app registrations `HR Copilot API`, `HR Copilot Connector`, `HR Copilot Indexer` (all created in setup, deleted in tear-down) |
| Lab users | **`alex.demo` (Alex Demo)**: employee (Employees group). **`sam.demo` (Sam Demo)**: manager (both groups; maker access to `DEV` to test in Copilot Studio). `labadmin` (the recording account): admin consent, SharePoint site owner, maker, Owner on the subscription |
| Azure | Resource group **`rg-mglab-deep-dive-02`** in **Sweden Central** (Azure OpenAI), deployed by `infra/main.bicep`: Azure AI Search **Basic** (per hour while it exists, roughly €0.10/hour), Azure OpenAI with gpt-5.4-mini 2026-03-17 (Data Zone Standard, 20k TPM) and text-embedding-3-small (Standard) — a few hundred thousand tokens, under €1; Function App on Flex Consumption (cents). Deploy right before recording; tear-down deletes the group and purges the Cognitive Services accounts |
| Licences / trials | Custom connectors are premium: **Power Apps Premium** (in the lab) for the makers/users. **Copilot Studio**: not in the shared lab list; start a Copilot Studio trial for `labadmin` (maker) and, if Sam tests in the published agent, for `sam.demo` |
| Recording machine | The Windows lab laptop: browser (Copilot Studio, maker portal, Entra) with `pipeline/mask.js`, separate browser profiles for Alex and Sam; WSL (Ubuntu) bash with Azure CLI, Functions Core Tools v4, Python 3.11+, Bicep CLI |

Code and test scenes in `script.yaml` are real (from this folder). The three `screen` scenes need the lab.
**Status: needs tenant** for everything on screen. Offline: 73 pytest tests, `bicep build`/`lint` pass.

## Prerequisites
- **Azure** lab subscription, Owner (or Contributor + User Access Administrator) on the resource group.
- **Model availability:** check on Learn (*Foundry Models sold by Azure → model availability*) that
  `gpt-5.4-mini` `2026-03-17` is offered as **Data Zone Standard** in the region of `main.bicepparam` (Sweden
  Central) and that you have 20k TPM quota; `text-embedding-3-small` v1 as **Standard** there. Otherwise change
  region or `chatSku` and note it in README.
- **Microsoft 365 lab tenant:** lab users **Alex Demo** (`alex.demo`, employee) and **Sam Demo** (`sam.demo`, manager), a SharePoint site
  `/sites/hr-lab`, the Power Platform environment `DEV`.
- **Licences:** custom connectors are a premium feature (Power Apps/Power Automate premium or a trial); Copilot Studio
  licence or trial for the maker, and for Sam if he tests in the published agent.
- **Cost:** Azure AI Search **Basic** bills per hour while it exists; Azure OpenAI tokens (a few hundred thousand for
  ingestion + questions); Flex Consumption per execution. Check the pricing pages, deploy right before recording,
  delete right after.
- **Local:** Azure CLI, Functions Core Tools v4, Python 3.11+, Bicep CLI.

## Setup (off camera)

1. **Groups.** In Entra, create security groups `HR Copilot - Employees` (Alex, Sam) and `HR Copilot - Managers`
   (Sam). Copy `indexer/libraries.json` to `indexer/libraries.local.json` (don't commit it) and put the two real
   object IDs in it.
2. **API app registration** `HR Copilot API`: *Expose an API* → App ID URI `api://<client id>`, scope
   `user_impersonation`. *Token configuration* → *Add groups claim* → **Groups assigned to the application**, access
   token: Group ID. In *Enterprise applications* → the same app → *Users and groups*, assign both groups.
   (This keeps the claim small and avoids the 200-group overage.)
3. **Connector app registration** `HR Copilot Connector`: client secret; *API permissions* → My APIs →
   `HR Copilot API` → delegated `user_impersonation` → grant admin consent. Redirect URI comes in step 8.
4. **Ingestion identity** `HR Copilot Indexer` (app registration with a client secret): Graph **application**
   permission `Sites.Selected`, admin consent. As an admin, grant it `read` on the site:
   `POST https://graph.microsoft.com/v1.0/sites/{site-id}/permissions` with
   `{"roles":["read"],"grantedToIdentities":[{"application":{"id":"<indexer client id>","displayName":"HR Copilot Indexer"}}]}`
   (Graph Explorer as admin, or PnP `Grant-PnPAzureADAppSitePermission`).
5. **SharePoint.** In `/sites/hr-lab` create libraries **Policies** (upload `leave-policy.md`, `travel-policy.md`,
   `it-faq.md` and any small `handbook.docx`) and **Managers** (upload `salary-bands.md`). On *Managers*, stop
   inheriting permissions and grant only `HR Copilot - Managers`, so SharePoint and the index agree.
6. **Azure**
   ```bash
   az login                                                     # labadmin, off camera
   az group create -n rg-mglab-deep-dive-02 -l swedencentral
   az deployment group create -g rg-mglab-deep-dive-02 -f infra/main.bicep -p infra/main.bicepparam \
      -p apiClientId=<HR Copilot API client id> \
         ingestPrincipalId=$(az ad sp show --id <indexer client id> --query id -o tsv) ingestPrincipalType=ServicePrincipal \
      --query properties.outputs -o json > /tmp/copilot-outputs.json          # don't show on camera
   cd src && func azure functionapp publish <functionAppName> && cd ..
   ```
7. **Index and ingest** (as the indexer identity; `DefaultAzureCredential` picks up the environment variables):
   ```bash
   export AZURE_TENANT_ID=... AZURE_CLIENT_ID=<indexer client id>; read -rs AZURE_CLIENT_SECRET; export AZURE_CLIENT_SECRET
   export SEARCH_ENDPOINT=... SEARCH_INDEX=hr-policies OPENAI_ENDPOINT=...    # from /tmp/copilot-outputs.json
   python indexer/cli.py create-index
   python indexer/cli.py ingest --config indexer/libraries.local.json        # <- record this (ingest-run)
   ```
   Role assignments can take a few minutes; a 403 from Search or Azure OpenAI right after deployment usually means
   wait and retry.
8. **Custom connector** (Power Apps → Custom connectors → *Import an OpenAPI file* →
   `connector/apiDefinition.swagger.json`): General → Host = the function host name. Security → **OAuth 2.0**,
   identity provider **Microsoft Entra ID**, client ID/secret of `HR Copilot Connector`, Resource URL
   `api://<HR Copilot API client id>`. Save, copy the **Redirect URL** into the connector app registration (Web
   platform). Test tab → new connection as Alex → `AskHrPolicies` with `{"question":"Can I carry over leave days?"}`
   must return 200 with a citation. A 401 means the audience or issuer doesn't match the Easy Auth settings; a 403
   with the overage message means step 2's group setting is missing.
9. **Copilot Studio** agent `HR Policy Copilot`: authentication *Authenticate with Microsoft*; Tools → **Add a tool**
   → **New tool** → **Custom connector** → `AskHrPolicies`, credentials: **user authentication** (the default).
   Instructions: *"For any HR policy question use the Ask the HR policies tool. Quote its answer and list the
   citation titles with links. Never answer HR questions from general knowledge."* To test as Sam, sign in to Copilot
   Studio as Sam (give him maker access to the environment) or publish to the demo website / Teams and chat as Sam.
10. **Injection check (off camera, for the README):** as Alex ask *"How do I reset my password?"* and record whether
   the answer stays on the password topic despite the planted line in `it-faq.md`. Write the real outcome in README.

## Screens to capture (1920×1080, terminal font ≥ 16 pt)

| Scene id | File | What must be on screen |
|---|---|---|
| `ingest-run` | `screens/ingest-run.jpg` | Terminal: `python indexer/cli.py ingest …` output — `index Policies/leave-policy.md: 3 chunks -> groups …`, `skip  Policies/handbook.docx (not text)`, `index Managers/salary-bands.md …`, and the final counts dict. Group IDs masked. |
| `employee` | `screens/employee.jpg` | Copilot Studio *Test your agent* signed in as **Alex Demo**: (1) "Can I carry over leave days?" → answer with a citation to the leave policy; (2) "What's the salary range for band M2?" → *I couldn't find this in the documents you have access to.* |
| `manager` | `screens/manager.jpg` | Same agent signed in as **Sam Demo**: "What's the salary range for band M2?" → 66,000 to 82,000 EUR with a citation to *Contoso salary bands 2027*. |

If the agent paraphrases instead of returning the tool's wording, keep it if the facts and the citation are right,
and adjust the narration to what is on screen.

## Masking
- `pipeline/mask.js` before each browser capture. Mask: tenant name and domain, user principal names (keep the
  display names Alex Demo / Sam Demo), environment name and ID, function host name in the connector, subscription,
  resource and group object IDs (the ingestion log prints group IDs).
- Never show client secrets, `/tmp/copilot-outputs.json`, the connector's Security tab with the secret field, or the
  `func` publish output.

## Tear-down
```bash
az group delete -n rg-mglab-deep-dive-02 --yes --no-wait
```
Then delete the custom connector and its connections, the Copilot Studio agent, the three app registrations, the two
groups (or keep them for other episodes), the *Policies* and *Managers* libraries, and `indexer/libraries.local.json`.
Azure OpenAI and Cognitive Services accounts are soft-deleted: purge them in the portal if you need the names again.
