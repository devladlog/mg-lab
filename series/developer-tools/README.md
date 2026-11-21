# DEVLADLOG Dev Tools

**Blog category:** [Developer Tools](https://www.devladlog.com/articles/developer-tools/) · ~72 articles · track: azure
**Audience:** Developers improving their daily workflow and team practices
**YouTube playlist:** `DEVLADLOG Dev Tools` · **Hashtags:** #DevTools #VSCode #GitHub

Two series run side by side:

1. **Video series** — one 5-7 min, narrated, real demo in the lab tenant (masked), English episode per blog topic, plus 3 Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, daily 09:30 Lisbon, one series per day, 14-day rotation; each post links one article,
   rotating through the five formats (Complete Guide, Architecture Patterns and Decision Framework, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | Sat 05 Dec 2026 09:30, then every 14 days |
| Episode 01 target premiere | Tue 19 Jan 2027 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
| 01 | Git & GitHub Best Practices | [Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-11-28-git-github-best-practices-complete-guide-2025/) |
| 02 | VS Code Extensions | [Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-11-25-vs-code-extensions-complete-guide-2025/) |
| 03 | DevContainers | [Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-27-devcontainers-complete-guide-2025/) |
| 04 | Docker for Developers | [Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-02-docker-for-developers-complete-guide-2025/) |
| 05 | CI/CD Pipeline Setup | [Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-06-cicd-pipeline-setup-complete-guide-2025/) |
| 06 | Code Quality Tools | [Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-09-code-quality-tools-complete-guide-2025/) |
| 07 | Code Review Best Practices | [Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-24-code-review-best-practices-complete-guide-2025/) |
| 08 | API Testing (with Postman) | [Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-16-api-testing-with-postman-complete-guide-2025/) |
| 09 | Debugging Techniques | [Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-13-debugging-techniques-complete-guide-2025/) |
| 10 | Performance Profiling Tools | [Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-20-performance-profiling-tools-complete-guide-2025/) |
| 11 | Package Management | [Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-31-package-management-complete-guide-2025/) |
| 12 | Visual Studio Tips & Tricks | [Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-11-21-visual-studio-tips-tricks-complete-guide-2025/) |

Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
- [ ] GitHub account devladlog (exists)
- [ ] VS Code + Docker on a desktop for DevContainers and Docker episodes
- [ ] Visual Studio 2022/2026 on a Windows machine for the Visual Studio episode
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: "DEV TOOLS"` in each `script.yaml`
- [ ] Episode 01 script: [`episodes/01-git-github-best-practices/script.yaml`](episodes/01-git-github-best-practices/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/developer-tools/episodes/01-git-github-best-practices/script.yaml --out build/developer-tools-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `DEVLADLOG Dev Tools` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
