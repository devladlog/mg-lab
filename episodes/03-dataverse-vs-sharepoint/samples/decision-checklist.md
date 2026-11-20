# Dataverse or SharePoint lists? — decision checklist

Score one point per "yes" in each column.

| Question | SharePoint | Dataverse |
|---|---|---|
| Is the data flat (one main list, few lookups)? | ✅ | |
| Are documents and collaboration the core of the solution? | ✅ | |
| Do all users see roughly the same rows? | ✅ | |
| Will it stay in the thousands of rows? | ✅ | |
| Are standard Microsoft 365 licences the only budget? | ✅ | |
| Do you have several related tables with business rules? | | ✅ |
| Must different users see different rows or columns? | | ✅ |
| Will it reach hundreds of thousands of rows or grow fast? | | ✅ |
| Do you need solutions, pipelines and environments (ALM)? | | ✅ |
| Do you need model-driven apps, plugins or auditing? | | ✅ |

**3+ in the Dataverse column → start in Dataverse.** Migrating later costs more than the licences.

Limits worth remembering (Microsoft Learn): a SharePoint list holds up to 30 million items; the list view threshold is
5,000 items per query; Power Apps evaluates non-delegable formulas on the first 500 rows by default (max 10,000).
