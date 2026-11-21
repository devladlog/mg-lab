# DEVLADLOG SQL

**Blog category:** [SQL](https://www.devladlog.com/articles/sql/) · ~72 articles · track: azure
**Audience:** DBAs and developers working with SQL Server and Azure SQL
**YouTube playlist:** `DEVLADLOG SQL` · **Hashtags:** #SQLServer #TSQL #AzureSQL

Two series run side by side:

1. **Video series** — one 5-7 min, narrated, real demo in the lab tenant (masked), English episode per blog topic, plus 3 Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, daily 09:30 Lisbon, one series per day, 14-day rotation; each post links one article,
   rotating through the five formats (Complete Guide, Architecture Patterns and Decision Framework, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | Tue 01 Dec 2026 09:30, then every 14 days |
| Episode 01 target premiere | Tue 05 Jan 2027 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
| 01 | T-SQL Advanced Queries | [Complete Guide](https://www.devladlog.com/articles/sql/2025-07-17-t-sql-advanced-queries-complete-guide-2025/) |
| 02 | Database Design & Normalization | [Complete Guide](https://www.devladlog.com/articles/sql/2025-07-20-database-design-normalization-complete-guide-2025/) |
| 03 | Indexing Strategies | [Complete Guide](https://www.devladlog.com/articles/sql/2025-07-24-indexing-strategies-complete-guide-2025/) |
| 04 | Query Optimization | [Complete Guide](https://www.devladlog.com/articles/sql/2025-07-27-query-optimization-complete-guide-2025/) |
| 05 | Stored Procedures & Functions | [Complete Guide](https://www.devladlog.com/articles/sql/2025-07-31-stored-procedures-functions-complete-guide-2025/) |
| 06 | SQL Server Security | [Complete Guide](https://www.devladlog.com/articles/sql/2025-08-04-sql-server-security-complete-guide-2025/) |
| 07 | Backup & Recovery | [Complete Guide](https://www.devladlog.com/articles/sql/2025-08-07-backup-recovery-complete-guide-2025/) |
| 08 | SQL Server Performance Tuning | [Complete Guide](https://www.devladlog.com/articles/sql/2025-07-13-sql-server-performance-tuning-complete-guide-2025/) |
| 09 | High Availability & Disaster Recovery | [Complete Guide](https://www.devladlog.com/articles/sql/2025-08-11-high-availability-disaster-recovery-complete-guide-2025/) |
| 10 | Always On Availability Groups | [Complete Guide](https://www.devladlog.com/articles/sql/2025-08-22-always-on-availability-groups-complete-guide-2025/) |
| 11 | SQL Server Integration Services (SSIS) | [Complete Guide](https://www.devladlog.com/articles/sql/2025-08-15-sql-server-integration-services-ssis-complete-guide-2025/) |
| 12 | SQL Server Reporting Services (SSRS) | [Complete Guide](https://www.devladlog.com/articles/sql/2025-08-18-sql-server-reporting-services-ssrs-complete-guide-2025/) |

Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
- [ ] SQL Server 2022 Developer in a container (free) or Azure SQL Database serverless (budget alert)
- [ ] Fictional sample database script committed to the repo
- [ ] Two SQL Server VMs (homelab Hyper-V) for Always On and HA/DR
- [ ] SSIS/SSRS need a Windows VM with SQL Server Developer
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: "SQL"` in each `script.yaml`
- [ ] Episode 01 script: [`episodes/01-t-sql-advanced-queries/script.yaml`](episodes/01-t-sql-advanced-queries/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/sql/episodes/01-t-sql-advanced-queries/script.yaml --out build/sql-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `DEVLADLOG SQL` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
