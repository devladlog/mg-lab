# DEVLADLOG Microsoft 365

**Blog category:** [Microsoft 365](https://www.devladlog.com/articles/microsoft-365/) · ~85 articles · track: sharepoint-m365
**Audience:** M365 admins, security and compliance owners, IT leads
**YouTube playlist:** `DEVLADLOG Microsoft 365` · **Hashtags:** #Microsoft365 #M365Admin #ModernWork

Two series run side by side:

1. **Video series** — one 5-7 min, narrated, real demo in the lab tenant (masked), English episode per blog topic, plus 3 Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, daily 09:30 Lisbon, one series per day, 14-day rotation; each post links one article,
   rotating through the five formats (Complete Guide, Architecture Patterns and Decision Framework, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | Mon 30 Nov 2026 09:30, then every 14 days |
| Episode 01 target premiere | Tue 29 Dec 2026 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
| 01 | Tenant Administration & Monitoring | [Complete Guide](https://www.devladlog.com/articles/office-365/2025-07-10-tenant-administration-complete-guide-2025/) |
| 02 | Microsoft Teams Architecture & Governance | [Complete Guide](https://www.devladlog.com/articles/office-365/2025-01-01-teams-architecture-complete-guide-2025/) |
| 03 | Microsoft 365 Groups Lifecycle | [Complete Guide](https://www.devladlog.com/articles/office-365/2025-07-09-groups-lifecycle-complete-guide-2025/) |
| 04 | Entra ID Governance & Identity | [Complete Guide](https://www.devladlog.com/articles/office-365/2026-03-31-entra-id-governance-complete-guide-2026/) |
| 05 | Microsoft Purview Compliance | [Complete Guide](https://www.devladlog.com/articles/office-365/2025-04-05-purview-compliance-complete-guide-2025/) |
| 06 | Microsoft Defender for 365 | [Complete Guide](https://www.devladlog.com/articles/office-365/2026-05-02-defender-365-security-complete-guide-2026/) |
| 07 | Intune & Device Management | [Complete Guide](https://www.devladlog.com/articles/office-365/2026-04-01-intune-device-management-complete-guide-2026/) |
| 08 | Microsoft 365 Copilot for Microsoft 365 | [Complete Guide](https://www.devladlog.com/articles/office-365/2026-06-04-copilot-m365-complete-guide-2026/) |
| 09 | Licensing Optimization | [Complete Guide](https://www.devladlog.com/articles/office-365/2025-05-06-licensing-optimization-complete-guide-2025/) |
| 10 | Exchange Online Administration | [Complete Guide](https://www.devladlog.com/articles/office-365/2025-01-02-exchange-online-complete-guide-2025/) |
| 11 | SharePoint Online Administration | [Complete Guide](https://www.devladlog.com/articles/office-365/2025-03-04-sharepoint-online-admin-complete-guide-2025/) |
| 12 | OneDrive for Business | [Complete Guide](https://www.devladlog.com/articles/office-365/2025-02-03-onedrive-business-complete-guide-2025/) |
| 13 | Microsoft 365 Apps Deployment | [Complete Guide](https://www.devladlog.com/articles/office-365/2025-03-05-apps-deployment-complete-guide-2025/) |
| 14 | Microsoft Forms & Data Collection | [Complete Guide](https://www.devladlog.com/articles/office-365/2025-06-08-forms-data-collection-complete-guide-2025/) |
| 15 | Planner & To Do Task Management | [Complete Guide](https://www.devladlog.com/articles/office-365/2025-05-07-planner-todo-complete-guide-2025/) |
| 16 | Microsoft Viva Platform | [Complete Guide](https://www.devladlog.com/articles/office-365/2026-06-03-viva-employee-experience-complete-guide-2026/) |
| 17 | Hybrid Migration Strategies | [Complete Guide](https://www.devladlog.com/articles/office-365/2025-08-11-hybrid-migration-complete-guide-2025/) |

Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
- [ ] Lab tenant admin roles (exist)
- [ ] Microsoft 365 E5 / E5 Security trial for Defender, Purview and Entra ID Governance episodes
- [ ] Intune trial + a test VM for Intune & Device Management
- [ ] Microsoft 365 Copilot licence (1 seat) for the Copilot episode
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: "MICROSOFT 365"` in each `script.yaml`
- [ ] Episode 01 script: [`episodes/01-tenant-administration-monitoring/script.yaml`](episodes/01-tenant-administration-monitoring/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/microsoft-365/episodes/01-tenant-administration-monitoring/script.yaml --out build/microsoft-365-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `DEVLADLOG Microsoft 365` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
