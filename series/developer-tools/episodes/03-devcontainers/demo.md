# Demo shot list — DEVLADLOG Dev Tools #3, Dev Containers

Everything except the four `screen` scenes is already real: code excerpts from `src/orders-app`, the image check
output (read from mcr.microsoft.com on 21 Nov 2026), the merged configuration from the Dev Containers CLI 0.91.0,
`dotnet test` (15 passed) and `pytest` (45 passed with the opt-ins). No Microsoft 365 tenant, Azure resource or
GitHub repository is needed. Status: **needs the recording laptop** (Docker Desktop) for all four screens.

## Lab environment

| Machine | What | Notes |
|---|---|---|
| Recording laptop (Windows 11, host of the Hyper-V lab) | WSL 2 with an **Ubuntu** distribution | `wsl --install -d Ubuntu` if missing. The Hyper-V lab VMs are **not** used; shut them down to free RAM. |
| | **Docker Desktop** for Windows, *Use the WSL 2 based engine* on, *Resources → WSL integration* on for Ubuntu | Licence: confirm Momento Galático is within Docker's free-use terms, otherwise a paid seat. Give it at least 4 GB RAM (the container builds .NET). |
| | **VS Code** + extensions *WSL* (`ms-vscode-remote.remote-wsl`) and *Dev Containers* (`ms-vscode-remote.remote-containers`) | Dark Modern theme, `window.zoomLevel` 1, 1920×1080. |
| | Git inside Ubuntu | `sudo apt install git` if missing. |

Network: the first build pulls `mcr.microsoft.com/devcontainers/dotnet:3-10.0-noble` and the Features from
`ghcr.io`, then NuGet packages. Do one warm-up build off camera; record the second "Reopen in Container" or a
**Rebuild Container** so the wait is short (the NuGet volume makes the restore fast).

Cost: none (no cloud resources).

## Setup (off camera)

In the Ubuntu (WSL) terminal, **not** under `/mnt/c`:

```bash
mkdir -p ~/src && cp -r <mg-lab>/series/developer-tools/episodes/03-devcontainers/src/orders-app ~/src/
cd ~/src/orders-app
rm -rf src/*/bin src/*/obj tests/*/bin tests/*/obj
git init -b main
git config user.name "Alex Demo" && git config user.email alex.demo@contoso.com
git add . && git commit -m "chore: import orders-app"     # hooks are not installed yet (no core.hooksPath)
export PS1='$ '
code .
```

`<mg-lab>` is the repo path as seen from WSL (for example `/mnt/c/...`); copying from there is fine, working
there is not.

Warm-up: F1 → **Dev Containers: Reopen in Container**, wait for "Dev container ready", then
F1 → **Dev Containers: Reopen Folder in WSL**. Now the image and Features are cached.

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `reopen` | `screens/reopen.jpg` | VS Code connected to WSL with `~/src/orders-app` open. F1 → **Dev Containers: Reopen in Container**. Capture when the post-create terminal shows `Hooks: .githooks  \|  fetch.prune=true  pull.ff=only` and the last line `Dev container ready: dotnet 10.0.4xx \| Python 3.x \| gh 2.x`, with the remote indicator bottom-left reading **Dev Container: Contoso orders-app (.NET 10)**. If the volume was new, a `Taking ownership of /home/vscode/.nuget/packages` line appears above: keep it in frame if possible (it proves the chown branch). |
| `run` | `screens/run.jpg` | New terminal in the container: `dotnet test` → `Passed!  - Failed: 0, Passed: 15`. Then `dotnet run --project src/Contoso.Orders.Api` (listening on `http://localhost:8080`). **Ports** panel: 8080, label **Orders API**. Browser on Windows: `http://localhost:8080/healthz` showing `"os": "Ubuntu 24.04..."` and `"inContainer": true`; a second capture of `http://localhost:8080/orders?page=5` with `"pageNumber":5` and 37 items (Firefox/Edge JSON viewer, collapsed `items`). |
| `extensions` | `screens/extensions.jpg` | Extensions view (Ctrl+Shift+X) inside the container: section **DEV CONTAINER: CONTOSO ORDERS-APP (.NET 10) - INSTALLED** with C# Dev Kit, C#, EditorConfig, GitHub Actions, Python, Pylance, autopep8. Type `eslint` in the search box: ESLint shows an **Install in Dev Container** button (not installed). Optional second capture: Docker Desktop → **Volumes** with `orders-app-nuget`. |
| `windows` | `screens/wsl.jpg` | Left: Windows Terminal, Ubuntu tab, `pwd` → `/home/<user>/src/orders-app`, `docker version --format '{{.Server.Os}}'` → `linux`. Right: Docker Desktop → Settings → General (*Use the WSL 2 based engine* checked) and Resources → WSL integration (Ubuntu on). Two captures side by side in the edit is fine. |

Checks to make during recording (not scenes, but confirm and fix the README if they differ):
1. The `Taking ownership` line appears on the first create with a new volume (delete the volume first:
   `docker volume rm orders-app-nuget` while the container is stopped) and does **not** appear on the next rebuild.
2. ESLint is really absent from the container's installed list (the `-dbaeumer.vscode-eslint` removal works).
3. A commit in the container's terminal with message `added stuff` is rejected by the episode 1 hook (proves
   `setup-dev.sh` ran), and `git commit -m "build(devcontainer): add .NET 10 dev container"` passes.
4. `python3 tools/devcontainer_check.py` in the container prints `OK` (if the image has moved to a new major by the
   recording date, it prints `STALE`: record that instead and update the pin in a follow-up commit).

## Masking
- The Windows/WSL user name in paths (`/home/<user>`, the WSL title bar, `\\wsl$` paths) and in the terminal prompt
  (`export PS1='$ '`).
- VS Code Accounts menu (bottom of the activity bar) if signed in; Docker Desktop's account avatar (top right).
- Nothing else is sensitive: the image, Features and orders data are public or fictional.

## Tear-down
1. F1 → **Dev Containers: Reopen Folder in WSL**, then in Docker Desktop delete the `vsc-orders-app-*` container
   and image (or `docker ps -a --filter label=devcontainer.local_folder` → `docker rm -f <id>`).
2. `docker volume rm orders-app-nuget`.
3. `rm -rf ~/src/orders-app`.
4. Optional: `docker image rm mcr.microsoft.com/devcontainers/dotnet:3-10.0-noble` if disk space is needed
   (keep it if episode 4 is recorded next).
