# DEVLADLOG Dev Tools #3 — Dev Containers: one environment, in the repo

The Contoso **orders-app** from episodes 1 and 2 becomes a .NET 10 API, and its development environment moves
into the repository. Clone, **Reopen in Container**, and you have the .NET 10 SDK, Python for the episode 1 hooks,
the GitHub CLI, the team's VS Code extensions, a forwarded port and restored packages. Nothing installed on the
laptop except Docker and VS Code.

| Path | What it is |
|---|---|
| [`src/orders-app/.devcontainer/devcontainer.json`](src/orders-app/.devcontainer/devcontainer.json) | Image `mcr.microsoft.com/devcontainers/dotnet:3-10.0-noble`, Features (Python os-provided, GitHub CLI), port 8080, NuGet named volume, `postCreateCommand`, extensions (adds three, removes one the image brings), `hostRequirements` for Codespaces |
| [`src/orders-app/.devcontainer/post-create.sh`](src/orders-app/.devcontainer/post-create.sh) | Runs after the container is created: fixes the volume's ownership, installs the episode 1 hooks, `dotnet restore`, prints the toolchain |
| [`src/orders-app/tools/devcontainer_check.py`](src/orders-app/tools/devcontainer_check.py) | Compares the pinned image tag with the floating tag straight from the registry (no Docker) and shows what the image itself adds |
| [`src/orders-app/src/Contoso.Orders.Api/`](src/orders-app/src/Contoso.Orders.Api/) | Minimal API: `/orders` with the paging rules from episode 1 (50 per page, max 100), `/orders/{id}`, `/healthz` that reports the OS it runs on |
| [`src/orders-app/tests/Contoso.Orders.Api.Tests/`](src/orders-app/tests/Contoso.Orders.Api.Tests/) | 15 xUnit tests (paging rules, the API through `WebApplicationFactory`, `inContainer` from `DOTNET_RUNNING_IN_CONTAINER`) |
| `src/orders-app/.githooks/`, `tools/repo_guard/`, `scripts/setup-dev.sh`, `.gitattributes` | Copied unchanged from [episode 1](../01-git-github-best-practices/src/kit/) |
| [`tests/`](tests/) | 45 pytest tests: official schemas, team rules, `post-create.sh` run for real, the image check, the Dev Containers CLI |
| [`tests/schemas/`](tests/schemas/) | Official JSON schemas, vendored: `devContainer.base.schema.json` (devcontainers/spec) and the VS Code and Codespaces parts (microsoft/vscode) |
| [`tests/fixtures/`](tests/fixtures/) | Registry responses and Feature manifests recorded from `mcr.microsoft.com` and `ghcr.io` on 21 Nov 2026, plus the script that re-records them |

## Run the tests

```bash
cd series/developer-tools/episodes/03-devcontainers
(cd src/orders-app && dotnet test)          # Passed! 15 passed
python3 -m pytest -q tests                   # 42 passed, 3 skipped (~17 s: post-create runs dotnet restore)

# the opt-in ones: live registry + the official Dev Containers CLI
npm install --prefix /tmp/dccli @devcontainers/cli          # 0.91.0 used here
ONLINE=1 DEVCONTAINER_CLI=/tmp/dccli/node_modules/.bin/devcontainer python3 -m pytest -q tests   # 45 passed
```

What runs where:

| Check | Build machine (here, no Docker) | Recording laptop (Docker Desktop) |
|---|---|---|
| `devcontainer.json` against the official schemas + team rules | yes | yes |
| Feature ids/options against the published Feature manifests | yes (recorded) / live with the CLI | yes |
| `devcontainer read-configuration` (Features downloaded, merged with image metadata) | yes, with a stub `docker` that answers "no container yet" | yes |
| `post-create.sh` (hooks, restore, idempotent, fails on error, chown branch as a non-root user) | yes, for real in a temp copy | yes, inside the container |
| Image freshness (`tools/devcontainer_check.py`) | yes, live registry or recorded | yes |
| Building the container, VS Code attaching, port forwarding, extensions installed | **no** | **yes**, see [demo.md](demo.md) |

## Use it

On Windows: WSL 2, Docker Desktop with the WSL 2 engine, VS Code with the Dev Containers extension. Clone **inside
the WSL file system**, then:

```bash
cd ~/src && git clone <repo> orders-app && code orders-app
# F1 → Dev Containers: Reopen in Container
# terminal in the container:
dotnet test
dotnet run --project src/Contoso.Orders.Api      # port 8080 is forwarded: http://localhost:8080/healthz
python3 tools/devcontainer_check.py              # is our image pin still getting updates?
```

## What we learned / gotchas

- **A pinned image major freezes silently.** Dev container image tags carry the image's own version first:
  `3-10.0-noble` is image major 3 with .NET 10. We started with `1-10.0-noble` and the registry showed that tag was
  last built on 16 Oct 2025 with `DOTNET_SDK_VERSION=10.0.100-rc.2.25502.107`, a release candidate, while `10.0-noble`
  was image 3.0.1 with SDK 10.0.404 (built 20 Nov 2026). Nothing fails, you just stay behind.
  `tools/devcontainer_check.py` reads both from the registry and exits 1 when the pin is behind; a test replays the
  recorded responses so the check runs offline too.
- **You get more extensions than you list.** The image metadata (`devcontainer.metadata` label) adds
  `dbaeumer.vscode-eslint` and `ms-dotnettools.csharp` (the image bakes in the Node Feature), and the Python Feature
  adds `ms-python.python`, `ms-python.vscode-pylance` and `ms-python.autopep8`. `devcontainer read-configuration
  --include-merged-configuration` shows the merged list. A leading `-` removes one (`"-dbaeumer.vscode-eslint"`); a
  test fails if a removal targets something neither the image nor a Feature adds.
- **A new named volume belongs to root.** The NuGet cache is a named volume so packages survive a rebuild. Docker
  creates it owned by root, the tools run as `vscode`, so `post-create.sh` takes ownership once (the VS Code docs
  use `sudo chown` in `postCreateCommand` for the same reason). Tested by running the script as `nobody` with a
  root-owned folder.
- **`postCreateCommand` runs again after every rebuild**, so every step is idempotent (tested by running it twice),
  and `set -euo pipefail` makes a failed restore stop the script instead of printing "ready" (tested).
- **The schema is strict.** `devContainer.base.schema.json` rejects unknown properties, so a typo like
  `postCreateComand` fails validation instead of being silently ignored; it also declares
  `allowTrailingCommas: false`. The VS Code part references `vscode://schemas/settings/machine`, which only exists
  inside VS Code; the test maps it to "any object".
- **`read-configuration` still calls Docker** (`docker ps` to look for an existing container). On a machine without
  Docker we pass `--docker-path` to a stub that returns nothing; the CLI then fetched the Features from ghcr.io and the
  image metadata from MCR itself.
- **Where the files live matters on Windows.** Microsoft Learn: keep the project in the WSL 2 file system, not on
  `C:\`, or Docker goes through a cross-OS file share that is "significantly slower". `.gitattributes` from episode 1
  keeps `*.sh` LF so `post-create.sh` survives a Windows checkout.
- **`global.json` with `rollForward: latestFeature`** lets the image's SDK 10.0.404 build a repo that asks for
  10.0.100; a test keeps the image's .NET version, `global.json` and the projects' `net10.0` in step.

## References
- Microsoft Learn: [Set up Dev Containers on Windows](https://learn.microsoft.com/windows/dev-environment/docker/dev-containers) (WSL 2 + Docker Desktop prerequisites, store files in WSL, Reopen in Container) ·
  [Get started with Docker remote containers on WSL 2](https://learn.microsoft.com/windows/wsl/tutorials/wsl-containers) ·
  [Releases and support for .NET](https://learn.microsoft.com/dotnet/core/releases-and-support) (.NET 10 LTS until November 2028) ·
  [Default .NET images use Ubuntu](https://learn.microsoft.com/dotnet/core/compatibility/containers/10.0/default-images-use-ubuntu)
- Dev Container spec: [devcontainer.json reference](https://containers.dev/implementors/json_reference/) (lifecycle order, `waitFor`, `remoteUser`, `forwardPorts`, `onAutoForward`, `hostRequirements`) ·
  [schemas](https://github.com/devcontainers/spec/tree/main/schemas) · [Dev Containers CLI](https://github.com/devcontainers/cli)
- VS Code: [Developing inside a container](https://code.visualstudio.com/docs/devcontainers/containers) ·
  [Improve disk performance](https://code.visualstudio.com/remote/advancedcontainers/improve-performance) (targeted named volumes and `chown`, Clone Repository in Container Volume) ·
  [VS Code devcontainer schemas](https://github.com/microsoft/vscode/tree/main/extensions/configuration-editing/schemas) (extension ids, `-` to remove)
- GitHub: [Setting a minimum specification for codespace machines](https://docs.github.com/en/codespaces/setting-up-your-project-for-codespaces/configuring-dev-containers/setting-a-minimum-specification-for-codespace-machines) (`hostRequirements`)
- Images: `mcr.microsoft.com/devcontainers/dotnet` tags and labels were read from the registry API (`/v2/.../tags/list`, manifests, config blobs) on 21 Nov 2026.
- Blog: [DevContainers — Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-27-devcontainers-complete-guide-2025/)
