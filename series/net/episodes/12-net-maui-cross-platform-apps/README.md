# DEVLADLOG .NET #12 — .NET MAUI Cross-Platform Apps: a phone and Windows client that works offline (.NET 10)

Same fictional scenario as the earlier episodes (`contoso`, `alex.demo`, departments FIN / IT / OPS). This episode builds a small
**.NET MAUI** app for the project requests API of episode 11: a list of requests, a form to submit a new one, and an
**offline outbox**. The idea carries over from episode 11: *save first, ask second*. A request typed on a phone is written to the
device before the network is tried, and is sent later with the same `Idempotency-Key`, so a retry can never create it twice.

**Honest scope.** The container has no MAUI workload, no Android SDK and no Windows. So the app is split on purpose:
everything that can be tested lives in a plain `net10.0` library (`Contoso.Mobile.Core`) and is tested here; the MAUI project
(`Contoso.Mobile`) is thin and **was not built or run in the container** (see "Not verified").

| Path | What it is |
|---|---|
| [`src/Contoso.Mobile.Core/`](src/Contoso.Mobile.Core/) | `net10.0` library. `Api/RequestsApi.cs` (talks to the episode 11 gateway, sends the `Idempotency-Key`), `Api/ApiEndpoints.cs` (10.0.2.2 on Android), `Offline/Outbox.cs` (JSON-file outbox + last-list cache), `Offline/SyncService.cs` (flush when online), `ViewModels/` (CommunityToolkit.Mvvm) |
| [`src/Contoso.Mobile/`](src/Contoso.Mobile/) | The MAUI single project: `Shell`, `Views/RequestListPage.xaml`, `Views/NewRequestPage.xaml` (compiled bindings), `MauiProgram.cs` (DI), `Platforms/Android` (manifest, cleartext config for 10.0.2.2), `Platforms/Windows` (unpackaged) |
| [`tests/Contoso.Mobile.Tests/`](tests/Contoso.Mobile.Tests/) | 59 xUnit v3 tests: API mapping, outbox and sync, view models, and the **real XAML pages** compiled and bound against the view models |
| [`deploy/tests.output.txt`](deploy/tests.output.txt) | Real output of the test run |

## Build, test, run
```powershell
cd series/net/episodes/12-net-maui-cross-platform-apps
dotnet test --project tests/Contoso.Mobile.Tests     # works on Linux/Windows/macOS, no workload needed. Expect total 59, succeeded 59

# the app: needs the maui workload (Visual Studio 2026 / VS Code + .NET MAUI extension / dotnet workload install maui)
# 1) start episode 11 (three services; ports 5311-5313), see ../11-microservices-with-net
# 2) Windows:  dotnet build src/Contoso.Mobile -f net10.0-windows10.0.19041.0 -t:Run
#    Android:  start an emulator (x64 image on Hyper-V), then  dotnet build src/Contoso.Mobile -f net10.0-android -t:Run
```
`dotnet test -m:1` is not accepted by xUnit v3 on Microsoft.Testing.Platform (it reads `-m` as its own option): use `dotnet test --project <csproj>`
and let the machine decide.

## What is tested, and how real it is
| Area | How |
|---|---|
| API client | A real `HttpClient` with a stub message handler: 201 -> Created, 200 -> Replayed, 202 -> Accepted, 5xx/408/429/no network -> Unavailable, other 4xx -> Rejected with the ProblemDetails text. The header is `Idempotency-Key` and the body is what episode 11's endpoint expects |
| Outbox / cache | Real files in a temp folder: survives a restart, same key stored once, 50 parallel adds, atomic write (no temp file left), a damaged file is set aside and the app starts empty |
| Sync | Offline sends nothing; online sends oldest first; "unavailable" stops and keeps order; a retry reuses the same key; a rejected draft is parked and never retried by itself; two flushes at once send each draft once |
| View models | Validation like the server's, pt-PT decimal comma, outbox before send, "coming back online" refreshes the list, the Submit command disables itself while running |
| Pages | The **real `.xaml`** of both pages is compiled by the MAUI XAML source generator, bound to the view models, and driven by their AutomationIds (type in the entries, click the button). Needs no emulator |
| App configuration | Android manifest has `ACCESS_NETWORK_STATE`; the cleartext config names 10.0.2.2 only; `UsesCleartextTraffic` only in `DEBUG`; the project targets Android, Windows only on Windows, and no Apple platform |

The XAML check is the interesting trick: `Microsoft.Maui.Controls` is added as a plain package (no `UseMaui`, which needs the workload),
the test project links the app's `Views/*.xaml`, and `MauiXamlInflator=SourceGen` still runs. A binding to a property that does not exist
gives `MAUIG2045`, which the test project turns into an error. Verified with a deliberate typo: the build failed, as it should.

## Not verified here
- `dotnet build src/Contoso.Mobile` (needs the maui workload; with no workload the SDK stops with NETSDK1147).
- Running on Android (emulator) or on Windows; how the pages look; real `Connectivity` events; real Shell navigation; the icon and splash generation.
- The Windows `Package.appxmanifest` keeps the `$placeholder$` tokens of the template; the project builds unpackaged (`WindowsPackageType` = `None`).
- iOS and Mac Catalyst are left out: building for them needs a Mac. Per Learn, a Linux machine can only target Android.
- The demo (`demo.md`) must be run on the lab laptop. If something differs, report it instead of re-scripting around it.

## What we learned / gotchas
- **`UseMaui` needs the workload, the XAML generator does not.** A plain `net10.0` test project with a package reference runs the source generator and catches binding typos on any OS.
- **Page tests need a dispatcher.** `BindableObject` throws "was not instantiated on a thread with a dispatcher" in a test process; a small `DispatcherProvider` stub (`TestDispatcher.cs`) fixes it.
- **`Page.SendAppearing` does nothing without a window**, so a test cannot "show" a page that way; the test calls the page's protected `OnAppearing` through reflection.
- **The guard is `CanExecute`, not the command.** Through `ICommand` (what a `Button` uses) a second tap is ignored while the first runs. Calling `SubmitCommand.ExecuteAsync` twice from code is not guarded and creates two drafts. A test documents this.
- **`NetworkAccess.Internet` is not "the server is reachable".** Learn says so. The sync service treats "Unavailable" as normal: it stops, keeps the order, and waits for the next try.
- **Android emulator: `10.0.2.2`**, not `localhost` (that is the emulator itself). Cleartext HTTP is blocked by default from API 28 on, so a network security config allows it for 10.0.2.2 only, and only in `DEBUG` builds. A physical phone needs the PC's LAN address and a firewall rule.
- **`ACCESS_NETWORK_STATE`** must be in the Android manifest for the connectivity API.
- **pt-PT writes 12.000,50.** The amount field parses with the device culture, so the demo works on a Portuguese laptop.
- **JSON file, not SQLite.** For a queue of a few drafts a file is enough and testable everywhere; SQLite is the next step when the data grows.
- **Retries are safe because of episode 11.** The draft's GUID is its `Idempotency-Key`; a flush that died after the server answered is simply sent again and comes back as 200 Replayed.

## References

- Supported platforms and build hosts for .NET MAUI: <https://learn.microsoft.com/dotnet/maui/supported-platforms>
- .NET MAUI single project (target frameworks): <https://learn.microsoft.com/dotnet/maui/fundamentals/single-project>
- Connect to local web services from Android emulators and iOS simulators (10.0.2.2, cleartext): <https://learn.microsoft.com/dotnet/maui/data-cloud/local-web-services>
- Connectivity (`NetworkAccess`, `ACCESS_NETWORK_STATE`): <https://learn.microsoft.com/dotnet/maui/platform-integration/communication/networking>
- MVVM Toolkit source generators (`ObservableProperty`, `RelayCommand`): <https://learn.microsoft.com/dotnet/communitytoolkit/mvvm/>
- What's new in .NET MAUI for .NET 10: <https://learn.microsoft.com/dotnet/maui/whats-new/dotnet-10>
- Blog Complete Guide: <https://www.devladlog.com/articles/dotnet/2026-04-27-net-maui-cross-platform-apps-complete-guide-2026/>
