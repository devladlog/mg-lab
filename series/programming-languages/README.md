# DEVLADLOG Code

**Blog category:** [Programming Languages](https://www.devladlog.com/articles/programming-languages/) · ~75 articles · track: azure
**Audience:** Developers who want production-grade habits in C#, TypeScript, Python and PowerShell
**YouTube playlist:** `DEVLADLOG Code` · **Hashtags:** #TypeScript #CSharp #CleanCode

Two series run side by side:

1. **Video series** — one 5-7 min, narrated, real demo in the lab tenant (masked), English episode per blog topic, plus 3 Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, daily 09:30 Lisbon, one series per day, 14-day rotation; each post links one article,
   rotating through the five formats (Complete Guide, Architecture Patterns and Decision Framework, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | Thu 03 Dec 2026 09:30, then every 14 days |
| Episode 01 target premiere | Tue 12 Jan 2027 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
| 01 | TypeScript Best Practices | [Complete Guide](https://www.devladlog.com/articles/programming-languages/2026-06-07-typescript-best-practices-complete-guide-2026/) |
| 02 | C# Advanced Features | [Complete Guide](https://www.devladlog.com/articles/programming-languages/2026-06-03-c-advanced-features-complete-guide-2026/) |
| 03 | Async/Await Patterns | [Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-06-25-asyncawait-patterns-complete-guide-2025/) |
| 04 | LINQ & Functional Programming | [Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-06-21-linq-functional-programming-complete-guide-2025/) |
| 05 | Design Patterns in Practice | [Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-06-28-design-patterns-in-practice-complete-guide-2025/) |
| 06 | Clean Code Principles | [Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-07-02-clean-code-principles-complete-guide-2025/) |
| 07 | PowerShell Automation | [Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-06-17-powershell-automation-complete-guide-2025/) |
| 08 | Python for Azure Development | [Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-06-10-python-for-azure-development-complete-guide-2025/) |
| 09 | JavaScript/Node.js Patterns | [Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-06-14-javascriptnodejs-patterns-complete-guide-2025/) |
| 10 | Performance Profiling | [Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-07-06-performance-profiling-complete-guide-2025/) |
| 11 | Modern Language Features | [Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-07-09-modern-language-features-complete-guide-2025/) |

Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
- [ ] Container toolchains: .NET, Node, Python, pwsh (exist)
- [ ] No cloud resources needed for most episodes
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: "CODE"` in each `script.yaml`
- [ ] Episode 01 script: [`episodes/01-typescript-best-practices/script.yaml`](episodes/01-typescript-best-practices/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/programming-languages/episodes/01-typescript-best-practices/script.yaml --out build/programming-languages-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `DEVLADLOG Code` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
