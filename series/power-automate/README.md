# DEVLADLOG Power Automate

**Blog category:** [Power Automate](https://www.devladlog.com/articles/power-automate/) · ~97 articles · track: power-platform
**Audience:** Makers and developers automating business processes
**YouTube playlist:** `DEVLADLOG Power Automate` · **Hashtags:** #PowerAutomate #PowerPlatform #Automation

Two series run side by side:

1. **Video series** — one 5-7 min, narrated, real demo in the lab tenant (masked), English episode per blog topic, plus 3 Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, daily 09:30 Lisbon, one series per day, 14-day rotation; each post links one article,
   rotating through the five formats (Complete Guide, Architecture Patterns and Decision Framework, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | Fri 27 Nov 2026 09:30, then every 14 days |
| Episode 01 target premiere | Tue 15 Dec 2026 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
| 01 | Cloud Flows Fundamentals | [Complete Guide](https://www.devladlog.com/articles/power-automate/2025-01-01-cloud-flows-fundamentals-complete-guide-2025/) |
| 02 | Approval Workflows & Business Process | [Complete Guide](https://www.devladlog.com/articles/power-automate/2025-01-02-approval-workflows-complete-guide-2025/) |
| 03 | Advanced Expressions & Functions | [Complete Guide](https://www.devladlog.com/articles/power-automate/2025-03-05-expressions-functions-complete-guide-2025/) |
| 04 | HTTP Connector & REST API Patterns | [Complete Guide](https://www.devladlog.com/articles/power-automate/2026-05-02-http-connector-patterns-complete-guide-2026/) |
| 05 | SharePoint Integration | [Complete Guide](https://www.devladlog.com/articles/power-automate/2025-05-06-sharepoint-integration-complete-guide-2025/) |
| 06 | Microsoft Teams Integration | [Complete Guide](https://www.devladlog.com/articles/power-automate/2026-06-03-teams-integration-complete-guide-2026/) |
| 07 | Excel & Data Operations | [Complete Guide](https://www.devladlog.com/articles/power-automate/2026-06-04-excel-data-operations-complete-guide-2026/) |
| 08 | Custom Connectors | [Complete Guide](https://www.devladlog.com/articles/power-automate/2025-03-04-custom-connectors-complete-guide-2025/) |
| 09 | ALM & Solution Management | [Complete Guide](https://www.devladlog.com/articles/power-automate/2025-07-09-alm-solution-management-complete-guide-2025/) |
| 10 | Performance Optimization | [Complete Guide](https://www.devladlog.com/articles/power-automate/2025-07-10-performance-optimization-complete-guide-2025/) |
| 11 | Security & Data Loss Prevention | [Complete Guide](https://www.devladlog.com/articles/power-automate/2025-08-11-security-dlp-complete-guide-2025/) |
| 12 | AI Builder Document Processing | [Complete Guide](https://www.devladlog.com/articles/power-automate/2025-06-08-ai-builder-processing-complete-guide-2025/) |
| 13 | Business Process Flows | [Complete Guide](https://www.devladlog.com/articles/power-automate/2026-04-01-business-process-flows-complete-guide-2026/) |
| 14 | Desktop Flows & RPA | [Complete Guide](https://www.devladlog.com/articles/power-automate/2025-02-03-desktop-flows-rpa-complete-guide-2025/) |
| 15 | Dynamics 365 Integration | [Complete Guide](https://www.devladlog.com/articles/power-automate/2025-05-07-dynamics-365-integration-complete-guide-2025/) |
| 16 | Process Mining & Process Advisor | [Complete Guide](https://www.devladlog.com/articles/power-automate/2026-03-31-process-mining-complete-guide-2026/) |

> Error Handling & Retry Patterns is already covered by MG Lab #2; link to it instead of a new episode.

Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
- [ ] MG Lab environments (exist)
- [ ] Premium licence for HTTP/custom connectors (Developer Plan)
- [ ] Power Automate Desktop on a Windows machine for Desktop Flows & RPA
- [ ] Process Mining trial for Process Advisor
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: "POWER AUTOMATE"` in each `script.yaml`
- [ ] Episode 01 script: [`episodes/01-cloud-flows-fundamentals/script.yaml`](episodes/01-cloud-flows-fundamentals/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/power-automate/episodes/01-cloud-flows-fundamentals/script.yaml --out build/power-automate-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `DEVLADLOG Power Automate` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
