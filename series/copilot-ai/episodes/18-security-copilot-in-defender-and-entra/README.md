# DEVLADLOG Copilot & AI #18 - Security Copilot in Defender and Entra

Microsoft Security Copilot shows up in three places: inside the **Defender** and **Entra** portals (embedded), in its own
**standalone** portal, and as **agents** that run on their own. All of it is paid for in **Security Compute Units (SCUs)**.
This episode builds the part you can own as code, and checks it offline:

1. a **custom plugin** (YAML) with KQL skills that run in Defender advanced hunting, and a GPT skill;
2. a **sign-in triage agent** manifest (Learn marks agent manifests as prerelease) that runs every hour;
3. `seckit`, a .NET tool that checks those manifests against Microsoft Learn's rules, **parses every KQL template with the
   Kusto.Language parser against the real advanced hunting columns**, prices SCUs, and runs a pre-flight list for the
   Conditional Access Optimization Agent and the Phishing Triage Agent.

The Contoso story continues: Alex Demo is on the Contoso SOC. A user reports an invoice phishing mail from the made-up
domain `fabrikam-invoices.example`, and the same hour `alex.demo@contoso.example` shows a burst of failed sign-ins.
Nothing here touches a real tenant. Everything that needs Security Copilot capacity is in [`demo.md`](demo.md).

Series plan: [`../../README.md`](../../README.md). Shared lab: [`../../../LAB.md`](../../../LAB.md). Previous:
[episode 17, extending Microsoft 365 Copilot](../17-extending-microsoft-365-copilot-declarative-agents/) (same pattern:
manifest, description, validate before upload). Licensing background:
[episode 1, the Copilot landscape](../01-the-copilot-landscape-every-copilot-licence-and-wh/). Category episodes this builds on:
[Microsoft Defender for 365](../../../microsoft-365/episodes/06-microsoft-defender-for-365/),
[Entra ID governance](../../../microsoft-365/episodes/04-entra-id-governance-identity/). Next: episode 19, *Copilot governance:
Purview DSPM for AI and admin controls*.

## What each Security Copilot piece is (Learn, checked 2026-11-21)

| Piece | What it does | Needs |
|---|---|---|
| Embedded in Defender | Incident summary (created when you open an incident, up to 100 correlated alerts), guided response (triage, containment, investigation, remediation), script analysis, incident report, advanced hunting query assistant (natural language to KQL) | Security Copilot capacity; unified RBAC permissions decide which action buttons are enabled |
| Embedded in Entra | Risky user summary, sign-in log questions, app risk, incident investigation | Security Copilot capacity; at least Security Reader to investigate |
| Conditional Access Optimization Agent | Scans new users and apps from the last 24 hours, finds Conditional Access gaps, suggests (or creates in report-only mode) policies | Entra ID P1, SCUs (under one per run on average), Security Administrator to activate. Risky-user and risky-sign-in suggestions need Entra ID P2 |
| Phishing Triage Agent | Classifies user-reported phishing as a threat or false alarm with a written reason and a decision map. **Learn now says it is the same agent as the Security Alert Triage Agent**, extended (preview) to a subset of identity and cloud alerts | Defender for Office 365 Plan 2, URBAC for Defender for Office 365, *Monitor reported messages in Outlook* on, alert policy *Email reported by user as malware or phish* on, the auto-resolve tuning rule off |
| Custom plugin and agent (this episode) | Your own KQL, GPT and API skills; an agent with a trigger | Security Copilot access; the right to add custom plugins (admin setting) |

**Cost (US dollars, can change).** Provisioned SCU 4 per hour (billed per started hour, 1 to 100 SCUs); overage 6 per SCU
(0 to 999, billed on exact use); Microsoft 365 E5 and E7: 400 SCUs a month per 1,000 licences, capped at 10,000, no hourly
billing (Learn, *Security Copilot for E5 and E7 included customers*; Microsoft pricing page). Learn says usage above the
inclusion will be throttled "at a future date", with scaling at 6 per SCU offered then. `seckit scu` does the arithmetic.

## Names that changed

| Old | Current |
|---|---|
| Microsoft Copilot for Security | **Microsoft Security Copilot** |
| `AADSignInEventsBeta` (advanced hunting) | **`EntraIdSignInEvents`**, replaced on 19 October 2026; Learn says old queries are migrated automatically. `seckit` warns on the old name |
| Azure Active Directory | **Microsoft Entra ID** |
| Phishing Triage Agent | Same agent as **Security Alert Triage Agent**, now covering more alert types (preview) |
| Plugin (Security Copilot) | Learn now says **tool** for a skill and **agent manifest** for the file; the YAML keys (`Skills`, `SkillGroups`) did not change |

## What is in this folder

| Path | What it is |
|---|---|
| [`plugin/contoso-soc-hunting.yaml`](plugin/contoso-soc-hunting.yaml) | Custom plugin: `GetFailedSignInsByUser`, `GetEmailFromSenderDomain`, `GetHighAlertsByKeyword` (KQL, target Defender) and `SummarizeSignInFailures` (GPT) |
| [`agent/contoso-signin-triage-agent.yaml`](agent/contoso-signin-triage-agent.yaml) | Agent manifest: a KQL fetch skill, an AGENT entry skill with child skills, an hourly trigger |
| [`samples/broken-plugin.yaml`](samples/broken-plugin.yaml) | A plugin with planted mistakes; `seckit check` must report them all |
| [`samples/tenant-profile.*.json`](samples) | Two fictional tenant profiles for the pre-flight check (one ready, one not) |
| [`src/SecCopilotKit/`](src/SecCopilotKit) | The library: `ManifestChecker`, `KqlChecker`, `HuntingSchema`, `TemplateRenderer`, `ScuEstimator`, `Preflight` |
| [`src/SecCopilotKit.Cli/`](src/SecCopilotKit.Cli) | `seckit`: `check`, `render`, `scu`, `preflight` |
| [`src/SecCopilotKit.Tests/`](src/SecCopilotKit.Tests) | 115 xUnit tests |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (about 800 words) and shot list with `## Lab environment` |

## Run and test

```bash
cd series/copilot-ai/episodes/18-security-copilot-in-defender-and-entra
cd src
dotnet test SecCopilotKit.Tests -m:1       # Passed: 115 (restores Microsoft.Azure.Kusto.Language 12.4.1 and YamlDotNet 18.1.0 from nuget.org)
cd ..
dotnet run --project src/SecCopilotKit.Cli -- check plugin/contoso-soc-hunting.yaml        # 0 error(s), 0 warning(s)
dotnet run --project src/SecCopilotKit.Cli -- check samples/broken-plugin.yaml             # 8 error(s), 7 warning(s), exit 1
dotnet run --project src/SecCopilotKit.Cli -- render plugin/contoso-soc-hunting.yaml GetEmailFromSenderDomain "domain=fabrikam-invoices.example"
dotnet run --project src/SecCopilotKit.Cli -- scu provisioned --scus 1 --hours 730      # 2920.00 USD
dotnet run --project src/SecCopilotKit.Cli -- scu inclusion --licences 4000 --used 1700 # 1600 included, 100 beyond
dotnet run --project src/SecCopilotKit.Cli -- preflight phishing-triage samples/tenant-profile.contoso-lab.json   # exit 1: 2 items to fix
```

After a run delete `src/*/bin`, `src/*/obj`; they are not committed.

## What the checks do

- **Manifest rules from Learn (Agent manifest, KQL plugins):** `Descriptor` and `SkillGroups` required; descriptor name has no
  whitespace and none of `/ , \ ? # @`; skill names have no whitespace or period and are unique; `Format` is one of API, GPT,
  AGENT, KQL, LogicApp; KQL `Target` is Defender, Sentinel, SentinelDataLake, LogAnalytics or Kusto, `Template` or
  `TemplateUrl` but not both, up to 80,000 characters; Kusto needs `Cluster` and `Database`, Sentinel its four ids; GPT
  `ModelName` must be `gpt-4.1`; API needs `SupportedAuthTypes`; agent definitions need Publisher, Product,
  RequiredSkillsets and at least one trigger with a `ProcessSkill`.
- **Input and placeholder agreement:** a `{{name}}` with no `Inputs` entry is an error; an input never used is a warning.
- **KQL with a real parser:** each template is parsed with Kusto.Language and analysed against the columns of `EmailEvents`,
  `EntraIdSignInEvents` and `AlertInfo` (copied from the Learn schema pages). A misspelt column (`AccountUPN`) is an error,
  because KQL column names are case-sensitive. Warnings for unbounded results and a missing time filter.
- **Placeholders stay inside string literals.** Learn does not document how Security Copilot escapes input values, so the
  kit assumes none: `where AccountUpn =~ '{{upn}}'` is accepted, `where AccountUpn == {{upn}}` is an error. The tests show the
  reason: an unescaped value like `x' or 1==1 | where 'a'=='a` adds operators to the query, and the escaped one stays one
  string literal. `seckit render` escapes, for local testing only.
- **Agent trigger wiring:** Learn says the trigger calls `ProcessSkill` with the values of each object `FetchSkill` returns.
  The kit reads the result columns of the fetch query and reports a required `ProcessSkill` input that no column provides.
- **Costs and pre-flight:** `ScuEstimator` reproduces Learn's worked examples (400 licences give 160 SCUs, 4,000 give 1,600,
  5 provisioned SCUs for two hours bill 10 SCU-hours). `Preflight` lists the Learn prerequisites of the two agents against a
  JSON profile you fill in by hand; settings you did not answer are reported **unknown**, not met.

## Gotchas (all from Learn)

1. **One SCU is the minimum, and it is billed every hour** even when you use nothing; turning off the Conditional Access
   Optimization Agent does not stop that billing. Make provisioning changes at the start of the hour.
2. **Provisioned SCUs do not roll over** within the hour, and inclusion SCUs reset monthly and do not roll over.
3. **The Conditional Access Optimization Agent needs a Security Administrator to activate it**, cannot be paused once started (Learn's walkthrough also advises against an account whose role is activated through PIM), and reviews up to 300 users and 150
   applications per run.
4. **The Phishing Triage Agent ignores alerts resolved by alert tuning**: switch off the built-in *Auto-Resolve - Email
   reported by user as malware or phish* rule or it sees nothing.
5. **Agent identity:** both agents can run under a Microsoft Entra Agent ID rather than a user account. A user account used
   as an agent identity cannot use PIM or a Temporary Access Pass.
6. **Query tables move:** `AADSignInEventsBeta` became `EntraIdSignInEvents`, and `EntraIdSignInEvents` needs an Entra ID P2
   licence to collect and view the data (Learn, table reference).
7. **GPT skills accept `gpt-4.1` only**, and a skill that returns a lot of rows spends the SCUs of the model that reads
   them: bound every query.

## Verified here and not

Verified in the build container (Linux, .NET 8 runtime, SDK 10): `dotnet test SecCopilotKit.Tests -m:1` gives **115 passed**
(build with 0 warnings); the CLI commands above ran; the plugin and agent manifests pass the checker; the planted mistakes
are all reported. The Learn rules and the three table schemas were read on 2026-11-21.

**Not verified without Security Copilot capacity and a tenant:** that Security Copilot accepts these two manifests on upload
(the checker implements Learn's documented rules, not the service's own validator); that the KQL skills return rows from a
real `EntraIdSignInEvents` or `EmailEvents`; that the model chooses the skills from their descriptions; that the agent
manifest `Triggers` and `Interfaces` keys behave as documented in a prerelease feature; how the service escapes `{{input}}`
values; the SCU cost of a real run; every embedded-experience screen. Prices are from Microsoft's pages on 2026-11-21 and
the Defender for Office 365 Plan 2 price was not checked. Nothing was uploaded, signed in or created in any cloud.

## References

- [Agent manifest](https://learn.microsoft.com/copilot/security/developer/agent-manifest)
- [Build Security Copilot agents using YAML](https://learn.microsoft.com/copilot/security/developer/build-agent-manifest)
- [KQL plugins](https://learn.microsoft.com/copilot/security/plugin-kql)
- [Create your own custom plugins](https://learn.microsoft.com/copilot/security/custom-plugins)
- [Security Compute Units and capacity](https://learn.microsoft.com/copilot/security/security-compute-units-capacity)
- [Security Copilot for Microsoft 365 E5 and E7 included customers](https://learn.microsoft.com/copilot/security/security-copilot-inclusion)
- [Microsoft Security Copilot pricing](https://www.microsoft.com/security/pricing/microsoft-security-copilot)
- [Microsoft Security Copilot experiences](https://learn.microsoft.com/copilot/security/experiences-security-copilot)
- [Security Copilot in Microsoft Defender](https://learn.microsoft.com/defender-xdr/security-copilot-in-microsoft-365-defender)
- [Advanced hunting query assistant](https://learn.microsoft.com/defender-xdr/advanced-hunting-security-copilot-query-assistant)
- [Security Copilot in Microsoft Entra](https://learn.microsoft.com/entra/security-copilot/security-copilot-in-entra)
- [Conditional Access Optimization Agent](https://learn.microsoft.com/entra/security-copilot/conditional-access-agent-optimization)
- [Phishing Triage Agent](https://learn.microsoft.com/defender-xdr/phishing-triage-agent)
- [EmailEvents](https://learn.microsoft.com/defender-xdr/advanced-hunting-emailevents-table),
  [EntraIdSignInEvents](https://learn.microsoft.com/defender-xdr/advanced-hunting-entraidsigninevents-table),
  [AlertInfo](https://learn.microsoft.com/defender-xdr/advanced-hunting-alertinfo-table)
