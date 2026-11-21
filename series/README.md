# DEVLADLOG category series

One **video series** and one **social Spotlight series** per [devladlog.com](https://www.devladlog.com) category (14).
Data lives in [`series.yaml`](series.yaml); regenerate the READMEs and stubs with `python series/build_series.py`.

| Series | Blog category | Episodes planned | Episode 01 | Ep 01 target | First Spotlight |
|---|---|---|---|---|---|
| [DEVLADLOG Power Apps](powerapps/) | [PowerApps](https://www.devladlog.com/articles/powerapps/) | 10 | Model-Driven Apps | 01 Dec | 23 Nov |
| [DEVLADLOG Azure](azure/) | [Azure](https://www.devladlog.com/articles/azure/) | 10 | Azure Functions & Serverless | 03 Dec | 24 Nov |
| [DEVLADLOG SharePoint](sharepoint/) | [SharePoint](https://www.devladlog.com/articles/sharepoint/) | 10 | Lists & Libraries Best Practices | 08 Dec | 25 Nov |
| [DEVLADLOG .NET](net/) | [.NET](https://www.devladlog.com/articles/net/) | 12 | Minimal APIs | 10 Dec | 26 Nov |
| [DEVLADLOG Power Automate](power-automate/) | [Power Automate](https://www.devladlog.com/articles/power-automate/) | 16 | Cloud Flows Fundamentals | 15 Dec | 27 Nov |
| [DEVLADLOG AI](ai/) | [AI](https://www.devladlog.com/articles/ai/) | 17 | Prompt Engineering for LLMs | 17 Dec | 28 Nov |
| [DEVLADLOG Power BI](power-bi/) | [Power BI](https://www.devladlog.com/articles/power-bi/) | 17 | Data Modeling & Star Schema | 22 Dec | 29 Nov |
| [DEVLADLOG Microsoft 365](microsoft-365/) | [Microsoft 365](https://www.devladlog.com/articles/microsoft-365/) | 17 | Tenant Administration & Monitoring | 29 Dec | 30 Nov |
| [DEVLADLOG SQL](sql/) | [SQL](https://www.devladlog.com/articles/sql/) | 12 | T-SQL Advanced Queries | 05 Jan | 01 Dec |
| [DEVLADLOG Dynamics 365](dynamics-365/) | [Dynamics 365](https://www.devladlog.com/articles/dynamics-365/) | 12 | Dataverse Deep Dive | 07 Jan | 02 Dec |
| [DEVLADLOG Code](programming-languages/) | [Programming Languages](https://www.devladlog.com/articles/programming-languages/) | 11 | TypeScript Best Practices | 12 Jan | 03 Dec |
| [DEVLADLOG Windows Server](windows-server/) | [Windows Server](https://www.devladlog.com/articles/windows-server/) | 12 | Windows Server Administration | 14 Jan | 04 Dec |
| [DEVLADLOG Dev Tools](developer-tools/) | [Developer Tools](https://www.devladlog.com/articles/developer-tools/) | 12 | Git & GitHub Best Practices | 19 Jan | 05 Dec |
| [DEVLADLOG Deep Dive](deep-dive/) | [Deep Dive](https://www.devladlog.com/articles/deep-dive/) | 18 | Enterprise Document Intelligence (AI Document Intelligence + Power Automate + SharePoint) | 21 Jan | 06 Dec |

**Video cadence:** Tue + Thu 18:00 Lisbon, rotating through the series (each series gets an episode about every 7 weeks).
**Spotlight cadence:** daily 09:30 Lisbon, one series per day (14-day rotation), LinkedIn page + Facebook.
**MG Lab** continues as the flagship cross-topic series; Shorts stay at 13:00.

Videos use the same pipeline as MG Lab (`pipeline/make_episode.py`) with `series_label`, `series_name` and `file_prefix`
set in each `script.yaml`.
