# DEVLADLOG Dynamics 365

**Blog category:** [Dynamics 365](https://www.devladlog.com/articles/dynamics-365/) · ~72 articles · track: power-platform
**Audience:** Dynamics 365 CE consultants, admins and developers
**YouTube playlist:** `DEVLADLOG Dynamics 365` · **Hashtags:** #Dynamics365 #Dataverse #PowerPlatform

Two series run side by side:

1. **Video series** — one 5-7 min, narrated, real demo in the lab tenant (masked), English episode per blog topic, plus 3 Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, daily 09:30 Lisbon, one series per day, 14-day rotation; each post links one article,
   rotating through the five formats (Complete Guide, Architecture Patterns and Decision Framework, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | Wed 02 Dec 2026 09:30, then every 14 days |
| Episode 01 target premiere | Thu 07 Jan 2027 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
| 01 | Dataverse Deep Dive | [Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-26-dataverse-deep-dive-complete-guide-2025/) |
| 02 | Security Roles & Teams | [Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-11-14-security-roles-teams-complete-guide-2025/) |
| 03 | Dynamics 365 Customization | [Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-11-03-dynamics-365-customization-complete-guide-2025/) |
| 04 | Business Process Flows | [Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-30-business-process-flows-complete-guide-2025/) |
| 05 | Custom Plugins & Workflows | [Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-23-custom-plugins-workflows-complete-guide-2025/) |
| 06 | Integration with Power Platform | [Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-11-06-integration-with-power-platform-complete-guide-2025/) |
| 07 | Dynamics 365 Sales | [Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-08-dynamics-365-sales-complete-guide-2025/) |
| 08 | Dynamics 365 Customer Service | [Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-12-dynamics-365-customer-service-complete-guide-2025/) |
| 09 | Power Apps Portal Integration | [Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-19-power-apps-portal-integration-complete-guide-2025/) |
| 10 | Reporting & Analytics | [Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-11-17-reporting-analytics-complete-guide-2025/) |
| 11 | Dynamics 365 Administration | [Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-11-10-dynamics-365-administration-complete-guide-2025/) |
| 12 | Finance & Operations | [Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-16-dynamics-365-finance-operations-complete-guide-2025/) |

Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
- [ ] Dynamics 365 Sales / Customer Service trial environment (30 days; create when filming starts)
- [ ] MG Lab DEV for Dataverse-only episodes (exists)
- [ ] Finance & Operations needs a partner/trial environment: plan as an architecture-only episode if none
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: "DYNAMICS 365"` in each `script.yaml`
- [ ] Episode 01 script: [`episodes/01-dataverse-deep-dive/script.yaml`](episodes/01-dataverse-deep-dive/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/dynamics-365/episodes/01-dataverse-deep-dive/script.yaml --out build/dynamics-365-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `DEVLADLOG Dynamics 365` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
