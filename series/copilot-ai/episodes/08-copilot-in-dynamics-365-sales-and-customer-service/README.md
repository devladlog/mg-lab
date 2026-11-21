# DEVLADLOG Copilot & AI #8 - Copilot in Dynamics 365 Sales and Customer Service

Contoso Bikes' sales team and service desk both ask the same thing: *Copilot writes summaries and answers from our
records, so why are some of them empty?* This episode answers it with something you can run. Copilot in Dynamics 365 only
sees what is in Dataverse, and Learn documents exactly which attributes and rules it uses. `d365_copilot_ready` reads
opportunities, accounts, cases and knowledge articles from the Dataverse Web API and reports, per record, what Copilot
will not be able to use. Then the episode shows the real Copilot on the same data (see `demo.md`).

Series plan: [`../../README.md`](../../README.md). Shared lab: [`../../../LAB.md`](../../../LAB.md).
Previous: episode 7, [*Copilot in Power BI and Fabric*](../07-copilot-in-power-bi-and-fabric/) (same idea: Copilot is
only as good as the model behind it). Next: episode 9, *Copilot in SharePoint and SharePoint Agents*.
Category episodes this builds on: [Dynamics 365 7: Sales](../../../dynamics-365/episodes/07-dynamics-365-sales/)
(`salesctl`, the opportunity pipeline), [Dynamics 365 8: Customer Service](../../../dynamics-365/episodes/08-dynamics-365-customer-service/)
(`casekit`, cases and knowledge), [Dynamics 365 1: Dataverse deep dive](../../../dynamics-365/episodes/01-dataverse-deep-dive/)
(tables and Web API), [Dynamics 365 10: Reporting and analytics](../../../dynamics-365/episodes/10-reporting-analytics/).
The service and finance side of the same Contoso Bikes story: [Power BI 1](../../../power-bi/episodes/01-data-modeling-star-schema/).

**Lab licensing reality (read first).** Copilot in Sales and in Customer Service needs a Dynamics 365 licence that
includes Copilot. The official pricing pages (read 21 Nov 2026, USD, per user per month, paid yearly) list: Sales
Professional 65 (no Copilot), Sales Enterprise 105 and Premium 150 (Copilot); Customer Service Professional 50 (no
Copilot), Enterprise 105, Premium 195. The lab has a Sales trial environment; Customer Service needs its own trial. Whether the
trial licences expose Copilot is checked on camera, never assumed. The Sales agent in Microsoft 365 Copilot needs a
Microsoft 365 Copilot licence for Microsoft Graph data (the lab has none, so that part is not recorded). Nothing in
this folder fakes a Copilot answer.

| Path | What it is |
|---|---|
| [`src/d365_copilot_ready/dataverse.py`](src/d365_copilot_ready/dataverse.py) | Read-only Dataverse Web API client, standard library only: bearer token from an environment variable, `Prefer: odata.maxpagesize`, follows `@odata.nextLink` unchanged, no `$skip`, loop guard, org URL masking |
| [`src/d365_copilot_ready/rules.py`](src/d365_copilot_ready/rules.py) | The readiness rules (table below), each tied to a Learn statement |
| [`src/d365_copilot_ready/dataset.py`](src/d365_copilot_ready/dataset.py) | Loads rows from sample files or a live org (9 entity sets, selected columns) and runs the rules |
| [`src/d365_copilot_ready/cli.py`](src/d365_copilot_ready/cli.py) | `python -m d365_copilot_ready check --sample DIR` or `--org URL`, text or JSON, `--fail-on` |
| [`src/data/sample/`](src/data/sample) | Fictional Contoso data in Web API shape (`{"value": [...]}`): 6 opportunities, 4 accounts, 6 cases, 7 articles. Zero GUIDs, one fictional contact (Alex Demo) |
| [`tests/`](tests) | 29 pytest tests, including paging against a local test server (tests only, never used in the demo) |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (14 scenes, about 785 words) and recording shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/08-copilot-in-dynamics-365-sales-and-customer-service
python3 -m pip install -r src/requirements.txt         # pytest only: the tool is standard library
python3 -m pytest                                      # 29 passed (Python 3.13, pytest 9.1)

# offline, on the sample files (exit code 1 because the sample contains errors on purpose)
PYTHONPATH=src python3 -m d365_copilot_ready check --sample src/data/sample
PYTHONPATH=src python3 -m d365_copilot_ready check --sample src/data/sample --ui-language 2070 --format json

# live, needs a tenant: a Dataverse access token in an environment variable (never in a file)
export DATAVERSE_TOKEN="$(az account get-access-token --resource https://<org>.crm4.dynamics.com --query accessToken -o tsv)"
PYTHONPATH=src python3 -m d365_copilot_ready check --org https://<org>.crm4.dynamics.com --ui-language 1033
```

Sample result: `-- 7 errors, 11 warnings, 9 info`, and `2 usable for UI language 1033` out of 7 articles.

## What the rules check (and where Learn says so)

| Rule | Meaning | Learn page |
|---|---|---|
| O001, O002 | Open opportunity: `estimatedvalue`, `estimatedclosedate`. Closed: `actualvalue`, `actualclosedate` | understand-copilot-summaries |
| O003 | `parentcontactid` empty: no key contact | understand-copilot-summaries |
| O004 (error) | `parentaccountid` empty: account history and purchase history come from the parent account | understand-copilot-summaries |
| O005-O007 | No products, no budget, no quote: those sections of the summary have nothing to say | understand-copilot-summaries |
| A001, A002 | Account: `industrycode` for the industry sentence, closed opportunities for the history | understand-copilot-summaries |
| C001 (error) | Fewer than 38 words in the case text (title, description, notes, email text): Learn says no summary is generated | copilot-use-summary |
| C003-C006 | Customer, product, subject, case type: default case summary inputs | copilot-map-custom-fields |
| K001, K002 (error) | Not Published (`statecode` 3) or not the latest version | copilot-enable-help-pane |
| K003 (error) | Article language differs from the representative's UI language | copilot-enable-help-pane, copilot-language-support |
| K004, K005 (error) | Empty `content`, or all text inside tables: Copilot reads the `content` column only and cannot read tables | copilot-enable-help-pane, faq-copilot-features |
| K006 | Images are not read either | faq-copilot-features |

Not checked, because the records do not show it: audit history (needed for recent changes and stage updates; Sales Hub
has a *Turn audit on* switch), the `prvReadProduct` privilege for the Product field, Dataverse search being on,
the experience profile, the tenant and environment settings, data loss prevention policies, competitor records.
These are settings, not data: see `demo.md`.

## What we learned / gotchas

- **Case summary minimum.** Learn: no summary is generated if the descriptions in the source fields are under 38 words
  in English. The wording is "the descriptions added in the source case fields that Copilot uses", so which fields
  count is not spelled out. Our rule counts title, description, notes and email text, which is the generous reading:
  a case that fails the rule should fail in Copilot, a case that passes it is not guaranteed a summary.
- **Knowledge: `content` only.** The help pane page says Copilot uses the `content` attribute of the knowledge article
  table and that this cannot be customised. Title, keywords and description do not feed answers. The article must be
  Published and the latest version, and tagged with the same language as the UI. A Spanish UI with English-only
  articles gives no response (Learn language scenario table).
- **Tables and images.** The FAQ says Copilot cannot read tables and images in knowledge articles.
- **Audit history.** Sales stage updates come from audit history of the last two months (top 200 records). Without
  audit on, that part of the summary has nothing to read. Sales Hub offers *Turn audit on* in the Copilot settings.
- **Names.** Copilot Service workspace is the primary representative app; it replaced Customer Service Hub for new
  organizations with Enterprise licences (Feb 2025) and the deprecated Omnichannel for Customer Service
  representative app (deprecated 1 Apr 2023). The admin app is Copilot Service admin center. Copilot features in the
  Hub need extra configuration in Power Apps (FAQ). The Sales agent in Microsoft 365 Copilot is a separate product
  from Copilot in Dynamics 365 Sales, with its own licence rules (References).
- **Paging.** Dataverse has no `$skip`, returns up to 5,000 rows per request without a page size, and the next link
  must be used unchanged with the same page size preference.
- **Nondeterministic.** Learn's FAQ: the same question can give different responses. The checker tells you what to fix
  in the data; it cannot predict the wording of a summary.

## Honest status

- Verified here: the rules, the sample result, paging and error handling (29 tests, local test server).
- **Needs the tenant, not verified here:** the live queries (entity set names, `$select` columns, the annotation and
  email filters, the `languagelocale` lookup), the token flow, and every Copilot screen. The Customer Service parts need a
  Customer Service environment that the lab does not have yet. See `demo.md` for the owner decisions (trial, cost).
- The price figures were read from the Microsoft pricing pages with a page-to-text fetch on 21 Nov 2026; confirm them on
  the pages before publishing the video.

## References

- Sales: [Default attributes used in Copilot summaries](https://learn.microsoft.com/dynamics365/sales/understand-copilot-summaries),
  [Summarize records with Copilot](https://learn.microsoft.com/dynamics365/sales/copilot-summarize-records),
  [Turn on and set up Copilot in Dynamics 365 Sales](https://learn.microsoft.com/dynamics365/sales/enable-setup-copilot),
  [Agents, Copilot, and AI capabilities in Dynamics 365 apps](https://learn.microsoft.com/dynamics365/copilot/ai-get-started)
- Sales agent in Microsoft 365 Copilot: [Use Sales agent](https://learn.microsoft.com/microsoft-sales-copilot/use-sales-chat),
  [Set up Sales agent](https://learn.microsoft.com/microsoft-sales-copilot/set-up-sales-chat),
  [Install Sales agent](https://learn.microsoft.com/microsoft-sales-copilot/install-sales-app),
  [Buy Dynamics 365 Sales](https://learn.microsoft.com/dynamics365/sales/buy-dynamics-365-sales)
- Customer Service: [Use Copilot-generated case summaries](https://learn.microsoft.com/dynamics365/customer-service/use/copilot-use-summary),
  [Manage case and custom record summary](https://learn.microsoft.com/dynamics365/customer-service/administer/copilot-map-custom-fields),
  [Manage Copilot features in Customer Service](https://learn.microsoft.com/dynamics365/customer-service/administer/configure-copilot-features),
  [Configure Copilot features in the help pane](https://learn.microsoft.com/dynamics365/contact-center/administer/copilot-enable-help-pane),
  [Ask a question](https://learn.microsoft.com/dynamics365/contact-center/use/use-ask-a-question),
  [Understand Copilot language support](https://learn.microsoft.com/dynamics365/contact-center/use/copilot-language-support),
  [FAQ for Copilot in Customer Service](https://learn.microsoft.com/dynamics365/customer-service/administer/faq-copilot-features)
- Names: [Welcome to Dynamics 365 Customer Service](https://learn.microsoft.com/dynamics365/customer-service/implement/overview),
  [Customer Service Hub app removal and migration FAQ](https://learn.microsoft.com/dynamics365/customer-service/administer/faq-csh-removal),
  [Omnichannel for Customer Service app deprecation FAQ](https://learn.microsoft.com/dynamics365/customer-service/administer/migrate-oc-faq)
- Dataverse: [Page results by using OData](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/query/page-results),
  [KnowledgeArticle table reference](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/knowledgearticle),
  [LanguageLocale table reference](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/languagelocale)
- Prices (USD per user per month, paid yearly, read 21 Nov 2026):
  [Dynamics 365 Sales pricing](https://www.microsoft.com/dynamics-365/products/sales/pricing),
  [Dynamics 365 Customer Service pricing](https://www.microsoft.com/dynamics-365/products/customer-service/pricing)
- Blog Complete Guides (devladlog.com): Dynamics 365 Sales and Customer Service topics, linked from the series plan.
