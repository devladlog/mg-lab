# DEVLADLOG AI

**Blog category:** [AI](https://www.devladlog.com/articles/ai/) · ~101 articles · track: sharepoint-m365
**Audience:** Developers and architects putting AI into enterprise apps responsibly
**YouTube playlist:** `DEVLADLOG AI` · **Hashtags:** #AzureAI #GenerativeAI #AzureOpenAI

Two series run side by side:

1. **Video series** — one 5-7 min, narrated, real demo in the lab tenant (masked), English episode per blog topic, plus 3 Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, daily 09:30 Lisbon, one series per day, 14-day rotation; each post links one article,
   rotating through the five formats (Complete Guide, Architecture Patterns and Decision Framework, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | Sat 28 Nov 2026 09:30, then every 14 days |
| Episode 01 target premiere | Thu 17 Dec 2026 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
| 01 | Prompt Engineering for LLMs | [Complete Guide](https://www.devladlog.com/articles/ai/2025-02-03-prompt-engineering-complete-guide-2025/) |
| 02 | Azure OpenAI Enterprise Patterns | [Complete Guide](https://www.devladlog.com/articles/ai/2026-06-03-azure-openai-enterprise-complete-guide-2026/) |
| 03 | RAG Patterns & Vector Search | [Complete Guide](https://www.devladlog.com/articles/ai/2026-03-31-rag-patterns-complete-guide-2026/) |
| 04 | Document Intelligence & Forms | [Complete Guide](https://www.devladlog.com/articles/ai/2026-06-04-document-intelligence-complete-guide-2026/) |
| 05 | AI Agents & Orchestration | [Complete Guide](https://www.devladlog.com/articles/ai/2026-05-02-ai-agents-orchestration-complete-guide-2026/) |
| 06 | Responsible AI & Ethics | [Complete Guide](https://www.devladlog.com/articles/ai/2025-05-06-responsible-ai-complete-guide-2025/) |
| 07 | AI Governance & Compliance | [Complete Guide](https://www.devladlog.com/articles/ai/2025-07-09-ai-governance-complete-guide-2025/) |
| 08 | AI Model Monitoring & Drift | [Complete Guide](https://www.devladlog.com/articles/ai/2025-06-08-model-monitoring-complete-guide-2025/) |
| 09 | Fine-Tuning LLMs for Enterprise | [Complete Guide](https://www.devladlog.com/articles/ai/2026-04-01-fine-tuning-llms-complete-guide-2026/) |
| 10 | Multi-Modal AI Models | [Complete Guide](https://www.devladlog.com/articles/ai/2025-08-11-multimodal-ai-complete-guide-2025/) |
| 11 | Conversational AI & Chatbots | [Complete Guide](https://www.devladlog.com/articles/ai/2025-04-05-conversational-ai-complete-guide-2025/) |
| 12 | NLP & Text Analytics | [Complete Guide](https://www.devladlog.com/articles/ai/2025-03-05-nlp-text-analytics-complete-guide-2025/) |
| 13 | Computer Vision & Image Analysis | [Complete Guide](https://www.devladlog.com/articles/ai/2025-03-04-computer-vision-complete-guide-2025/) |
| 14 | MLOps & ML Pipelines | [Complete Guide](https://www.devladlog.com/articles/ai/2025-05-07-mlops-pipelines-complete-guide-2025/) |
| 15 | Generative AI & LLMs | [Complete Guide](https://www.devladlog.com/articles/ai/2025-07-10-generative-ai-complete-guide-2025/) |
| 16 | Machine Learning Fundamentals | [Complete Guide](https://www.devladlog.com/articles/ai/2025-01-02-machine-learning-fundamentals-complete-guide-2025/) |
| 17 | Azure AI Services Platform | [Complete Guide](https://www.devladlog.com/articles/ai/2025-01-01-azure-ai-services-complete-guide-2025/) |

Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
- [ ] Azure AI Foundry / Azure OpenAI resource with a small deployment (pay-as-you-go, budget alert)
- [ ] Azure AI Search (free tier) for RAG
- [ ] Azure AI Document Intelligence (free tier F0)
- [ ] Fictional sample documents and data only
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: "AI"` in each `script.yaml`
- [ ] Episode 01 script: [`episodes/01-prompt-engineering-for-llms/script.yaml`](episodes/01-prompt-engineering-for-llms/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/ai/episodes/01-prompt-engineering-for-llms/script.yaml --out build/ai-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `DEVLADLOG AI` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
