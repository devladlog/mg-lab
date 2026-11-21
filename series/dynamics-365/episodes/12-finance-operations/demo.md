# Demo shot list — DEVLADLOG Dynamics 365 #12: Finance & Operations with Business Central

Already run in the build container (no Docker, no tenant): `python3 -m pytest -q tests` (36 passed) and the Pester tests of the setup
script (33 passed, 1 skipped, the DPAPI round trip needs Windows), plus the offline `customers`/`reconcile` on the fictional samples.
**Nothing has run against a real Business Central container or Dataverse yet: all four `screen` scenes need the recording laptop (and the
Sales trial tenant for the reconcile).** The unverified details are listed in the README ("Not verified") and are checked in steps 3 and 6.

## Lab environment

The Finance trial is gone from the plan (no trial exists for the lab). The live demo is **Business Central in a local developer
container on the recording laptop**. New resource, not in `series/LAB.md` yet (add it there once provisioned). No Hyper-V lab VM, no
Azure resource, no licence, no cost.

| Item | Spec |
|---|---|
| Machine | The recording laptop (Windows, Core Ultra 9, 24 threads, 191 GB RAM). Host Windows only; the Hyper-V lab VMs (`CON-*`) are not used and keep running |
| Docker | Docker Desktop for Windows, **in Windows-containers mode** (taskbar icon, *Switch to Windows Containers*). Check: `docker info --format '{{.OSType}}'` prints `windows`. The script checks it and says how to switch. Docker Desktop's licence terms apply (Learn notes a free option "might require a licence"): the owner confirms before installing |
| PowerShell | Elevated **Windows PowerShell 5.1** (`powershell.exe`, Run as administrator). Learn: version 28.0 containers have a known problem with PowerShell 7 |
| Module | BcContainerHelper from the PowerShell Gallery (the script installs it; needs internet) |
| Container | Name `mglab-bc`; sandbox artifacts, latest, country `us` (company **CRONUS USA, Inc.**); `NavUserPassword`; memory limit 8 GB (Learn: a container uses at least 6 GB); `-updateHosts`, `-assignPremiumPlan`, no desktop shortcuts |
| RAM / CPU | 8 GB limit; the laptop has far more, so no constraint |
| Disk | About 15 GB for artifacts plus images (Learn). Check the free space on the drive Docker Desktop stores its data on **and** on `C:` (the artifact cache is `C:\bcartifacts.cache`, working files `C:\ProgramData\BCContainerHelper`). The first run is a big download: run it **the day before** recording |
| Ports | Container defaults (BcContainerHelper source): web client 80, file share 8080, management 7045, client services 7046, SOAP 7047, **OData/API 7048**, developer 7049. Plain HTTP, no `-useSSL`. **Not published** to the laptop's LAN: the laptop reaches the container by name through the hosts entry that `-updateHosts` adds (`http://mglab-bc:7048/BC/api/v2.0`). Nothing is opened in Windows Firewall. If Docker's NAT subnet collides with the Hyper-V lab network `10.50.0.0/24`, `docker network ls` shows it: report it, do not renumber the lab |
| Secret | The generated admin password is DPAPI-encrypted in `E:\MGLab\secrets\mglab-bc.admin.dpapi` (only the recording Windows user on this laptop can decrypt it). It is never printed, never in the repo, never on screen. `-SetEnv` puts it in `BC_PASSWORD` of the current shell only: close that shell after recording |
| Dataverse side | **Dynamics 365 Sales trial** environment (until ~21 Dec 2026): record before it ends. `labadmin` is System Administrator there. Interactive sign-in from `bckit` (no secret needed): Learn sample client id, as in episodes 1-11 |
| Tools | Python 3.10+ and `pip install --user -r requirements.txt` on the laptop; dark terminal font 18+; browser with `pipeline/mask.js` for the Dataverse capture |

The Business Central container is **not** connected to Dataverse (online Business Central only connects to Dataverse environments of the
same Entra tenant; the container is a local stand-in for the product, not for the sync). The episode never claims a sync: the reconcile
is the code-level check.

**Fallback if the container cannot be built** (Windows containers feature missing, Docker mode cannot be switched, artifact download
blocked, creation fails even with `-Isolation hyperv`): cut the `container`, `doctor` and `invoices` screens, keep the architecture and
code scenes, and tell the owner. No stub, mock or fake server is ever shown.

## Setup (the day before)

1. Install Docker Desktop if it is not there, start it, switch to Windows containers.
2. Elevated Windows PowerShell 5.1:
   `cd <repo>\series\dynamics-365\episodes\12-finance-operations`
   `.\setup\New-LabBusinessCentral.ps1 -AcceptEula` (you accept the container EULA by passing the switch). It prints the Docker check,
   the artifact URL, the container creation log (Business Central's own output) and finally
   `API ok at http://mglab-bc:7048/BC/api/v2.0 : <n> company(ies): ...`. If it stops with the 401 hint, see step 3.
3. **Verify and note in README ("Not verified")**: the API answers at that URL; the generated password is accepted. If the script reports
   401: sign in to the web client as `admin` (the log shows the URL and the user name), open the user card and create a *web service access
   key*, and use that as `BC_PASSWORD` in step 4 (the script itself never changes the password). Note the real company names, whether the US
   sandbox has more than one company, and fix `README.md` and `bc.json`.
4. Same shell: `.\setup\New-LabBusinessCentral.ps1 -SetEnv`, then `cd src`, `python -m bckit doctor`, `python -m bckit companies`.
5. Seed the fictional customers: `python -m bckit seed --company "CRONUS USA, Inc." --dry-run`, then without `--dry-run`. Write down the
   numbers Business Central assigned to Contoso Retail, Contoso Logistics Ltd and Contoso Hospitality Group (the output shows them).
6. Dataverse (Sales trial, Sales Hub, Accounts), by hand: on **Contoso Retail** set *Account Number* = its Business Central number
   (create the account if it does not exist from episode 7); create **Contoso Logistics Holdings** with the number of Contoso Logistics
   Ltd (so R003 shows a name difference); create **Contoso Legacy Store** with a number Business Central does not have, for example
   `LEGACY-1` (R002). Contoso Hospitality Group stays only in Business Central (R001); the person Alex Demo gives R005. Then
   `$env:DATAVERSE_URL = 'https://<sales trial org>.crm4.dynamics.com'` and
   `python -m bckit reconcile --name-contains Contoso; echo "exit $LASTEXITCODE"`. If the Dataverse call needs another sign-in, use the
   browser prompt (leave `AZURE_CLIENT_SECRET` unset). **Verify and note in README**: whether the trial's sample accounts already have
   account numbers (the unscoped run would show them as R002) and what the output really is. Keep whatever it prints.
7. In the Business Central web client (sign in as `admin`): create one **Sales Invoice** for Contoso Retail with any item from the item
   list, one line, and **Post** it. Then `python -m bckit invoices --company "CRONUS USA, Inc." --customer <Contoso Retail number>`.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/bc-container.jpg` — "A real container on the laptop"
Elevated PowerShell on the laptop: run `.\setup\New-LabBusinessCentral.ps1 -AcceptEula` a **second time** (idempotent: Docker check line,
"Container mglab-bc is already running.", the `API ok` line with the company names, the hint for `-SetEnv`). Then `docker ps` with
`mglab-bc` running (image and status visible) and the Business Central web client open on CRONUS USA, Inc. No password anywhere on
screen. Mask: nothing secret exists here; keep the host name `mglab-bc`.

### 2. `screens/bckit-customers.jpg` — "The first real call"
```powershell
python -m bckit doctor
python -m bckit seed --company "CRONUS USA, Inc."     # shows "exists ..." lines on a second run: that is the idempotency
python -m bckit customers --company "CRONUS USA, Inc." --limit 12
```
Real output: the URL it calls, the two `ok:` lines with the company names, the seed lines with Business Central's numbers, the counts and
the first customers. If the first attempt fails, record the real error line and what fixed it (for example the 401 hint).

### 3. `screens/bckit-invoices.jpg` — "The money side"
Business Central web client: the posted Sales Invoice for Contoso Retail (number and amount visible). Then the terminal:
```powershell
python -m bckit invoices --company "CRONUS USA, Inc." --customer <number>
python -m bckit invoices --company "CRONUS USA, Inc." --status Open --limit 5
```
Keep what it prints (status, due date, remaining amount per customer).

### 4. `screens/bckit-reconcile.jpg` — "Two systems, one answer"
```powershell
python -m bckit reconcile --name-contains Contoso; echo "exit $LASTEXITCODE"
python -m bckit reconcile; echo "exit $LASTEXITCODE"      # unscoped: CRONUS' own customers show up as R001, that is the point
```
Expect R001 (Contoso Hospitality Group), R002 (Contoso Legacy Store), R003 (Contoso Logistics), R005 (Alex Demo) and exit 1 in the scoped
run. Then side by side: the Business Central customer card for Contoso Retail and the Dataverse Account with the same number. If the output
is cleaner than planned, say so; if you fall back to the offline sample, label it "sample". Mask the Dataverse URL, tenant and user.

## Masking checklist
- Dataverse org URL, tenant name, user principal names, avatars. The Business Central host name `mglab-bc` is fine.
- The container password and any web service access key: never visible (typed into nothing; `BC_PASSWORD` is set silently by the script).
  If a web service access key was created, do not open the user card on camera.
- Only fictional customers (Contoso ..., Alex Demo), CRONUS demo data, and lab users on screen.

## Tear-down
1. Terminal: close the PowerShell windows that had `BC_PASSWORD` set (or `Remove-Item Env:BC_PASSWORD, Env:BC_USER, Env:BC_BASE_URL`).
2. `.\setup\New-LabBusinessCentral.ps1 -Remove` in the elevated prompt: removes the container, its hosts entry and shortcuts
   (`Remove-BcContainer`), and the encrypted password file. Business Central data inside the container goes with it (the seeded
   customers and the posted invoice are not kept anywhere else).
3. Disk (optional, only when the episode is finished for good): delete `C:\bcartifacts.cache`; remove the Business Central images
   that `docker images` lists as created for `mglab-bc` with `docker rmi <image id>` (those only; do not prune other images).
4. Dataverse: clear the account number on *Contoso Retail*; delete *Contoso Logistics Holdings* and *Contoso Legacy Store*; leave
   Contoso Retail and its cases for other episodes.
5. Docker Desktop: switch back to Linux containers if other episodes need them.
