# DEVLADLOG Power Apps

**Blog category:** [PowerApps](https://www.devladlog.com/articles/powerapps/) · ~136 articles · track: power-platform
**Audience:** Power Platform makers and pro developers building canvas and model-driven apps
**YouTube playlist:** `DEVLADLOG Power Apps` · **Hashtags:** #PowerApps #PowerPlatform #LowCode

Two series run side by side:

1. **Video series** — one 5-7 min, narrated, real demo in the lab tenant (masked), English episode per blog topic, plus 3 Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, daily 09:30 Lisbon, one series per day, 14-day rotation; each post links one article,
   rotating through the five formats (Complete Guide, Architecture Patterns and Decision Framework, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | Mon 23 Nov 2026 09:30, then every 14 days |
| Episode 01 target premiere | Tue 01 Dec 2026 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
| 01 | Model-Driven Apps | [Complete Guide](https://www.devladlog.com/articles/powerapps/2026-02-10-model-driven-apps-complete-guide-2026/) |
| 02 | Canvas Apps Fundamentals | [Complete Guide](https://www.devladlog.com/articles/powerapps/2026-02-06-canvas-apps-fundamentals-complete-guide-2026/) |
| 03 | Power Fx Formulas & Tips | [Complete Guide](https://www.devladlog.com/articles/powerapps/2026-02-14-power-fx-formulas-tips-complete-guide-2026/) |
| 04 | Dataverse Integration | [Complete Guide](https://www.devladlog.com/articles/powerapps/2026-02-17-dataverse-integration-complete-guide-2026/) |
| 05 | Custom Connectors | [Complete Guide](https://www.devladlog.com/articles/powerapps/2026-02-21-custom-connectors-complete-guide-2026/) |
| 06 | Power Automate Integration | [Complete Guide](https://www.devladlog.com/articles/powerapps/2026-02-25-power-automate-integration-complete-guide-2026/) |
| 07 | Component Libraries | [Complete Guide](https://www.devladlog.com/articles/powerapps/2026-02-28-component-libraries-complete-guide-2026/) |
| 08 | Mobile App Design | [Complete Guide](https://www.devladlog.com/articles/powerapps/2026-03-04-mobile-app-design-complete-guide-2026/) |
| 09 | ALM & DevOps for Power Platform | [Complete Guide](https://www.devladlog.com/articles/powerapps/2026-03-08-alm-devops-for-power-platform-complete-guide-2026/) |
| 10 | AI Builder Integration | [Complete Guide](https://www.devladlog.com/articles/powerapps/2026-03-11-ai-builder-integration-complete-guide-2026/) |

Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
- [ ] MG Lab DEV/TEST/PROD environments (exist)
- [ ] Power Apps Developer Plan or per-app licence for premium connectors
- [ ] AI Builder credits for the AI Builder episode (trial capacity)
- [ ] A phone or emulator for Mobile App Design
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: "POWER APPS"` in each `script.yaml`
- [ ] Episode 01 script: [`episodes/01-model-driven-apps/script.yaml`](episodes/01-model-driven-apps/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/powerapps/episodes/01-model-driven-apps/script.yaml --out build/powerapps-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `DEVLADLOG Power Apps` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
