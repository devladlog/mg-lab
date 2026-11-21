# Demo shot list — DEVLADLOG Dynamics 365 #11: Dynamics 365 Administration

Already run in the build container: `python3 -m pytest -q tests` (28 passed, Web API stubbed) and the three offline runs on
the fictional samples; `pac admin list`, `list-roles` and `self-elevate` usage lines checked with `pac` 2.16.1.
**Nothing has run against Dataverse yet: all four `screen` scenes need the lab tenant.** The only name that must be
confirmed live is the `$expand` of the role relationships (step 4).

## Lab environment

No VMs, no Azure resources: cloud tenant only, browser (admin center, app) plus a terminal on the recording laptop.

| Item | Notes | Cost |
|---|---|---|
| Dynamics 365 **Sales trial** environment (EMEA, created 21 Nov 2026, 30-day trial, ends ~21 Dec 2026) | **Why this one:** the episode is about *Dynamics 365* administration, so the environment should have Dynamics 365 apps (Sales Hub) and their application users and roles; `DEV` is Dataverse-only. It is a trial-type environment, which is also what the backup gotcha needs. Record **before the trial ends**. Mask the org URL | none (trial) |
| Environment `DEV` | Shown in the environments list for contrast (check its type in the admin center and say it). Not changed | none |
| `labadmin` | Global Administrator and System Administrator in the Sales trial environment (the recording account; confirm in step 2) | none |
| `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo` | Lab users, only appear in the Members list of the role. For the A002 demo `riley.demo` is disabled in step 3 (and re-enabled in tear-down) | none |
| Recording laptop | Python 3.10+, `pip install --user -r requirements.txt`, `pac` signed in (`pac auth create`, recorder signs in, no credentials in any file), dark terminal font 18+, browser with `pipeline/mask.js` | none |

## Setup (before recording)

1. `export DATAVERSE_URL=https://<sales trial>.crm4.dynamics.com`, `cd src`. Sign in when the tool asks (interactive MSAL,
   as `labadmin`).
2. Admin center → Manage → Environments → *Sales trial* → Settings → Users + permissions → Security roles → **System
   Administrator** → Members: note who is in it. `labadmin` must be there; if not, `pac admin self-elevate --environment <id>`
   (Learn: tenant admins are not given the role automatically) and say so in the narration of the admins scene.
3. To give A001/A002 something real to find without touching anyone's real access: assign **System Administrator** to
   `alex.demo`, `sam.demo` and `jordan.demo` (that is four people with `labadmin`, over the team limit of 3), and disable
   `riley.demo` *after* also assigning the role to her (user record in the environment's Users list → Disable; whether
   that flips `isdisabled` for her is **not verified**: check the `admins` output). **Note what actually works and fix
   this step.** If disabling isn't practical, skip A002 on screen and say the sample shows it.
4. `python3 -m adminkit admins`. **Verify and note in README** ("Not verified on Learn"): the query is accepted, the
   response has `systemuserroles_association` and `teamroles_association` on the role, and the table matches the Members
   list. If the expand is refused, fix `admins.query` and the tests from the real error text. Also run
   `python3 -m adminkit settings` and `python3 -m adminkit jobs` once to see they work.
5. Write down the current audit values (`settings` prints them) so tear-down can restore them.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/admin-environments.jpg` — "The environments we run" (needs tenant)
Admin center → Manage → Environments: the list (Sales trial, DEV; type, state, region). Then open *Sales trial* and show
Details and the Settings page with **Audit and logs**. Mask tenant, org URL, user.

### 2. `screens/adminkit-settings.jpg` — "Before and after" (needs tenant)
```bash
python3 -m adminkit settings
python3 -m adminkit audit-on --days 365            # dry run
python3 -m adminkit audit-on --days 365 --apply    # before / after lines
python3 -m adminkit settings
```
Then admin center → environment → Settings → Audit and logs → **Audit settings**: auditing on, retention. Real output only;
the first `settings` will say whatever the environment really has (the trial may already have auditing on: if so,
use `audit-on --days -1` or another value so there is a visible change, and say that).

### 3. `screens/adminkit-jobs.jpg` — "System jobs, from code and from the app" (needs tenant)
```bash
python3 -m adminkit jobs
python3 -m adminkit jobs --from-json ../sample/system-jobs.json --now 2027-01-15T12:00:00Z   # only if the lab has nothing failed; label it "sample"
```
Then in the app: Advanced settings → System Jobs, view filtered to **Failed**, open one job to show the message. If there
are no failed jobs in the last 7 days, show the empty `jobs` output and the empty view honestly.

### 4. `screens/adminkit-admins.jpg` — "The admin list, and the admin center" (needs tenant)
```bash
python3 -m adminkit admins
```
Then admin center → Security roles → System Administrator → Members, side by side. Show the exit code (`echo $?` gives 1
when over the limit). Mask UPNs and app ids; lab users and Microsoft application users only.

## Masking checklist
- Org URL, tenant name, user UPNs, avatars and any GUID that could be real (user and role ids are system-generated, but blur
  them anyway); never the owner's own account. Application user names such as `# CDSUserManagement` are Microsoft's and may show.
- Only lab users (`labadmin`, `alex.demo`, ...) and Microsoft application users on screen.

## Tear-down
1. Restore the audit values written down in step 5 (`python3 -m adminkit audit-on --days <old> --apply` only restores
   retention and leaves auditing on; if auditing was off before, switch it off in admin center → Settings → Audit and logs → Audit
   settings). Table/column auditing was never changed.
2. Remove **System Administrator** from `alex.demo`, `sam.demo`, `jordan.demo` and `riley.demo` (admin center → Security
   roles → System Administrator → Members → Remove). Re-enable `riley.demo` if she was disabled.
3. Nothing else was created: no backups (trial environments don't support them), no app registrations, no Azure resources.
