# DEVLADLOG Dynamics 365 #9 — Power Apps Portal Integration

Power Apps portals are now **Power Pages**. The scenario continues from [episode 8](../08-dynamics-365-customer-service/):
store managers at *Contoso Retail* get a support page that lists and creates **cases** in Dataverse through the portal
Web API. The design studio builds the site; what this episode adds is what the studio doesn't review for you:

- **pagekit** (Python), reads a site downloaded with `pac pages download` (YAML files) and lints the Web API
  configuration: site settings, table permissions, web roles
- **site-js/support-api.js**, the page script: token handling (`__RequestVerificationToken`), a case list with explicit
  `$select`, case creation with a contact bind and the `entityid` header, and error parsing; tested with Node's own
  test runner

| Path | What it is |
|---|---|
| [`src/pagekit/siteconfig.py`](src/pagekit/siteconfig.py) | Reads `site-settings/`, `table-permissions/`, `web-roles/` from a downloaded site. Every field name that isn't on Learn is in one `FIELDS` dict |
| [`src/pagekit/lint.py`](src/pagekit/lint.py) | Rules P001-P013 (wildcard, missing columns, no table permission, global scope, anonymous write, unsupported configuration tables, EntitySetName in a setting, drift from `portal.json`) |
| [`src/pagekit/columns.py`](src/pagekit/columns.py) | F001: each enabled table's `fields` against the real columns (`EntityDefinitions(...)/Attributes`) |
| [`src/pagekit/cli.py`](src/pagekit/cli.py), [`webapi.py`](src/pagekit/webapi.py), [`auth.py`](src/pagekit/auth.py) | `inspect`, `lint`, `columns`; Web API client and MSAL token provider as in episodes 1-8 |
| [`portal.json`](portal.json) | The tables and columns the support pages need (the expectation `lint --expect` compares with) |
| [`site-js/support-api.js`](site-js/support-api.js) | `listCases`, `createCase`, `safeFetch`, runs in a Power Pages page and in Node |
| [`sample/site/`](sample/site/), [`sample/bad-site/`](sample/bad-site/) | Fictional downloaded-site folders for the offline run: a clean one and one with eleven deliberate errors |
| [`tests/`](tests/), [`site-js/test/`](site-js/test/) | 15 pytest tests, 7 Node tests; the Web API and `fetch` are test doubles (tests only: the demo runs against the real site) |

## Run and test (no tenant)

```bash
cd series/dynamics-365/episodes/09-power-apps-portal-integration
python3 -m pip install --user -r requirements.txt
python3 -m pytest -q tests                      # 15 passed
(cd site-js && npm test)                        # 7 passed (node --test, no dependencies)
cd src
python3 -m pagekit lint ../sample/site --expect                # exit 0: 0 error(s), 0 warning(s)
python3 -m pagekit lint ../sample/bad-site --expect            # exit 1: 11 error(s), 6 warning(s)
```
```
ERROR   P002  Webapi/incident: fields contains '*': Learn says the wildcard is deprecated and requests fail until explicit column names are configured
ERROR   P005  Cases for everyone: Global scope for the Anonymous Users role with create/write on a Web API table: public write access
ERROR   P003  Webapi/adx_webpage: configuration table: the portals Web API does not support it
...
11 error(s), 6 warning(s), 0 note(s)
```

## Against the lab site (needs tenant)

Prerequisites: [demo.md](demo.md) (Power Pages trial site in the *Sales trial* environment, Power Platform CLI signed in).

```bash
pac auth create --environment <env url>
pac pages list -v
pac pages download --path ./site-download --webSiteId <site id> --modelVersion <1 or 2 from the list>
export DATAVERSE_URL=https://<org>.crm4.dynamics.com
cd src
python3 -m pagekit inspect ../site-download/<site folder>
python3 -m pagekit lint ../site-download/<site folder> --expect
python3 -m pagekit columns ../site-download/<site folder>
```
`support-api.js` goes into a web file or the page's JavaScript on the site (steps in demo.md).

## What we learned / gotchas

- **The Web API is for your own pages.** Learn (*Portals Web API overview*): "built for creating a rich user experience
  inside portal pages. It isn't optimized for third-party services or application integration." Actions and functions
  aren't supported; configuration tables (`adx_webpage`, `adx_sitesetting`, ... a list of 48) can't be used,
  rule P003 carries that list. A Power Pages licence is required (anonymous calls count against anonymous capacity).
- **Two settings per table, logical name.** `Webapi/<table>/enabled` (default False) and `Webapi/<table>/fields`;
  the code uses the **EntitySetName** (`/_api/incidents`). P008 flags `Webapi/incidents/...`.
- **The `*` in `fields` is deprecated** and requests fail until explicit names are set; `UseFieldsFromView` with a public
  system view named *Power Pages Web API Columns* is the alternative (site version 9.8.8.x or later, up to 5 minutes for
  view changes). With neither, the `fields` setting is missing and the table is unusable (P001).
- **Table permissions rule everything.** The Web API follows them through web roles, as lists and forms do (Learn,
  *Power Pages security*). Learn's best-practice page: avoid Global access for sensitive tables, especially when
  exposed through the Web API; treat anonymous table permissions as public data access. P005/P006 encode that.
- **CSRF token on every call.** Learn: "All Web API calls must include a Cross-Site Request Forgery (CSRF) token"; its
  `safeAjax` sample gets it from `shell.getTokenDeferred()` and sends it as `__RequestVerificationToken`; the create
  sample reads the new id from the `entityid` response header. `support-api.js` does the same with `fetch`.
- **Operations are case-sensitive**, and `$select` should always be explicit (Learn: without properties an error is
  returned unless the legacy wildcard is configured). Lookups come back as `_<column>_value`.
- **Site lifecycle.** A site starts as a trial site; in a trial environment it expires after 30 days or with the
  environment, whichever is earlier; in a production or sandbox environment after 90 days. Seven days after suspension the
  site host is deleted (Learn, *Power Pages lifecycle*). The lab's *Sales trial* environment ends about 21 Dec 2026.
- **Private by default.** All sites are private, only makers and users they grant access to can open them, and the
  sign-in is Microsoft Entra, which comes preconfigured (Learn, *Site visibility*, *Plan your Power Pages project*).
- **Not verified on Learn, so the tool inspects instead of assuming:** the YAML field names of table permissions and web
  roles in a download (`adx_entitylogicalname`, `adx_scope` and its numeric access-type values, privilege flags such as
  `adx_read`, `adx_entitypermission_webrole`), and the exact relationship/navigation name for the case's customer
  contact (`customerid_contact@odata.bind` in `createCase`). Only `adx_name` / `adx_value` for site settings appear on
  Learn (the deployment-profile example). `pagekit inspect` on the real download ([demo.md](demo.md) step 5) shows what
  was read; if it differs, `FIELDS` in `siteconfig.py` and the sample files are fixed from the real output.

## References
- [Portals Web API overview](https://learn.microsoft.com/power-pages/configure/web-api-overview) (route, site settings, wildcard deprecation, UseFieldsFromView, unsupported tables, CSRF, EntitySetName)
- [Use portals Web API write, update, and delete operations](https://learn.microsoft.com/power-pages/configure/write-update-delete-operations) (safeAjax, create, `entityid` header, `@odata.bind`)
- [Query data using portals Web API](https://learn.microsoft.com/power-pages/configure/read-operations) (`$select`, `$filter`, `$apply`, FetchXML, `_x_value` lookups)
- [Configuring table permissions](https://learn.microsoft.com/power-pages/security/table-permissions) and [Power Pages security](https://learn.microsoft.com/power-pages/security/power-pages-security)
- [Apply security best practices to your Power Pages site](https://learn.microsoft.com/power-pages/security/security-best-practices)
- [Microsoft Power Platform CLI support for Power Pages](https://learn.microsoft.com/power-pages/configure/power-platform-cli) and [pac pages](https://learn.microsoft.com/power-platform/developer/cli/reference/pages) (download, list, `--modelVersion`, YAML and HTML)
- [Power Pages lifecycle](https://learn.microsoft.com/power-pages/admin/lifecycle), [Power Pages trial FAQ](https://learn.microsoft.com/power-pages/getting-started/trial-faq), [Site visibility](https://learn.microsoft.com/power-pages/security/site-visibility)
- Blog: [Power Apps Portal Integration — Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-19-power-apps-portal-integration-complete-guide-2025/)
