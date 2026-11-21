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
| 04 | [A Dataverse plugin in C# with unit tests](episodes/04-dataverse-plugin-csharp/) | Plug-in source (net462, signed), 9 xUnit + Moq tests, Web API registration script, CI workflow |
| 05 | [Azure Functions + Microsoft Graph with managed identity](episodes/05-azure-functions-graph-managed-identity/) | Function (.NET 8, Flex Consumption), Bicep with no keys, Sites.Selected grant calls, tests, Cloud Shell deploy |
| 06 | [File share → SharePoint migration with PnP PowerShell](episodes/06-sharepoint-migration-pnp/) | Migration module (inventory, pre-flight, metadata, idempotent re-runs), 17 Pester tests, sample share, PnP app setup |
| 07 | [A Power Apps code component (PCF) in TypeScript](episodes/07-pcf-code-component/) | Field component (currency input with approval bands), 19 Jest tests, `pac pcf push`, solution project for release |

Each episode folder contains the script, the code and a short written guide.
Everything uses placeholder names and a demo tenant. No client code or data.

## How the videos are made

The [`pipeline/`](pipeline/) folder turns an episode `script.yaml` into a narrated 1080p video,
vertical Shorts with burned-in captions, an SRT file, chapters and a thumbnail — using open-source tools
(Kokoro TTS, FFmpeg, Pillow, Pygments).

## License

Code samples: [MIT](LICENSE). Fonts in `pipeline/fonts`: SIL Open Font License (Inter, JetBrains Mono).
