# Demo shot list — DEVLADLOG Dynamics 365 #12: Finance & Operations

Already run in the build container: `python3 -m pytest -q tests` (17 passed, services stubbed) and the offline `customers` /
`reconcile` on the fictional samples. **Nothing has run against Finance and Operations or Dataverse yet: all four `screen`
scenes need the lab tenant, and a Finance environment that the lab does not have today.** Several response details are
listed under "Not verified on Learn" in the README and are checked in step 6.

## Lab environment

**New resource, not in `series/LAB.md` yet** (add it there when provisioned): a Dynamics 365 Finance trial environment.
Cloud tenant only, no VMs, no Azure resources. The recording machine is the lab Windows desktop (browser plus terminal).

| Item | Notes | Cost |
|---|---|---|
| Dynamics 365 **Finance trial** environment | Learn (*Unified admin trials*): the tenant admin gets the free Finance trial offer from **Marketplace** in the Microsoft 365 admin center (search *Finance*, take the free trial offer), assigns the license to the lab admin, then in the Power Platform admin center: Manage, Environments, **New**, type **Trial (subscription-based)**, region EMEA, security group, **Enable Dynamics 365 apps**, template **Finance** (Learn shows *Finance (Preview)* as the example), Save. Deployment can take about an hour. **The trial length is not stated on the Learn page: read it off the offer and write it in README before recording.** Learn warns the Finance trial doesn't support Visual Studio development: not needed. Do **not** use the older Lifecycle Services preview route: Learn (*Project Operations preview*) says that route needs an Azure subscription billed per environment, and new LCS projects for Finance are frozen since Feb 2026 | none (trial); confirm the offer shows no charge before accepting |
| Dynamics 365 **Sales trial** environment (ends ~21 Dec 2026) | Provides the Dataverse side: the account *Contoso Retail* from episode 7 (set its account number in step 4). Record **before the trial ends**. Mask the org URL | none (trial) |
| Microsoft Entra app registration `mglab-fokit` | In the lab tenant, single tenant, one client secret with the shortest useful expiry; the recorder creates it and the secret never goes into any file. Learn lists the delegated permissions for the registration (*Access Dynamics AX Custom Service*, *Access Dynamics AX data*, *Access Dynamics AX online as organization users*, under *Microsoft Dynamics ERP*): add them | none |
| `labadmin` | Recording account: admin of the Finance environment and System Administrator in the Sales trial environment | none |
| Recording laptop | Python 3.10+, `pip install --user -r requirements.txt`, dark terminal font 18+, browser with `pipeline/mask.js` | none |

**Fallback if the Finance trial can't be provisioned** (offer not visible for this tenant or region, or the environment fails
to deploy): the series plan already says to make this an architecture-only episode. Then cut the `environment`, `doctor`,
`reconcile` and `dualwrite` screens and re-script from the Learn pages and Dataverse-side screens only, and tell the owner.
No stub, mock or local server is ever shown.

## Setup (before recording)

1. Deploy the Finance trial as above and open it once as `labadmin`. Note the company ids in the company selector
   (**write the real ids in README**; the `usmf` in the README is only an example).
2. Register `mglab-fokit` in Entra ID (portal), add the secret, note the application (client) id and tenant id.
3. In Finance: **System administration > Setup > Microsoft Entra applications**, New: *Client Id* = the application id, *Name*
   = `mglab-fokit`, *User ID* = a user for the app (Learn's sample uses Admin; a dedicated service user is the better practice:
   create one if it takes five minutes, otherwise use Admin and say so on screen). Save.
4. Data, all through the apps (no code writes data in this episode):
   - Finance, company A, Accounts receivable > All customers > New: **C-1001 Contoso Retail**, **C-1002 Contoso Logistics**,
     **C-1003 Contoso Hospitality** (type Organization; the required fields per Learn are account, party type, customer group,
     sales currency and organization name: use existing groups and currency), and one **person** customer **C-2001 Alex Demo**.
   - Dataverse (Sales trial), Accounts: set **Account Number = C-1001** on *Contoso Retail*; create **Contoso Logistics Ltd**
     with **C-1002** (so R003 shows a name difference); create **Contoso Legacy Store** with **C-1099** (R002). C-1003 stays
     only in Finance (R001).
5. Terminal: `export FO_URL=https://<environment>.operations.dynamics.com`,
   `export DATAVERSE_URL=https://<sales trial>.crm4.dynamics.com`, `export AZURE_TENANT_ID=... AZURE_CLIENT_ID=...
   AZURE_CLIENT_SECRET=...` (typed in the shell, not saved anywhere), `cd src`.
6. `python3 -m fokit doctor`, then `python3 -m fokit customers`. **Verify and note in README** ("Not verified on Learn"): the call
   succeeds; the columns come back with the casing used in `fo.json` (`CustomerAccount`, `dataAreaId`, ...); `PartyType` is the
   text `Organization`/`Person`; the person customer is counted as R005. If any name or value differs, fix `fo.json`,
   `customers.py` and the tests from the real output. If the Dataverse call needs a different token (the app has no
   application user in the Sales trial environment), either create the application user there, or run `reconcile` with an
   interactive sign-in by leaving `AZURE_CLIENT_SECRET` unset for that command and note what you did.
7. `python3 -m fokit reconcile`: expect R001 (C-1003), R002 (C-1099), R003 (C-1002), R005 (person) and no R004 unless a second
   company has the same account number. Keep whatever it really prints.
8. Optional, only if it takes a few minutes and works: in Finance, Data management workspace > **Dual-write**, link to a
   Dataverse environment and apply **Customers V3 (accounts)** (Learn, *Dual-write setup*). **Not planned in the script and
   not verified in this lab.** The `dualwrite` scene just shows the page as it is.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/fo-environment.jpg` — "A real Finance environment" (needs tenant)
Power Platform admin center → Manage → Environments: the Finance trial next to the Sales trial (type, state, region). Then the
Finance environment in the browser: Accounts receivable → All customers, company selector visible, the demo customers listed.
Mask tenant, org URLs, user.

### 2. `screens/fokit-customers.jpg` — "The first real call" (needs tenant)
```bash
python3 -m fokit doctor
python3 -m fokit customers
```
Real output: the URL it calls (blur the host), the ok line with the columns, then the counts per company and the first rows.

### 3. `screens/fokit-reconcile.jpg` — "Two systems, one answer" (needs tenant)
```bash
python3 -m fokit reconcile; echo "exit $?"
```
Then Finance → All customers and the Dataverse Accounts view for one customer (for example *Contoso Retail* with C-1001 on both
sides), side by side. If the output is cleaner than planned, say so; if you fall back to the sample, label it "sample".

### 4. `screens/fo-dual-write.jpg` — "The map behind it" (needs tenant)
Finance → Data management workspace → **Dual-write**: the list of table maps; open **Customers V3 (accounts)** and show
`CustomerAccount` mapped to `accountnumber` and its status. Show whatever the environment really has: running, stopped or not linked.
If the page says the environment isn't linked yet, keep that on screen and don't re-record the narration around it.

## Masking checklist
- Org URLs for both environments, tenant name, user principal names, avatars, client id and tenant id (they are real
  identifiers), the client secret (never visible: typed into the shell before recording starts).
- Only fictional customers (Contoso Retail, Contoso Logistics, Contoso Hospitality, Alex Demo) and lab users on screen.

## Tear-down
1. Delete the three Finance customers and the person customer if Finance allows it (customers without transactions); otherwise
   they disappear with the trial environment.
2. Dataverse: clear the account number on *Contoso Retail*, delete *Contoso Logistics Ltd* and *Contoso Legacy Store* (leave
   Contoso Retail and its cases for other episodes).
3. Finance: remove the `mglab-fokit` row in Microsoft Entra applications. Entra ID: delete the secret and the app registration.
4. If dual-write was linked (step 8): unlink it and delete the maps' data in Dataverse before deleting anything else.
5. Power Platform admin center: delete the Finance trial environment; Microsoft 365 admin center: remove the Finance trial
   license/subscription so nothing renews.
