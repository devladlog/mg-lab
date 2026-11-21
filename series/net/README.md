# DEVLADLOG .NET

**Blog category:** [.NET](https://www.devladlog.com/articles/net/) · ~133 articles · track: azure
**Audience:** .NET developers building APIs, web apps and services on Azure
**YouTube playlist:** `DEVLADLOG .NET` · **Hashtags:** #dotnet #csharp #aspnetcore

Two series run side by side:

1. **Video series** — one 5-7 min, narrated, real demo in the lab tenant (masked), English episode per blog topic, plus 3 Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, daily 09:30 Lisbon, one series per day, 14-day rotation; each post links one article,
   rotating through the five formats (Complete Guide, Architecture Patterns and Decision Framework, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | Thu 26 Nov 2026 09:30, then every 14 days |
| Episode 01 target premiere | Thu 10 Dec 2026 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
| 01 | Minimal APIs | [Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-05-minimal-apis-complete-guide-2026/) |
| 02 | ASP.NET Core Web APIs | [Complete Guide](https://www.devladlog.com/articles/dotnet/2026-04-20-aspnet-core-web-apis-complete-guide-2026/) |
| 03 | Entity Framework Core | [Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-01-entity-framework-core-complete-guide-2026/) |
| 04 | Dependency Injection & DI Containers | [Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-08-dependency-injection-di-containers-complete-guide-2026/) |
| 05 | Testing with xUnit & NUnit | [Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-23-testing-with-xunit-nunit-complete-guide-2026/) |
| 06 | Blazor WebAssembly & Server | [Complete Guide](https://www.devladlog.com/articles/dotnet/2026-04-24-blazor-webassembly-server-complete-guide-2026/) |
| 07 | SignalR Real-Time Communication | [Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-12-signalr-real-time-communication-complete-guide-2026/) |
| 08 | gRPC Services | [Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-16-grpc-services-complete-guide-2026/) |
| 09 | Performance Optimization | [Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-19-performance-optimization-complete-guide-2026/) |
| 10 | .NET 8/9 Features | [Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-27-net-89-features-complete-guide-2026/) |
| 11 | Microservices with .NET | [Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-30-microservices-with-net-complete-guide-2026/) |
| 12 | .NET MAUI Cross-Platform Apps | [Complete Guide](https://www.devladlog.com/articles/dotnet/2026-04-27-net-maui-cross-platform-apps-complete-guide-2026/) |

Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
- [ ] .NET 8/9 SDK in the container (exists)
- [ ] Azure subscription with the €10 budget alert (exists)
- [ ] Azure SQL or SQL Server container for EF Core
- [ ] Android emulator or Windows machine for .NET MAUI
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: ".NET"` in each `script.yaml`
- [ ] Episode 01 script: [`episodes/01-minimal-apis/script.yaml`](episodes/01-minimal-apis/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/net/episodes/01-minimal-apis/script.yaml --out build/net-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `DEVLADLOG .NET` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
