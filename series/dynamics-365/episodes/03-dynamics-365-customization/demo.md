# Demo shot list — DEVLADLOG Dynamics 365 #3: Dynamics 365 Customization

Already run in the build container: `npm test` in `formscript/` (tsc build + 13 `node --test` tests against the
compiled web resource) and `python3 -m pytest -q tests` (35 tests, Web API stubbed), plus `custkit render`.
**Nothing has run against Dataverse yet: all five `screen` scenes need the lab tenant**, and the `deploy` and
`probe-rule` narration must be checked against what really appears.

## Lab environment

No VMs and no Azure resources. Everything is in the cloud tenant, recorded from the browser and a terminal on the
recording laptop.

| Item | Notes | Cost |
|---|---|---|
| Power Platform environment `DEV` (Dataverse, exists) | Dynamics 365 apps not required: custom table only | none |
| Episode 1 done in `DEV` | `mgl_projectrequest` in solution `MGLabDataverse` (publisher prefix `mgl`), 18 records imported | none |
| A few fictional accounts | e.g. "Contoso Ltd" and "Fabrikam (sample)"; set Customer Account on 3+ requests so one account has several open requests (PR-0004, PR-0011, PR-0013 → Contoso Ltd) | none |
| A model-driven app with the Project Request table | The one used in episode 2, or create "Project Requests" in the solution (New → App → Model-driven app, add the table) | none |
| Identity | Your lab user with **System Customizer** in `DEV` (not a Global Administrator), or an app registration + application user with System Customizer | none |
| Node 22 + npm, Python 3.10+ with `pip install --user -r requirements.txt` | On the recording laptop | none |
| Browser with `pipeline/mask.js` | Maker portal and app shots | none |

## Setup (before recording)

1. `cd formscript && npm ci --no-audit --no-fund && npm test` → `# pass 13`. This builds `dist/mgl_projectrequest_form.js`.
2. `export DATAVERSE_URL=https://<lab-env>.crm4.dynamics.com` (plus `AZURE_*` if using the app user). Terminal: dark,
   font 18+, short prompt, don't echo the URL.
3. **Rehearsal deploy, then tear down** (`python3 -m custkit remove`), so the recorded run is a real first run. The
   column stays after `remove`; that's fine, the recorded run then shows `= column mgl_justification exists`
   (update the deploy narration) — or record the very first run without rehearsing.
4. **Form layout (recorded as screen 1):** make.powerapps.com → Solutions → MGLabDataverse → Tables → Project Request
   → Forms → *Information* (main). Add Request Code, Customer Account, Budget, Due Date, Priority and Business
   Justification to the first section. Save and publish. *Business Justification only exists after the first
   `deploy`*; if you deploy before arranging the form, `deploy` exits 1 with
   `! form Information has no control for mgl_justification` — that's expected; add it and run `deploy` again.
5. **Business rule (recorded as screen 2):** Project Request → Business rules → New business rule:
   - Name *Justification for large budgets*, **Scope: Entity**.
   - Condition *Budget ≥ 50000* (Budget, Is greater than or equal to, Value, 50000).
   - True: **Set Business Required** → Business Justification = Business Required; then a nested condition
     *Business Justification does not contain data* → **Show Error Message** on Business Justification:
     "Budgets of 50,000 or more need a business justification."
   - False: **Set Business Required** → Business Justification = Not Business Required.
   - Validate, Save, close, then **Activate** it from the solution's business rule list (the designer can't activate).
6. Run `python3 -m custkit deploy` once if the form step needs it, then make sure the record PR-0004 has
   Budget 75,000, Customer Account = Contoso Ltd and an empty justification for the app shot.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/form-designer.jpg` — "Layout in the form designer" (**needs tenant**)
Form designer on *Information*: the section with Name, Request Code, Customer Account, Budget, Due Date, Priority,
Business Justification visible; the tree view or the Events tab can be open. Mask tenant/environment in the header.

### 2. `screens/business-rule.jpg` — "Budget over fifty thousand needs a reason" (**needs tenant**)
Business rule designer with the whole rule visible: Scope = **Entity** at the top right, the condition, the Set
Business Required action on the true branch, the nested Show Error Message, and Not Business Required on the false
branch. Use the zoom/mini-map so it all fits.

### 3. `screens/deploy.jpg` — "Deploy, then deploy again" (**needs tenant**)
```bash
cd src
python3 -m custkit deploy
python3 -m custkit deploy
```
Expected first run: `+ column ...` (or `= column ... exists`), `+ web resource mgl_/projectrequest/form.js (N bytes)`,
`~ form Information: added library ...`, `~ form Information: added OnLoad handler MGL.ProjectRequest.onLoad`,
`+ view 'Open requests over 50,000'`, `published`, `N created, 1 updated, 0 unchanged, 0 warning(s)`.
Second run: four `=` lines, `nothing to publish`.
**Verify and note in README if different:**
- that `PATCH systemforms(<id>)` with `formxml` is accepted and the handler shows on the form's **Events** tab
  (form designer → Events → On Load: `mgl_/projectrequest/form.js`, `MGL.ProjectRequest.onLoad`, *Pass execution
  context* checked);
- that the event element name `onload` is what the designer itself writes (open the form XML via a solution export
  if in doubt);
- that the view shows in the table's Views list and in the app's view selector with the six columns;
- that all four components are listed in the MGLabDataverse solution (Objects).

### 4. `screens/app-form.jpg` — "On the real form" (**needs tenant**)
Open PR-0004 in the model-driven app (hard refresh first, so the new script loads). In one frame: the yellow form
notification "Contoso Ltd already has N open requests: PR-…" (real codes), **Request Code greyed out**, Budget
75,000, Business Justification with the required asterisk (and the rule's error message under it while it's empty). Optional B-roll: change Customer Account to an account
with no other requests → the warning disappears; set Budget to 40,000 → the asterisk goes away.
Also check a **new** record: Request Code editable.

### 5. `screens/probe-rule.jpg` — "Does the server say no?" (**needs tenant**)
```bash
python3 -m custkit probe-rule
echo "exit=$?"
```
Expected: `server refused: HTTP 400: Budgets of 50,000 or more need a business justification.` and `exit=0`.
**Record whatever happens.** If it prints `server accepted the record ...` (exit 3), the probe deletes its record;
keep that result in the video, rewrite the `probe` and `gotcha` narration, and add it to README "What we learned".
Note: once the rule is active, episode 1's `python -m dvlab import` should also fail for PR-0002/PR-0004 (budget
≥ 50,000, no justification) — worth one line in README after checking it.

## Masking checklist
- Environment URL and org name (terminal and address bar), tenant name, user UPN/avatar in the maker portal and app.
- Only fictional accounts and the episode 1 sample data on screen.
- Never show tokens, `AZURE_CLIENT_SECRET` or `env` output.

## Tear-down
1. `python3 -m custkit remove` — unregisters the handler, deletes the view, publishes, deletes the web resource.
2. Deactivate and delete the business rule *Justification for large budgets* (episode 1's import works again).
3. Remove Business Justification from the form, publish, then delete the column in the solution if it's no longer
   wanted (deleting a column deletes its data). Episode 4 uses it in a BPF stage: **keep it if episode 4 is next**.
4. Remove the Customer Account values from the sample records only if other episodes don't need them.
