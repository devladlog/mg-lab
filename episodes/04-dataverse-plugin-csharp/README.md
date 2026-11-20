# MG Lab #4 — A Dataverse plugin in C#, with unit tests

One plug-in on the **Project Request** table from [episode 3](../03-dataverse-vs-sharepoint/), registered pre-operation,
synchronous, on Create and Update:

1. A due date being set can't be in the past.
2. Budget ≥ €50,000 → priority is forced to **High**.
3. A request can't be **Approved** without a department (reads the pre-image on Update).

> First draft also had "budget can't be negative". It never ran: the currency column's minimum value (0) is checked
> by the platform before the plug-in. Don't code what the platform already does.

| Path | What it is |
|---|---|
| [`src/MGLab.Plugins`](src/MGLab.Plugins) | The plug-in: `net462`, strong-name signed, `Microsoft.CrmSdk.CoreAssemblies` |
| [`src/MGLab.Plugins/ProjectRequestRules.cs`](src/MGLab.Plugins/ProjectRequestRules.cs) | Pure rules — no Dataverse calls, clock injected |
| [`src/MGLab.Plugins.Tests`](src/MGLab.Plugins.Tests) | 9 xUnit + Moq tests; compiles the plug-in sources against the .NET 8 Dataverse SDK so they run anywhere |
| [`samples/register-plugin.js`](samples/register-plugin.js) | Registers assembly, type, steps and pre-image with the Web API |
| [`samples/plugin-tests.yml`](samples/plugin-tests.yml) | GitHub Actions workflow: build + test on Linux |

```bash
cd src
dotnet test MGLab.Plugins.Tests          # Passed: 9
dotnet build MGLab.Plugins -c Release     # bin/Release/net462/MGLab.Plugins.dll
```

**Signing key:** `MGLab.Plugins.snk` is not committed (the build signs only when it exists). Dataverse requires a signed assembly, so create your own (Visual Studio → Properties → Signing, or
`sn -k MGLab.Plugins.snk`) before building.

## References
- [Write a plug-in](https://learn.microsoft.com/power-apps/developer/data-platform/write-plug-in)
- [Event framework / pipeline stages](https://learn.microsoft.com/power-apps/developer/data-platform/event-framework)
- [Build and package plug-in code](https://learn.microsoft.com/power-apps/developer/data-platform/build-and-package)
- [Analyze plug-in performance (2-minute limit)](https://learn.microsoft.com/power-apps/developer/data-platform/analyze-performance)
- [Tracing and logging](https://learn.microsoft.com/power-apps/developer/data-platform/logging-tracing)
