# DEVLADLOG Azure #6 — Cost Optimization: price it before you deploy, catch what's left running

Episodes 1–5 deployed the contoso workloads. This episode puts a price on them at the three moments where it matters:

- **Before deploying: price the what-if.** `costwatch estimate` reads the JSON of
  `az deployment group what-if`, where SKUs, instance counts and regions are already resolved per environment
  (the compiled template still has expressions), and prices the **always-on** resources with the public
  **Azure Retail Prices API** (no sign-in). Exit code 1 when the month is over budget, so episode 3's plan stage can
  stop a deployment; exit code 2 when a price can't be found unambiguously, because **zero rows is not zero euros**
- **While running: a budget per workload tag.** Subscription-scope `Microsoft.Consumption/budgets` in Bicep, filtered
  on the `workload` tag that episode 2's policy requires, with Actual 50 %, Actual 90 % and Forecasted 100 % alerts
- **After: hunt the leftovers.** `costwatch waste` runs Resource Graph queries (based on the FinOps best-practice
  queries on Microsoft Learn) for unattached disks, unattached static public IPs, App Service plans with no apps and
  VMs stopped but not deallocated, puts a monthly price on each, and lists untagged resources and Azure Advisor's cost
  recommendations

```
 az deployment group what-if --no-pretty-print -o json ─► costwatch estimate ─► Retail Prices API (EUR, list prices)
                                                           │ table + Markdown summary
                                                           └─ exit 0 within budget · 1 over budget · 2 can't price
 Cost Management budget (subscription, tag workload in [...]) ─► e-mail at 50 % / 90 % actual, 100 % forecast
 az graph query (queries/*.kql) ─► costwatch waste ─► priced leftovers + untagged + Advisor
```

| Path | What it is |
|---|---|
| [`src/costwatch/prices.py`](src/costwatch/prices.py) | Retail Prices API client: OData filter (always `priceType eq 'Consumption'`), `api-version=2023-01-01-preview`, `NextPageLink` paging, 429 handling (plain-text body, `x-ms-ratelimit-retailprices-retry-after`), JSON cache, exactly-one-row rule, hourly → monthly at 730 h |
| [`src/costwatch/rules.py`](src/costwatch/rules.py) | Resource → meter: App Service plans (Linux vs Windows product, `P1 v3` spelling, capacity), private endpoints (region `Global`), Standard static public IPs, Standard HDD disks (size → S4…S80). Everything else: "not estimated", with the reason |
| [`src/costwatch/estimate.py`](src/costwatch/estimate.py) | What-if parsing (CLI shape and REST shape; Create/Modify/NoChange priced, Delete not), Markdown report |
| [`src/costwatch/waste.py`](src/costwatch/waste.py) | `az graph query` with skip-token paging, row → resource, pricing, the empty-disk rule |
| [`src/costwatch/__main__.py`](src/costwatch/__main__.py) | CLI: `estimate`, `waste`; `##vso[task.logissue]` line when over budget |
| [`queries/*.kql`](queries) | Resource Graph: unattached disks, unattached public IPs, empty App Service plans, stopped-not-deallocated VMs, untagged by type, Advisor cost savings |
| [`infra/budget.bicep`](infra/budget.bicep) + [`.bicepparam`](infra/budget.bicepparam) | Subscription budget, tag filter, 3 notifications, start date = first day of the current month |
| [`infra/waste-demo.bicep`](infra/waste-demo.bicep) | Deliberate leftovers: untagged static public IP, empty B1 plan |
| [`infra/estimate-ep2.sh`](infra/estimate-ep2.sh) | Real what-if of episode 2's lab and prod profiles against an empty group, then `costwatch estimate` |
| [`infra/deploy-budget.sh`](infra/deploy-budget.sh) / [`deploy-waste-demo.sh`](infra/deploy-waste-demo.sh) / [`teardown.sh`](infra/teardown.sh) | Budget (what-if + create); leftovers incl. two disks via `az disk create`; delete groups (budget only with `--with-budget`) |
| [`tests/`](tests) | 51 pytest tests; `fixtures/retail-prices-cache.json` = real API answers, `fakes/az` = fake Azure CLI for Resource Graph |

## Run it here (no Azure)

```bash
python3 -m pytest tests -q       # 51 passed
#   test_prices 10 · test_rules 15 · test_estimate 9 · test_waste 6 · test_infra 11

# Price episode 2's two profiles from the what-if fixtures, with live list prices (public API, no sign-in)
PYTHONPATH=src python3 -m costwatch --cache /tmp/prices.json estimate tests/fixtures/whatif-ep2-lab.json --budget 25    # 24.90 EUR, exit 0
PYTHONPATH=src python3 -m costwatch --cache /tmp/prices.json estimate tests/fixtures/whatif-ep2-prod.json --budget 25   # 246.40 EUR, exit 1

cd infra && bicep lint budget.bicep && bicep lint waste-demo.bicep && bicep build-params budget.bicepparam --stdout > /dev/null
```

Verified in this container (Python 3.13, pytest 9.1.1, Bicep CLI 0.49.2): 51 passed; Bicep lint/build clean; both
estimates above ran **against the live Retail Prices API** on 21 Nov 2026 (Sweden Central, EUR): lab
**24.90 EUR/month** (B1 Linux 11.80 + 2 × private endpoint 6.55), prod **246.40 EUR/month** (P1 v3 Linux × 2 = 233.30
+ 13.10). Those answers are the test fixture (`tests/fixtures/retail-prices-cache.json`); the tests fail if they try
to reach the API. `infra/estimate-ep2.sh` was dry-run with a stand-in `az` that prints the two fixtures (exit 1,
prod over budget, files kept in `~/.contoso-cost`). Mutation check: disabling the empty-disk rule makes exactly the two tests that rely on it fail.

**Not run here:** anything that needs a subscription: the real what-if (`estimate-ep2.sh`), the budget deployment,
Resource Graph queries, the waste demo. The what-if fixtures are **hand-written** to the documented what-if result
schema, modelled on episode 2's resources (like episode 3's fixtures); the recorder runs the real what-if, and the
real JSON should replace them. The fake `az` returns `{"count", "data", "skip_token", "total_records"}`; the parser
also accepts `skipToken` / `$skipToken`.

## Use it in episode 3's pipeline (not run here)

In the plan stage, after the what-if step writes `$(Agent.TempDirectory)/whatif.json`:

```bash
PYTHONPATH=series/azure/episodes/06-cost-optimization/src python3 -m costwatch \
  estimate "$(Agent.TempDirectory)/whatif.json" --budget 300 --summary "$(Agent.TempDirectory)/cost.md"
echo "##vso[task.uploadsummary]$(Agent.TempDirectory)/cost.md"
```

## Demo (needs a subscription)

```bash
az login
infra/estimate-ep2.sh rg-contoso-whatif swedencentral 25           # what-if creates nothing; prod exits 1
BUDGET_EMAIL=you@example.com infra/deploy-budget.sh
infra/deploy-waste-demo.sh rg-contoso-waste swedencentral
PYTHONPATH=src python3 -m costwatch waste --subscriptions <subscription-id>
infra/teardown.sh rg-contoso-waste rg-contoso-whatif               # add --with-budget to remove the budget too
```

## What we learned / gotchas

- **Zero rows is not zero euros.** The first price query filtered on `armSkuName eq 'B1'` and got `Count: 0`.
  `armSkuName` is empty for App Service B1 (but filled for P1 v3). An estimator that sums whatever comes back would
  have said 0.00. `costwatch` demands exactly one row per question and exits 2 otherwise. (Hit while building.)
- **`skuName` alone isn't one price.** `skuName eq 'B1'` returns the Linux product (`B1`, 0.0162/h) and the Windows
  product (`B1 App`, 0.0673/h), plus DevTest rows. Filter on `productName` (`… Plan - Linux`) and
  `priceType eq 'Consumption'`. (`priceType` is the documented filter name; the response field is called `type`.)
- **A reservation row says "1 Hour" but the price is for the whole term.** Learn's sample shows a 1-year reservation
  at 25,007 with `unitOfMeasure: "1 Hour"`; we saw P1 v3 Linux reservation rows at 912 and 1,888 EUR with the same unit.
  Another reason to pin `priceType`.
- **Private endpoints are priced in `armRegionName eq 'Global'`.** Asking for `swedencentral` returns nothing.
- **The API rate-limits, with a plain-text 429.** We got "Too many requests at this point. Please retry after some
  time." (not JSON) and `x-ms-ratelimit-retailprices-retry-after: 60`; the remaining-requests header started at 9.
  The client waits and retries, and caches answers to a file. (Observed; the limit isn't documented on the API page.)
- **Not every price is hourly or monthly.** Private DNS zones come back with unit `1` and two tiers (first 25 zones,
  then cheaper). Disk operations are per `10K`. Such items are listed as "not estimated", never guessed; the CLI
  refuses units it doesn't understand.
- **An empty disk that was never used costs nothing.** Learn: storage for an empty managed disk isn't allocated (or
  billed) until first use. The unattached-disk query can't tell; `costwatch` prices `createOption: Empty` disks with no
  ownership change as 0.00, and the demo shows one next to a billed disk created from an image.
- **Budgets warn, they don't stop spending.** Learn: resources aren't affected and consumption isn't stopped; cost data
  is typically 8–24 hours late and budgets are evaluated every 24 hours; notifications usually within an hour after
  that; up to five thresholds and five e-mails. The start date must be the first of a month (Bicep default:
  `utcNow('yyyy-MM-01')`). *Not verified:* whether redeploying in a later month (new start date) updates the budget
  in place; the demo deploys it once.
- **Tags aren't retroactive.** Cost Management applies a tag only to usage after it was applied, resource group tags
  aren't inherited by resources' usage unless tag inheritance is enabled (EA, MCA and MPA billing accounts only).
- **Retail ≠ your bill.** The calculator's unit prices come from the same API, but they are list prices; agreements,
  credits and reservations change the real numbers. The report says so on every run.

## References
- Blog: [Cost Optimization — Complete Guide](https://www.devladlog.com/articles/azure/2026-01-26-cost-optimization-complete-guide-2026/)
- [Azure Retail Prices REST API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices) (filters incl. `priceType`, 1,000 rows per page and `NextPageLink`, case-sensitive values from 2023-01-01-preview, reservation rows with `reservationTerm`)
- [Estimate costs with the Azure pricing calculator](https://learn.microsoft.com/azure/cost-management-billing/costs/pricing-calculator) (730 hours default; prices from the Retail Prices API)
- [Tutorial: Create and manage budgets](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets) and [Quickstart: create a budget with Bicep](https://learn.microsoft.com/azure/cost-management-billing/costs/quick-create-budget-bicep)
- [Manage costs with automation](https://learn.microsoft.com/azure/cost-management-billing/costs/manage-automation) (evaluated once per day)
- [Understand Cost Management data: tags](https://learn.microsoft.com/azure/cost-management-billing/costs/understand-cost-mgt-data#how-tags-are-used-in-cost-and-usage-data) and [tag inheritance](https://learn.microsoft.com/azure/cost-management-billing/costs/enable-tag-inheritance)
- FinOps best practices: [Storage](https://learn.microsoft.com/cloud-computing/finops/best-practices/storage), [Networking](https://learn.microsoft.com/cloud-computing/finops/best-practices/networking), [Compute](https://learn.microsoft.com/cloud-computing/finops/best-practices/compute), [Web](https://learn.microsoft.com/cloud-computing/finops/best-practices/web) (the Resource Graph queries)
- [Get Advisor recommendations in Azure Resource Graph](https://learn.microsoft.com/azure/advisor/advisor-azure-resource-graph) and [Resource Graph samples for Advisor](https://learn.microsoft.com/azure/advisor/resource-graph-samples)
- [Working with large Azure resource data sets](https://learn.microsoft.com/azure/governance/resource-graph/concepts/work-with-data) (1,000 rows, skip token, `id` needed) and [`az graph query`](https://learn.microsoft.com/cli/azure/graph)
- [Azure managed disk types](https://learn.microsoft.com/azure/virtual-machines/disks-types) (Standard HDD sizes, billing rounds up to the tier) and [Understand Azure Disk Storage billing](https://learn.microsoft.com/azure/virtual-machines/disks-understand-billing#empty-managed-disk-billing) (empty disks)
- [Deploy Bicep with the Azure CLI](https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-what-if) (what-if) and [`az disk create`](https://learn.microsoft.com/cli/azure/disk#az-disk-create) (`--image-reference` URN)
