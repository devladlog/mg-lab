# DEVLADLOG Copilot & AI #1 - The Copilot Landscape: Every Copilot, Licence and What's Free

Contoso's IT director asks: *which Copilots do we already pay for, and which ones are free?* This episode answers with
two things you can run:

- a **verified catalog** of 16 Copilot offerings (licence model, price where Microsoft or GitHub publishes one, where it
  runs, what the lab has, and which episode of the series covers it); a test fails if a price has no official source;
- a **licence audit** that reads the real `GET /subscribedSkus` response of a tenant and says whether the Microsoft 365
  Copilot add-on is held and which eligible base plans exist.

Series plan: [`../../README.md`](../../README.md) (read "Licensing reality in the lab"). Shared lab: [`../../../LAB.md`](../../../LAB.md).
Category episodes this one builds on:
[Microsoft 365 Copilot for Microsoft 365](../../../microsoft-365/episodes/08-microsoft-365-copilot-for-microsoft-365/) and
[Licensing optimization](../../../microsoft-365/episodes/09-licensing-optimization/). Next: episode 2, *Microsoft 365
Copilot Chat in a Real Tenant*.

| Path | What it is |
|---|---|
| [`src/data/copilot-catalog.yaml`](src/data/copilot-catalog.yaml) | The catalog. Prices only with `price_source`; verified 21 Nov 2026 |
| [`src/copilot_landscape/catalog.py`](src/copilot_landscape/catalog.py) | Load, validate (official domains only, vocabularies) and print the catalog |
| [`src/copilot_landscape/licence_audit.py`](src/copilot_landscape/licence_audit.py) | Parses Graph `subscribedSkus` (any casing), finds the Copilot add-on by part number or by its eight service plans, builds the verdict; `fetch_skus` calls Graph with a bearer token |
| [`src/copilot_landscape/cli.py`](src/copilot_landscape/cli.py) | `python -m copilot_landscape catalog` and `audit` |
| [`src/scripts/Export-SubscribedSkus.ps1`](src/scripts/Export-SubscribedSkus.ps1) | Real collector: Graph PowerShell `Get-MgSubscribedSku`, scope `LicenseAssignment.Read.All`, read-only |
| [`src/samples/subscribed-skus-contoso.json`](src/samples/subscribed-skus-contoso.json) | Fictional Contoso tenant (zero GUIDs) used by the tests only |
| [`tests/`](tests) | 21 pytest tests |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (15 scenes, about 775 words) and recording shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/01-the-copilot-landscape-every-copilot-licence-and-wh
python3 -m pip install -r src/requirements.txt      # PyYAML, pytest
python3 -m pytest -q                                 # 21 passed
cd src
python3 -m copilot_landscape catalog --free          # what needs no purchase
python3 -m copilot_landscape catalog --markdown      # the full table
python3 -m copilot_landscape catalog --validate      # 16 entries, 0 problem(s)
python3 -m copilot_landscape audit --skus samples/subscribed-skus-contoso.json
```

Against a real tenant (needs the tenant, read-only):

```powershell
./src/scripts/Export-SubscribedSkus.ps1 -OutFile $HOME/skus.json     # Connect-MgGraph, LicenseAssignment.Read.All
python -m copilot_landscape audit --skus $HOME/skus.json
# or, with a Graph token you obtained yourself, never written to a file:
$env:GRAPH_TOKEN = '<token>'; python -m copilot_landscape audit --graph-token-env GRAPH_TOKEN
```

Verified here: pytest 21 passed (Python 3.13); `Export-SubscribedSkus.ps1` parses with the PowerShell parser (0 errors).
Needs the tenant: running the export and the live Graph call, plus the two portal screens (see `demo.md`).

## What we learned / gotchas

- **The names changed.** Learn now says *Microsoft Copilot Chat* (formerly Microsoft 365 Copilot Chat) and describes
  three experiences: Copilot Chat (Basic), Microsoft 365 Copilot (Basic) and Microsoft 365 Copilot (Premium); Premium is
  the add-on licence. Copilot Studio was Power Virtual Agents (the SKU string is still `Power_Virtual_Agents`).
- **Basic cannot use Microsoft Graph.** Learn: Copilot Chat (Basic) answers from the web; organisational content only if
  you upload it, work with open content in Outlook/Teams, or use a pay-as-you-go agent. Graph and Work IQ grounding is
  Premium.
- **The add-on is detectable by service plans, not just by name.** The SKU carries eight Copilot service plans
  (`M365_COPILOT_APPS`, `M365_COPILOT_BUSINESS_CHAT`, ...). The audit matches both, so a renamed SKU is still found.
- **`Get-MgSubscribedSku | ConvertTo-Json` emits PascalCase**, Graph REST emits camelCase, and Windows PowerShell 5 can
  write a BOM. The loader lower-cases keys and reads `utf-8-sig`; each case has a test.
- **Security Copilot is "included" but not unlimited.** E5 and E7 get 400 SCUs per month per 1,000 licences (up to
  10,000); Learn says usage beyond that will be throttled at a future date, with pay-as-you-go at US$6 per SCU. Whether
  a *trial* E5 tenant is auto-provisioned is not documented: the catalog marks it `check-in-lab`.
- **Copilot in Power BI and Fabric does not run on trial capacities** (Learn, repeated on several pages), although the
  lab's Fabric access is a 60-day trial. Episode 7 must plan a paid F2 or a Fabric Copilot capacity and state the cost.
- **Prices are per market and move.** The US$30 figure is the en-US pricing page ("paid yearly"); the page notes that
  prices vary by currency and country. Re-check on the recording day.
- **GitHub changed its metering.** The plans page now lists monthly AI credit allowances instead of "premium requests";
  the catalog keeps only the plan prices and the 2,000-completion limit of the Free plan.

## References

Microsoft Learn
- [Microsoft Copilot overview (Basic / Premium, data protection, controls)](https://learn.microsoft.com/copilot/plan/copilot-overview)
- [License options for Microsoft Copilot](https://learn.microsoft.com/copilot/plan/copilot-license-options)
- [Microsoft Copilot requirements](https://learn.microsoft.com/copilot/plan/microsoft-copilot-requirements)
- [Compare Copilot in Microsoft 365 E3, E5 and E7](https://learn.microsoft.com/copilot/plan/compare-copilot-e3-e5-e7)
- [Copilot pay-as-you-go overview](https://learn.microsoft.com/copilot/plan/pay-as-you-go-overview) and [meters](https://learn.microsoft.com/copilot/plan/pay-as-you-go-meters)
- [Purchase and manage agents in Copilot Chat](https://learn.microsoft.com/copilot/manage/manage-agents-copilot-chat)
- [Copilot Studio licensing and billing](https://learn.microsoft.com/microsoft-copilot-studio/billing-licensing)
- [Copilot Managed Runtime licensing FAQ (US$1 = 100 Copilot Credits)](https://learn.microsoft.com/microsoft-365/admin/manage/apps/licensing-faq)
- [Security Copilot for Microsoft 365 E5 and E7 customers](https://learn.microsoft.com/copilot/security/security-copilot-inclusion)
- [Copilot in Fabric: enable and configure](https://learn.microsoft.com/fabric/fundamentals/copilot-enable-fabric), [Copilot for Power BI](https://learn.microsoft.com/power-bi/create-reports/copilot-introduction)
- [What is Azure Copilot?](https://learn.microsoft.com/azure/copilot/overview)
- [Microsoft Copilot in model-driven apps](https://learn.microsoft.com/power-apps/user/use-microsoft-365-copilot-model-driven-apps), [Sales agent](https://learn.microsoft.com/microsoft-sales-copilot/use-sales-chat)
- [GitHub Copilot in SSMS: installation](https://learn.microsoft.com/ssms/github-copilot/installation-state)
- [Product names and service plan identifiers for licensing](https://learn.microsoft.com/entra/identity/users/licensing-service-plan-reference)
- [List subscribedSkus (Microsoft Graph)](https://learn.microsoft.com/graph/api/subscribedsku-list?view=graph-rest-1.0)
- [Microsoft Copilot service plan diagnostic tool](https://learn.microsoft.com/copilot/implement/copilot-service-diagnostic-tool)

Vendor pages
- [Microsoft Copilot pricing for enterprise](https://www.microsoft.com/microsoft-365-copilot/pricing/enterprise) (read 21 Nov 2026)
- [GitHub Copilot plans](https://docs.github.com/en/copilot/get-started/plans) (read 21 Nov 2026)

No devladlog.com blog guide: this series is built from vendor documentation only.
