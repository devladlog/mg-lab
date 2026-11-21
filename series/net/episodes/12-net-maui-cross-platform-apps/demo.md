# Demo shot list — DEVLADLOG .NET #12 .NET MAUI Cross-Platform Apps

Built and run in the container (Linux): `dotnet test --project tests/Contoso.Mobile.Tests` 59 total, 59 passed (`deploy/tests.output.txt`).
**Not verified in the container, and needed for this demo:** `dotnet build` of the MAUI app, running it on Windows and on the Android
emulator, the look of the pages, real connectivity events. If something behaves differently, report it instead of re-scripting around it.
No Azure, no tenant, no licences. Cost: nothing. **Needs the lab device:** every screen below.

## Lab environment
| What | Details |
|---|---|
| Recording machine | Lab Windows laptop (host): .NET SDK 10.0.1xx, the **maui workload** (`dotnet workload install maui`, or Visual Studio 2026 with the .NET MAUI workload), Android SDK, VS Code, Windows Terminal |
| Android emulator | Android Virtual Device with an **x64** system image, accelerated by Hyper-V / Windows Hypervisor Platform (an ARM image would be very slow) |
| Backend | Episode 11 on the same laptop: gateway `http://localhost:5311`, requests `5312`, budget `5313`. The emulator reaches it as `http://10.0.2.2:5311` |
| Hyper-V lab VMs / Azure / M365 | Not used. The 10.50.0.0/24 lab network is not used |

## Setup (before recording)
```powershell
cd series/net/episodes/12-net-maui-cross-platform-apps
dotnet test --project tests/Contoso.Mobile.Tests        # expect total 59, succeeded 59
dotnet workload list                                     # maui must be listed

# 1) episode 11, three panes (see ../11-microservices-with-net/demo.md): budget, requests, gateway. Delete requests.db* first so ids start at 1.
# 2) build once so the recording is not a build:
dotnet build src/Contoso.Mobile -f net10.0-windows10.0.19041.0
dotnet build src/Contoso.Mobile -f net10.0-android
# 3) start the emulator, wait for the home screen, then deploy and run:  dotnet build src/Contoso.Mobile -f net10.0-android -t:Run
```
Warm up: open the app once on each target, then clear the app data (emulator: Settings > Apps > Contoso Requests > Storage) so the
outbox starts empty. Font size 16+ in the terminal. Android emulator: no Google account is needed; do not sign in to anything.

## Screens (match the `screen` scenes in script.yaml)
1. `screens/request-list.jpg` (Windows app + gateway pane): the list with its budget states. POST one request through the gateway first
   (`Invoke-WebRequest http://localhost:5311/api/requests -Method Post ...`, FIN 12,000 is used later, so use IT 9,000 here).
2. `screens/offline-submit.jpg` (emulator, airplane mode on): form filled with Standing desks / FIN / 12000 / alex.demo@contoso.com, then
   Submit. Expected: "Saved on this device. It will be sent when you are back online."
3. `screens/back-online.jpg` (emulator + terminal): airplane mode off, the list refreshes by itself, the new row is Reserved;
   `GET http://localhost:5311/api/budgets/FIN` shows reserved 12000 (once).
4. `screens/tests.jpg` (VS Code terminal): `Clear-Host; dotnet test --project tests/Contoso.Mobile.Tests`, total 59 succeeded 59.

## What to mask
Nothing: fictional data only (`contoso.com`, Alex Demo). Keep the emulator's top bar free of a real account or notifications
(Do Not Disturb on). No tenant name, no real hostnames.

## Tear-down
Stop the three services (Ctrl+C), close the emulator (no snapshot needed), delete `requests.db*`, then in the episode folder
delete `bin/` and `obj/` under `src/` and `tests/`. Nothing was created in Azure or M365.
