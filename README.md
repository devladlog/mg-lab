# MG Lab

**Practical Microsoft engineering, one episode at a time.**
Power Platform, SharePoint / Microsoft 365, Azure and .NET, built the way production deserves:
source control, automated tests, CI/CD and least privilege.

A video series by [Momento Galático](https://momentogalatico.com), a Microsoft consultancy based in Portugal.

📺 YouTube: [@momentogalatico](https://www.youtube.com/@momentogalatico) · 💼 [LinkedIn](https://www.linkedin.com/company/momentogalatico/)

## Episodes

| # | Episode | What you get |
|---|---------|--------------|
| 01 | [Power Platform ALM that actually works](episodes/01-power-platform-alm/) | GitHub Actions workflows (export & unpack, build & release), deployment settings files, pac CLI script |
| 02 | [Power Automate error handling: Try / Catch / Finally done right](episodes/02-power-automate-error-handling/) | Try/Catch/Finally flow definition, expressions cheat sheet, error log table, Report error child flow |
| 03 | [Dataverse vs SharePoint lists (real demo)](episodes/03-dataverse-vs-sharepoint/) | Dataverse data model + Web API script, SharePoint list schema, decision checklist |
| 03 | Dataverse vs SharePoint lists: choosing the right data layer | *coming soon* |
| 04 | A Dataverse plugin in C# with unit tests | *coming soon* |
| 05 | Azure Functions + Microsoft Graph with managed identity | *coming soon* |
| 06 | Automating SharePoint migrations with PnP PowerShell | *coming soon* |

Each episode folder contains the script, the code and a short written guide.
Everything uses placeholder names and a demo tenant. No client code or data.

## How the videos are made

The [`pipeline/`](pipeline/) folder turns an episode `script.yaml` into a narrated 1080p video,
vertical Shorts with burned-in captions, an SRT file, chapters and a thumbnail — using open-source tools
(Kokoro TTS, FFmpeg, Pillow, Pygments).

## License

Code samples: [MIT](LICENSE). Fonts in `pipeline/fonts`: SIL Open Font License (Inter, JetBrains Mono).
