# DEVLADLOG Deep Dive

**Blog category:** [Deep Dive](https://www.devladlog.com/articles/deep-dive/) · ~20 articles · track: deep-dive
**Audience:** Solution architects designing end-to-end Microsoft platforms
**YouTube playlist:** `DEVLADLOG Deep Dive` · **Hashtags:** #Azure #PowerPlatform #SolutionArchitecture

Two series run side by side:

1. **Video series** — one 5-7 min, narrated, real demo in the lab tenant (masked), English episode per blog topic, plus 3 Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, daily 09:30 Lisbon, one series per day, 14-day rotation; each post links one article,
   rotating through the five formats (Complete Guide, Architecture Patterns and Decision Framework, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | Sun 06 Dec 2026 09:30, then every 14 days |
| Episode 01 target premiere | Thu 21 Jan 2027 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
| 01 | Enterprise Document Intelligence (AI Document Intelligence + Power Automate + SharePoint) | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2026-05-18-enterprise-document-intelligence-azure-ai-power-automate-sharepoint/) |
| 02 | Enterprise AI Copilot (Azure OpenAI + Power Platform + SharePoint) | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2026-01-19-enterprise-ai-copilot-azure-openai-power-platform-sharepoint-integration/) |
| 03 | Building Secure Business Apps (Azure + Power Platform + .NET) | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-04-07-end-to-end-secure-business-app-azure-powerapps-sharepoint-dotnet/) |
| 04 | Enterprise Workflow Automation | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-02-24-enterprise-workflow-automation-azure-power-platform-sharepoint/) |
| 05 | Employee Onboarding Portal | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-04-07-building-employee-onboarding-portal-azure-powerapps-sharepoint/) |
| 06 | Customer Portal (Azure B2C + Power Pages + SharePoint) | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-11-03-customer-portal-secure-external-access-azure-b2c-power-pages-sharepoint/) |
| 07 | Enterprise API Management (APIM + Service Bus) | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-03-17-enterprise-api-management-azure-apim-service-bus-microservices/) |
| 08 | DevSecOps Pipeline | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-05-19-devsecops-pipeline-azure-devops-github-actions-container-security/) |
| 09 | Zero Trust Network Architecture | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2026-02-16-zero-trust-network-architecture-azure-ad-conditional-access-intune-defender/) |
| 10 | Cloud-Native Application Platform (AKS + Dapr + KEDA + Service Bus) | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2026-04-20-cloud-native-application-platform-aks-dapr-keda-azure-service-bus/) |
| 11 | Multi-Tenant SaaS on Azure | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-08-11-multi-tenant-saas-on-azure-architecture-identity-data-isolation/) |
| 12 | Modern Intranet Platform (SharePoint + Viva + Teams + Power Platform) | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-01-13-modern-intranet-platform-sharepoint-viva-teams-power-platform/) |
| 13 | Hybrid Work Platform | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-09-08-hybrid-work-platform-teams-sharepoint-viva-azure-communication-services/) |
| 14 | Enterprise Data Lakehouse (Synapse + Databricks + Power BI + Purview) | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2026-03-16-enterprise-data-lakehouse-azure-synapse-databricks-power-bi-purview/) |
| 15 | Data Analytics Platform | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-06-23-data-analytics-platform-synapse-power-bi-data-factory-ml/) |
| 16 | Enterprise Reporting Platform | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-07-07-enterprise-reporting-platform-power-bi-synapse-analytics-data-governance/) |
| 17 | Cloud Migration Platform | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-10-20-cloud-migration-platform-azure-migrate-site-recovery-hybrid-cloud/) |
| 18 | IoT Solution (IoT Hub + Stream Analytics) | [Complete Guide](https://www.devladlog.com/articles/deep-dive/2025-12-01-iot-solution-azure-iot-hub-stream-analytics-real-time-dashboards/) |

Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
- [ ] Everything above, combined; longer episodes (10-15 min) built from pieces already filmed in the other series
- [ ] Architecture diagrams per episode (drawn, not screenshots)
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: "DEEP DIVE"` in each `script.yaml`
- [ ] Episode 01 script: [`episodes/01-enterprise-document-intelligence-ai-document-int/script.yaml`](episodes/01-enterprise-document-intelligence-ai-document-int/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/deep-dive/episodes/01-enterprise-document-intelligence-ai-document-int/script.yaml --out build/deep-dive-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `DEVLADLOG Deep Dive` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
