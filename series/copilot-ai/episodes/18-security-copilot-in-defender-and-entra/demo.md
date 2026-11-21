# Demo shot list - Copilot & AI #18 Security Copilot in Defender and Entra

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab is not used. The offline part runs on the recording laptop |
| Tenant | **Needs tenant.** The lab Microsoft 365 tenant with the Defender portal (security.microsoft.com), the Entra admin center and the Security Copilot portal (securitycopilot.microsoft.com). Sign-in data for `EntraIdSignInEvents` needs Microsoft Entra ID P2 (Learn, table reference) |
| Accounts | `alex.demo` as a **Security Administrator** (activates the agents, uploads the plugin) and a second member `jordan.demo` whose failed sign-ins you create. Credentials are never written in this repo |
| Capacity | **NEEDS SECURITY COPILOT CAPACITY, not free.** Two ways, pick one: (a) the tenant has Microsoft 365 E5 or E7: capacity is auto-provisioned, 400 SCUs a month per 1,000 licences, no hourly bill (Learn). (b) Otherwise provision **1 SCU, overage 0**: **US$4 per SCU per hour, billed per started hour** (Microsoft Security Copilot pricing page, 2026-11-21). A two-hour recording session is about US$8 and a forgotten day is US$96, so **delete the capacity right after recording**. Overage costs US$6 per SCU if you allow it: do not |
| Licences for the agents | **Conditional Access Optimization Agent:** Microsoft Entra ID P1 (US$7 per user per month, paid yearly, on the Microsoft Entra pricing page, 2026-11-21; P2 is US$10 and is needed for the risky-user suggestions). **Phishing Triage Agent:** Microsoft Defender for Office 365 Plan 2, price not checked: read it on the Microsoft price page before you promise a number on camera. If either is not in the tenant, **skip that agent's scene** and say on camera what it needs. Nothing is bought for this episode |
| Azure | none, unless option (b): provisioning through Azure needs a subscription and resource group, so use the in-product option (*Provision capacity within Security Copilot*, Learn recommends it) |
| Recording machine | .NET 10 SDK, browser as `alex.demo`. No `az login`, no device codes |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the lab tenant |
|---|---|---|
| Manifest rules, KQL templates against the three table schemas, SCU arithmetic, pre-flight list | yes: `dotnet test SecCopilotKit.Tests -m:1` -> `Passed: 115` | uploading the two YAML files; the KQL returning rows |
| `seckit` commands | yes (`check`, `render`, `scu`, `preflight` all run) | none |
| Embedded Defender and Entra screens, agents | no | **record it** |

Open points to confirm on the tenant (each can change a scene):
1. Whether the lab tenant can add a custom plugin (Security Copilot > Plugin button > Custom > *Add plugin*; an owner can restrict who
   may upload custom plugins). If it is blocked, say so and show only the `seckit check` run.
2. Whether the agent manifest uploads (prerelease: Learn says it may change). If it is refused, record the error text and
   change the gotcha scene.
3. Which wording Security Copilot uses when it calls `GetFailedSignInsByUser`, and whether it needs the input named `upn`
   typed in the prompt.
4. How many SCUs one prompt and one agent run really use: read it from the in-product usage dashboard and replace the
   estimate in the `cost` scene.
5. Which Defender incident exists in the lab for the incident-summary screen. **Never invent an incident**: use a real one
   (a test alert from the Defender portal is fine) or skip the scene.

## Prerequisites
- Terminal dark theme, 18 pt, window 1600x900. Browser dark theme, 125 %.
- `cd series/copilot-ai/episodes/18-security-copilot-in-defender-and-entra/src` and `dotnet test SecCopilotKit.Tests -m:1` -> `Passed: 115`.
- Off camera: sign in to the three portals as `alex.demo`; create a handful of failed sign-ins for `jordan.demo`
  (wrong password in a private window, about 12 attempts, so the hourly query returns the account); make sure the lab has
  one user-reported phishing message only if the Phishing Triage Agent is in scope.

## Setup
1. **Capacity** (Security Copilot > capacity management; menu names change, follow Learn *Get started with Security Copilot* on the day): option (a) nothing to do; option (b) create capacity, 1 SCU,
   overage 0, in the region next to the tenant's data. Note the time: the clock-hour is billed.
2. **Plugin:** Security Copilot standalone: the *Plugin* button on the prompt bar (Manage plugins) > Custom > *Add plugin* > upload
   `plugin/contoso-soc-hunting.yaml`. Learn: when `Descriptor` has `Settings` you fill them after upload; this plugin has none.
3. **Agent (optional, prerelease):** upload `agent/contoso-signin-triage-agent.yaml` as an agent as described in Learn,
   *Build Security Copilot agents using YAML*. This manifest has no `Settings`, so nothing to fill in after upload.
4. **Embedded experiences:** Defender portal > Incidents > open a real incident > the Copilot tab (the summary is created when the
   page opens). Advanced hunting > Copilot pane > query assistant. Entra admin center > Protection > ID Protection > Risky users >
   a user > Summarize; Entra admin center > Sign-in logs > Copilot prompt bar.
5. **Agents (needs the licences above):** Entra admin center > Agents > Conditional Access Optimization > *Start agent* as a
   Security Administrator without a PIM-activated role (Learn). Defender portal > Incidents queue > Phishing Triage card > *Set up
   agent*, create a new agent identity (recommended), assign the role.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `check-screen` | `screens/check.jpg` | Terminal: `dotnet test SecCopilotKit.Tests -m:1` -> `Passed: 115`; `check plugin/contoso-soc-hunting.yaml` -> `0 error(s), 0 warning(s)`; then `check samples/broken-plugin.yaml` with the red lines (unquoted placeholder, `AccountUPN`, old table name, `gpt-4o`) |
| `embedded-screen` | `screens/embedded.jpg` | **Needs capacity.** Defender incident page: the Copilot tab with the real incident summary, then *Recommendations*. Then Entra: Risky users > a user > Summarize. Use whatever the tenant really produces, with names masked |
| `plugin-screen` | `screens/plugin.jpg` | **Needs capacity.** Security Copilot standalone: the plugin listed under Custom, then the prompt *Show failed sign-ins for jordan.demo@contoso.example* and the answer with the skill name in the activity trail. Then `seckit render` of the same skill in the terminal for comparison |
| `agent-screen` | `screens/agent.jpg` | **Needs capacity and a licence.** Entra: Conditional Access Optimization Agent, *Start agent*, the activity map and one suggestion (policy created in report-only mode). Do **not** apply it |

Extra take (not in the script): the in-product usage dashboard after the session; compare the SCUs used with `seckit scu provisioned --scus 1 --hours 2` (8.00 USD) and write the real figure into the cost scene.

Never fake a Copilot answer. If Security Copilot answers differently from the narration, change the narration.

Masking: tenant name and domain in every address bar, profile menu and the capacity page (subscription id if option b),
real user names in incidents, IP addresses of real sign-ins.

## Tear-down
1. **Delete the capacity** (option b): Delete it where you created it, and confirm in Azure/the portal that no
   provisioned SCU remains. The clock-hour you stop in is still billed.
2. Remove the custom plugin and the agent from the plugin list (Custom).
3. Entra: leave the Conditional Access Optimization Agent suggestions **unapplied**; delete any report-only policy the agent
   created if you applied one by mistake. Turn the agent off (Learn: that does not stop the monthly bill of a provisioned SCU).
4. Defender: remove the Phishing Triage Agent if you set it up; delete the test incident or tuning-rule change you made and
   re-enable the *Auto-Resolve* tuning rule if you disabled it.
5. Remove the `jordan.demo` test user or reset its password; sign out of all portals; delete `src/*/bin` and `src/*/obj`.
