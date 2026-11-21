# DEVLADLOG Dynamics 365 #3 — Dynamics 365 Customization

We customize the **Project Request** table from [episode 1](../01-dataverse-deep-dive/) the way a team can
maintain it: every change in the unmanaged solution `MGLabDataverse`, the lightest tool for each job, and the
code parts built, tested and deployed by a script you can run twice.

| Need | Tool | Where |
|---|---|---|
| A *Business Justification* column | column definition (Web API) | `custkit deploy` |
| Layout: Request Code, Customer Account, Budget, Due Date, Justification on the main form | form designer, no code | demo.md |
| Budget ≥ 50,000 → justification required, and the **server** refuses a save without one | business rule (scope *Entity*), no code | demo.md |
| Warn when the customer account already has open requests | form script (needs *other* records) | `formscript/` |
| Lock Request Code (the episode 1 alternate key) once the record exists | form script (needs the form type) | `formscript/` |
| A public view *Open requests over 50,000* | view (`savedquery`, Web API) | `custkit deploy` |

The script is TypeScript compiled to **one classic script file**; the tests run that exact file (not the source) in a
Node VM with a fake form context, and check that the handler name the form will call really exists in it.

| Path | What it is |
|---|---|
| [`customization.json`](customization.json) | Single source of truth: solution, table, column, web resource name, form + OnLoad handler, view. Read by Python **and** Node |
| [`formscript/src/ProjectRequestForm.ts`](formscript/src/ProjectRequestForm.ts) | `MGL.ProjectRequest.onLoad`: locks Request Code on update, attaches the account OnChange, queries open requests with `Xrm.WebApi.retrieveMultipleRecords`, shows/clears a form notification, never throws |
| [`formscript/test/`](formscript/test/) | 13 `node --test` tests against the compiled `dist/mgl_projectrequest_form.js` |
| [`src/custkit/formxml.py`](src/custkit/formxml.py) | Adds a form library + OnLoad handler to `systemforms.formxml` idempotently (stable GUIDs), fixes a handler without *pass execution context*, removes it again, lists fields the rule/script need that aren't on the form |
| [`src/custkit/components.py`](src/custkit/components.py) | Memo column payload, web resource payload (type 3, Base64, name checks), view fetchxml + layoutxml (with a check that every grid column is fetched), PublishXml parameter |
| [`src/custkit/deploy.py`](src/custkit/deploy.py) | `deploy` (create-or-update each component with `MSCRM.SolutionUniqueName`, publish only when something changed), `remove`, `probe-rule` |
| [`src/custkit/webapi.py`](src/custkit/webapi.py), [`auth.py`](src/custkit/auth.py) | Web API client (429 + Retry-After, update-only PATCH with `If-Match: *`), MSAL token provider (same as episode 1) |
| [`tests/`](tests/) | 35 pytest tests; the Web API is a recording stub that checks what we send ([`tests/fixtures/main_form.xml`](tests/fixtures/main_form.xml) is a hand-written form XML) |

## Run and test (no tenant)

```bash
cd series/dynamics-365/episodes/03-dynamics-365-customization
(cd formscript && npm ci --no-audit --no-fund && npm test)   # tsc build + node --test: 13 passed
python3 -m pip install --user -r requirements.txt
python3 -m pytest -q tests                                     # 35 passed
cd src && python3 -m custkit render                            # writes ../out/: view XML + patched sample form
```
`render` prints `form: ! no control for mgl_justification`: the sample form doesn't have the column yet, which is
exactly the warning `deploy` gives you before a business rule silently doesn't fire.

## Against an environment (needs tenant)

Prerequisites: episode 1 provisioned (`mgl_projectrequest` in `MGLabDataverse`), Customer Account and the other
columns added to the main form *Information* in the form designer.

```bash
export DATAVERSE_URL=https://<org>.crm4.dynamics.com          # + AZURE_* for an app user, or interactive sign-in
(cd formscript && npm test)                                     # builds dist/ — deploy uploads that file
cd src
python3 -m custkit deploy           # column, web resource, form handler, view, publish; exit 1 if a field is missing
python3 -m custkit deploy           # second run: "0 created, 0 updated, 4 unchanged", nothing published
python3 -m custkit probe-rule       # after the business rule is active: does the SERVER refuse a big budget without justification?
python3 -m custkit remove           # tear-down (keeps the column, it holds data)
```
The identity needs System Customizer (or System Administrator) in the environment.

## What we learned / gotchas

- **"Set Business Required" in a business rule doesn't protect the server.** With scope *Entity* a rule runs on
  forms *and* on the server, but only *set/clear value*, *set default* and *show error message* run there;
  requirement level, show/hide and lock are form-only. So the rule pairs a form action (required) with a *show
  error message* action (server). That should also stop an API import like episode 1's for big budgets without a
  justification; `probe-rule` checks it against the real environment, and the video shows whatever it answers.
- **A business rule doesn't fire on a form that doesn't contain every column it uses**, and a script only sees
  columns on the form (or declared as web resource dependencies). `deploy` lists missing fields and exits 1.
- **Business rules run before the OnLoad script** and don't react to values the OnLoad script sets. Changing a rule
  doesn't re-run it on existing records.
- **Rules that need other records or the form type are script territory.** Business rules see the current record only.
- **The layoutxml `object` attribute is the table's ObjectTypeCode**, and for custom tables that number differs
  between environments. Learn's view example hard-codes `3` because that's Opportunity; `deploy` reads it from
  `EntityDefinitions(...)?$select=ObjectTypeCode` every time.
- **Publishing:** a *new* web resource doesn't need publishing, an *updated* one does; the form and the view are
  published with their table (`<entities><entity>mgl_projectrequest</entity></entities>`). `deploy` publishes only
  when it changed something.
- **`MSCRM.SolutionUniqueName`** puts each create/update in our solution. If it names a *managed* solution the value
  is silently ignored (no error), so check the solution after the first deploy.
- **One OnLoad handler, everything else from code.** The form XML references only `MGL.ProjectRequest.onLoad`; OnChange
  is attached with `addOnChange`. A test resolves that dotted name against the compiled file, which catches the
  classic "function not found" after a rename. `deploy` also turns *pass execution context* on if it's off.
- **FormXml schema details matter when you edit it:** `<formLibraries>` needs at least one `<Library>` (max 50) and
  `<events>` at least one `<event>`. Our first `remove` left an empty `<events>` behind; a test caught it.
- **`Xrm.WebApi` OData options must be URL-encoded**, and lookups give GUIDs that can come wrapped in braces: the
  script strips braces before filtering on `_mgl_customeraccountid_value`.
- Test-harness gotcha: arrays created inside a Node `vm` context fail `assert.deepStrictEqual` against normal arrays
  (different realm prototypes); the tests spread them first.
- Up to **150 business rules per table** before performance degrades (Learn); that count includes the server-side ones.

## References
- [Create a business rule for a table](https://learn.microsoft.com/power-apps/maker/data-platform/data-platform-create-business-rule) (scope, form-only actions, field must be on the form, FAQ, 150 rules)
- [Customize views in model-driven apps](https://learn.microsoft.com/power-apps/developer/model-driven-apps/customize-entity-views) (`savedquery`, querytype 0, `MSCRM.SolutionUniqueName`)
- [EntityMetadata.ObjectTypeCode](https://learn.microsoft.com/dotnet/api/microsoft.xrm.sdk.metadata.entitymetadata.objecttypecode) (varies for custom tables between organizations)
- [Use optional parameters — associate a solution component with a solution](https://learn.microsoft.com/power-apps/developer/data-platform/optional-parameters#associate-a-solution-component-with-a-solution)
- [Web resource table](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/webresource) and [Web resources in model-driven apps](https://learn.microsoft.com/power-apps/developer/model-driven-apps/web-resources) (type 3 = Script)
- [Sample: Import files as web resources](https://learn.microsoft.com/power-apps/developer/model-driven-apps/sample-import-files-web-resources) (publish on update, not on create)
- [Web resource dependencies](https://learn.microsoft.com/power-apps/developer/model-driven-apps/web-resource-dependencies)
- [Form XML schema](https://learn.microsoft.com/power-apps/developer/model-driven-apps/form-xml-schema) (`formLibraries`, `events`, `Handler` attributes)
- [Form context for internal handlers is missing](https://learn.microsoft.com/troubleshoot/dynamics-365/field-service/scheduling/missing-form-context-bookable-resource) (PATCH `systemforms.formxml` + PublishXml; `passExecutionContext`)
- [Create and update column definitions using the Web API](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/create-update-column-definitions-using-web-api) (memo column)
- Client API: [getFormType](https://learn.microsoft.com/power-apps/developer/model-driven-apps/clientapi/reference/formcontext-ui/getformtype), [setFormNotification](https://learn.microsoft.com/power-apps/developer/model-driven-apps/clientapi/reference/formcontext-ui/setformnotification), [retrieveMultipleRecords](https://learn.microsoft.com/power-apps/developer/model-driven-apps/clientapi/reference/xrm-webapi/retrievemultiplerecords)
- Blog: [Dynamics 365 Customization — Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-11-03-dynamics-365-customization-complete-guide-2025/)
