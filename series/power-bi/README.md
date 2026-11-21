# DEVLADLOG Power BI

**Blog category:** [Power BI](https://www.devladlog.com/articles/power-bi/) · ~97 articles · track: power-platform
**Audience:** Report authors, data modelers and BI admins
**YouTube playlist:** `DEVLADLOG Power BI` · **Hashtags:** #PowerBI #DAX #DataAnalytics

Two series run side by side:

1. **Video series** — one 5-7 min, narrated, real demo in the lab tenant (masked), English episode per blog topic, plus 3 Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, daily 09:30 Lisbon, one series per day, 14-day rotation; each post links one article,
   rotating through the five formats (Complete Guide, Architecture Patterns and Decision Framework, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | Sun 29 Nov 2026 09:30, then every 14 days |
| Episode 01 target premiere | Tue 22 Dec 2026 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
| 01 | Data Modeling & Star Schema | [Complete Guide](https://www.devladlog.com/articles/power-bi/2025-01-01-data-modeling-complete-guide-2025/) |
| 02 | Advanced DAX | [Complete Guide](https://www.devladlog.com/articles/power-bi/2025-01-02-advanced-dax-complete-guide-2025/) |
| 03 | Power Query & M Language | [Complete Guide](https://www.devladlog.com/articles/power-bi/2025-02-03-power-query-m-complete-guide-2025/) |
| 04 | Visualization Design & Custom Visuals | [Complete Guide](https://www.devladlog.com/articles/power-bi/2025-03-04-visualization-design-complete-guide-2025/) |
| 05 | Row-Level Security | [Complete Guide](https://www.devladlog.com/articles/power-bi/2025-04-05-row-level-security-complete-guide-2025/) |
| 06 | Dashboards & Publishing | [Complete Guide](https://www.devladlog.com/articles/power-bi/2025-03-05-dashboards-publishing-complete-guide-2025/) |
| 07 | Dataflows & Shared Datasets | [Complete Guide](https://www.devladlog.com/articles/power-bi/2025-05-06-dataflows-shared-datasets-complete-guide-2025/) |
| 08 | Performance Tuning & Optimization | [Complete Guide](https://www.devladlog.com/articles/power-bi/2025-07-09-performance-tuning-complete-guide-2025/) |
| 09 | Deployment Pipelines & ALM | [Complete Guide](https://www.devladlog.com/articles/power-bi/2026-05-02-deployment-pipelines-complete-guide-2026/) |
| 10 | Incremental Refresh & Large Datasets | [Complete Guide](https://www.devladlog.com/articles/power-bi/2026-04-01-incremental-refresh-complete-guide-2026/) |
| 11 | Composite Models & DirectQuery | [Complete Guide](https://www.devladlog.com/articles/power-bi/2026-03-31-composite-models-complete-guide-2026/) |
| 12 | Paginated Reports | [Complete Guide](https://www.devladlog.com/articles/power-bi/2025-05-07-paginated-reports-complete-guide-2025/) |
| 13 | Embedded Analytics | [Complete Guide](https://www.devladlog.com/articles/power-bi/2025-06-08-embedded-analytics-complete-guide-2025/) |
| 14 | On-Premises Data Gateway | [Complete Guide](https://www.devladlog.com/articles/power-bi/2025-07-10-data-gateway-complete-guide-2025/) |
| 15 | Administration & Governance | [Complete Guide](https://www.devladlog.com/articles/power-bi/2025-08-11-administration-governance-complete-guide-2025/) |
| 16 | AI Insights & Smart Narratives | [Complete Guide](https://www.devladlog.com/articles/power-bi/2026-06-03-ai-insights-complete-guide-2026/) |
| 17 | Real-Time Analytics & Streaming | [Complete Guide](https://www.devladlog.com/articles/power-bi/2026-06-04-real-time-analytics-complete-guide-2026/) |

Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
- [ ] Power BI Desktop on a Windows machine
- [ ] Power BI Pro or a Fabric trial for workspaces, deployment pipelines and RLS testing
- [ ] Fictional sample dataset (generated, committed to the repo)
- [ ] On-premises data gateway on a homelab VM for the Gateway episode
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: "POWER BI"` in each `script.yaml`
- [ ] Episode 01 script: [`episodes/01-data-modeling-star-schema/script.yaml`](episodes/01-data-modeling-star-schema/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/power-bi/episodes/01-data-modeling-star-schema/script.yaml --out build/power-bi-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `DEVLADLOG Power BI` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
