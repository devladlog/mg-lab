# Demo shot list — DEVLADLOG Dynamics 365 #9: Power Apps Portal Integration

Already run in the build container: `python3 -m pytest -q tests` (15 passed, Web API stubbed), `npm test` in `site-js`
(7 passed, `fetch` and `shell` doubled) and `pagekit lint` on the two fictional sample sites. **Nothing has run against
a Power Pages site yet: all five `screen` scenes need the lab tenant**, and the YAML field names `pagekit` reads must be
confirmed from a real download first (step 5).

## Lab environment

No VMs, no Azure resources: cloud tenant only, browser plus a terminal on the recording laptop.

| Item | Notes | Cost |
|---|---|---|
| Dynamics 365 **Sales trial** environment (EMEA, created 21 Nov 2026, 30-day trial, ends ~21 Dec 2026) | **Why this one and not `DEV`:** the demo creates *cases* and shows them in Customer Service Hub with the SLA from episode 8, and Contoso Retail lives here; Dynamics 365 apps can't be installed in the Dataverse-only `DEV`. A Power Pages site can be created in an existing environment if the maker has the privileges (Learn, *Power Pages trial FAQ*). Learn (*Power Pages lifecycle*): a trial site in a trial environment expires after 30 days or when the environment does, so **record before the environment ends**. Mask the org URL | none (trial) |
| Power Pages **trial site** `Contoso Retail store support` | Created from make.powerpages.microsoft.com in the Sales trial environment (*Create a site*, a template with a plain page is enough). Sites are private by default and sign in with Microsoft Entra | none (trial site) |
| `labadmin` | System Administrator; builds the site, runs the terminal | none |
| `alex.demo` | Signs in to the private site as the "store manager" (Entra); needs access to the private site (step 2) | none |
| Recording laptop | Python 3.10+, Node 22, Power Platform CLI (`pac`), browser with `pipeline/mask.js` | none |
| Licensing | Learn (*Portals Web API overview*): Web API operations need a Power Pages licence. A trial site covers the recording; nothing is converted to production | none |

## Setup (before recording)

1. As `labadmin` open `https://make.powerpages.microsoft.com`, pick the *Sales trial* environment, **Create a site**
   (trial), name **Contoso Retail store support**. Wait for provisioning. Note the site's data model:
   `pac pages list -v` (step 4) prints Standard or Enhanced.
2. Share the private site with `alex.demo` (design studio → Security → *Site visibility* → private, add users; Learn,
   *Site visibility*). Open the site as `alex.demo` once: Entra sign-in creates the contact record for the user.
3. Web role and permissions (design studio → Security, Learn *Configuring table permissions*): create the web role
   **Store managers** (*Manage roles* opens the Portal Management app) and add it to `alex.demo`'s contact (Portal
   Management → Contacts → Related → Web Roles). Then table permissions:
   - **Store manager cases**: table *Case*, access type **Contact**, pick the relationship that links the case to the
     contact, privileges **Read** and **Create** (add Append and Append To if the designer asks for them for the contact
     lookup), role Store managers
   - **Own contact**: table *Contact*, access type **Self**, Read, role Store managers
   Write the exact labels you clicked in the README if they differ. Note that the case customer for a portal-created
   case must be the signed-in contact: that is why `createCase` binds `customerid_contact`; if the relationship name
   differs, change it in `support-api.js` and its test.
4. Site settings (Portal Management app → Site Settings, or design studio): `Webapi/incident/enabled` = `true`,
   `Webapi/incident/fields` = `title,description,prioritycode,createdon,statecode,ticketnumber`,
   `Webapi/contact/enabled` = `true`, `Webapi/contact/fields` = `firstname,lastname,emailaddress1`. Settings can take a
   few minutes to take effect (restart the site in the admin center to see them at once).
5. Download and inspect the site:
   ```bash
   pac auth create --environment <sales trial url>
   pac pages list -v
   pac pages download --path ./site-download --webSiteId <id> --modelVersion <1 or 2>
   export DATAVERSE_URL=https://<sales trial>.crm4.dynamics.com
   cd src && python3 -m pagekit inspect ../site-download/<site folder>
   ```
   **Verify and note in README** ("Not verified on Learn"): the four site settings appear as read; table permissions show
   table, scope and privileges; web roles show their names. If something shows `0 table permission(s)` the YAML field
   names differ: open one `*.tablepermission.yml` and fix `FIELDS` / `SCOPES` and the sample files, then re-run `pytest`.
6. Page: in the design studio add a page **Support** with a Code component / HTML section containing a list area
   (`<ul id="cases">`), a title input and a button. Paste `site-js/support-api.js` into the page's JavaScript (or
   upload it as a web file and reference it) and a few lines that call `mgSupport.listCases({top: 10})` and
   `mgSupport.createCase({title, contactId, priority: 1})`. The contact id of the signed-in user is available through
   Liquid (`{{ user.id }}`) on the page. Sync and browse as `alex.demo`.
7. `python3 -m pagekit columns ../site-download/<site folder>` should print `0 error(s)`.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/pages-site.jpg` — "The support site" (needs tenant)
Design studio, Pages workspace, the Support page selected, site name visible. Mask tenant, org and site URL.

### 2. `screens/pagekit-lint.jpg` — "Review before release" (needs tenant)
```bash
python3 -m pagekit inspect ../site-download/<site folder>
python3 -m pagekit lint ../site-download/<site folder> --expect          # clean: exit 0
```
For the failing example: edit `Webapi/incident/fields` in the downloaded file to `*` (a real edit of the local copy,
not uploaded), run `lint --expect` (exit 1, P002), restore it, run again. Keep the real output. Blur ids.

### 3. `screens/pages-table-permissions.jpg` — "Table permissions decide" (needs tenant)
Design studio → Security → Table permissions: *Store manager cases* (Case, Contact access, Read + Create, role Store
managers) and *Own contact* (Self). Mask tenant and site URL.

### 4. `screens/pages-api-call.jpg` — "The page, calling the API" (needs tenant)
Browser as `alex.demo` on the Support page: the case list from `listCases`, create **Till offline in store 12**
(High) with `createCase`; developer tools Network tab: the `POST /_api/incidents` request with the token header
(**hide the value**) and the `entityid` response header. Mask site URL.

### 5. `screens/hub-portal-case.jpg` — "The case in Customer Service Hub" (needs tenant)
Customer Service Hub as `labadmin`: the case created from the portal with customer = Alex Demo's contact, SLA timers
visible if the default SLA from episode 8 is still set (otherwise show the case without them and say so). Mask tenant
and avatar.

## Masking checklist
- Org URL, site URL (`*.powerappsportals.com`), tenant name, UPNs, avatars, site and record GUIDs.
- The `__RequestVerificationToken` value in the Network tab.
- Only the fictional account (Contoso Retail), `[MGL demo]`/portal demo cases and lab users on screen.

## Tear-down
1. Delete the demo cases created from the portal (and the contact record created for `alex.demo` if no later episode needs it).
2. Delete the table permissions, the **Store managers** web role and the four `Webapi/...` site settings.
3. Delete the trial site (Power Platform admin center → Power Pages sites → delete) and `./site-download`, which holds
   real ids.
4. If episode 8's SLA is no longer needed, tear it down as described there.
