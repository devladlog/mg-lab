# DEVLADLOG Azure

**Blog category:** [Azure](https://www.devladlog.com/articles/azure/) · ~116 articles · track: azure
**Audience:** Cloud architects and developers designing and running workloads on Azure
**YouTube playlist:** `DEVLADLOG Azure` · **Hashtags:** #Azure #CloudArchitecture #DevOps

Two series run side by side:

1. **Video series** — one 5-7 min, narrated, real demo in the lab tenant (masked), English episode per blog topic, plus 3 Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, daily 09:30 Lisbon, one series per day, 14-day rotation; each post links one article,
   rotating through the five formats (Complete Guide, Architecture Patterns and Decision Framework, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | Tue 24 Nov 2026 09:30, then every 14 days |
| Episode 01 target premiere | Thu 03 Dec 2026 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
| 01 | Azure Functions & Serverless | [Complete Guide](https://www.devladlog.com/articles/azure/2026-01-05-azure-functions-serverless-complete-guide-2026/) |
| 02 | Cloud Architecture | [Complete Guide](https://www.devladlog.com/articles/azure/2026-01-01-cloud-architecture-complete-guide-2026/) |
| 03 | Azure DevOps & CI/CD | [Complete Guide](https://www.devladlog.com/articles/azure/2026-01-08-azure-devops-cicd-complete-guide-2026/) |
| 04 | Security & Identity (Entra ID) | [Complete Guide](https://www.devladlog.com/articles/azure/2026-01-19-security-identity-entra-id-complete-guide-2026/) |
| 05 | Monitoring & Application Insights | [Complete Guide](https://www.devladlog.com/articles/azure/2026-01-23-monitoring-application-insights-complete-guide-2026/) |
| 06 | Cost Optimization | [Complete Guide](https://www.devladlog.com/articles/azure/2026-01-26-cost-optimization-complete-guide-2026/) |
| 07 | Azure Storage & Databases | [Complete Guide](https://www.devladlog.com/articles/azure/2026-01-16-azure-storage-databases-complete-guide-2026/) |
| 08 | Container Apps & AKS | [Complete Guide](https://www.devladlog.com/articles/azure/2026-02-03-container-apps-aks-complete-guide-2026/) |
| 09 | Networking & VPN | [Complete Guide](https://www.devladlog.com/articles/azure/2026-01-30-networking-vpn-complete-guide-2026/) |
| 10 | Azure AI & Cognitive Services | [Complete Guide](https://www.devladlog.com/articles/azure/2026-01-12-azure-ai-cognitive-services-complete-guide-2026/) |

Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
- [ ] Azure subscription + €10 budget alert (exists); raise the budget for AKS/networking episodes
- [ ] Cloud Shell + Bicep (exists)
- [ ] A second region or VNet pair for Networking & VPN
- [ ] Tear-down script per episode so nothing keeps billing
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: "AZURE"` in each `script.yaml`
- [ ] Episode 01 script: [`episodes/01-azure-functions-serverless/script.yaml`](episodes/01-azure-functions-serverless/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/azure/episodes/01-azure-functions-serverless/script.yaml --out build/azure-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `DEVLADLOG Azure` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
