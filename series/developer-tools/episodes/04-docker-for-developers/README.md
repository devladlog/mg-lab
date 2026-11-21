# DEVLADLOG Dev Tools #4 — Docker for developers: a real image and a local stack

The orders API from [episode 3](../03-devcontainers/) gets a database (EF Core: SQLite or SQL Server) and ships as
an image. One multi-stage **Dockerfile** builds it on the .NET 10 SDK image and runs it on the chiseled ASP.NET
image as a non-root user; **compose.yaml** starts it next to **SQL Server 2025** with a health check, a data volume
and the password in a git-ignored `.env`. A small linter keeps the three files honest, and the tests run the
Dockerfile's own build commands and start the result the way the container does, all without a Docker daemon.

| Path | What it is |
|---|---|
| [`src/orders-app/Dockerfile`](src/orders-app/Dockerfile) | `sdk:10.0-noble` build stage (restore layer, BuildKit NuGet cache, `-a $TARGETARCH`) → `aspnet:10.0-noble-chiseled-extra` final stage; tag + digest pins; `/data` owned by `$APP_UID`; `USER $APP_UID`; exec-form `ENTRYPOINT` |
| [`src/orders-app/.dockerignore`](src/orders-app/.dockerignore) | Build context = 7 files: no `bin/obj`, `.git`, `.env`, tests, tools |
| [`src/orders-app/compose.yaml`](src/orders-app/compose.yaml) | `api` (built from the Dockerfile, `depends_on: service_healthy`, `develop.watch`) + `db` (`mssql/server:2025-latest`, sqlcmd health check, `mssql-data` volume); ports on 127.0.0.1 only |
| [`src/orders-app/.env.example`](src/orders-app/.env.example) | The only variable: `MSSQL_SA_PASSWORD` (copy to `.env`, which is git-ignored) |
| [`src/orders-app/tools/container_lint.py`](src/orders-app/tools/container_lint.py) | Our rules for Dockerfile (DF001–DF009), build context (DI001) and Compose (DC001–DC007); `context` lists what Docker would send |
| [`src/orders-app/src/Contoso.Orders.Api/`](src/orders-app/src/Contoso.Orders.Api/) | Minimal API + EF Core: `Database:Provider` = `Sqlite` or `SqlServer`, seeded on first start, `POST /orders` with validation, `/healthz` (provider, OS, user) |
| [`src/orders-app/tests/Contoso.Orders.Api.Tests/`](src/orders-app/tests/Contoso.Orders.Api.Tests/) | 20 xUnit tests: API on SQLite, SQL Server schema generated offline, provider selection, `__` → `:` config mapping, the Compose connection string parsed by SqlClient |
| [`tests/`](tests/) | 56 pytest tests: Dockerfile, `.dockerignore`, Compose (official schema + interpolation), publish-and-run, SDK-built image |
| [`tests/schemas/compose-spec.json`](tests/schemas/compose-spec.json) | The Compose Specification JSON schema, vendored from compose-spec/compose-spec |
| [`tests/fixtures/Dockerfile.naive`](tests/fixtures/Dockerfile.naive) | The "first Dockerfile" we all wrote, for the linter to take apart (10 errors) |

## Run the tests

```bash
cd series/developer-tools/episodes/04-docker-for-developers
(cd src/orders-app && dotnet test)              # Passed! 20 passed
python3 -m pytest -q tests                       # 54 passed, 2 skipped (~10 s)
SDK_CONTAINER=1 python3 -m pytest -q tests       # 56 passed (downloads ~70 MB of base image layers once)

cd src/orders-app && python3 tools/container_lint.py   # ✓ 0 error(s), 0 warning(s)
```

What runs where:

| Check | Build machine (here, no Docker) | Recording laptop (Docker Desktop) |
|---|---|---|
| Dockerfile / `.dockerignore` / compose.yaml rules, Compose schema, `${VAR:?}` interpolation | yes | yes (plus `docker compose config`) |
| Every `COPY` source exists in the build context | yes | yes (`docker build` would fail otherwise) |
| The Dockerfile's `dotnet restore` + `dotnet publish` commands, then the app started like the final stage (same ENTRYPOINT and ENV, SQLite in a `/data` stand-in, SIGTERM, restart) | yes, for real | yes, as `docker build` / `docker run` |
| An image built **without** a Dockerfile (`dotnet publish /t:PublishContainer` to an archive) and inspected | yes (opt-in) | yes, and `docker load` |
| `docker build`, BuildKit cache mount, `--chown=$APP_UID`, chiseled runtime, Compose networking, SQL Server health check, `compose watch` | **no** | **yes**, see [demo.md](demo.md) |
| API against a real SQL Server | **no** (SQL Server schema is generated offline by EF Core) | **yes**, in Compose |

## Use it

```bash
cd src/orders-app
# single container, SQLite in a named volume
docker build -t contoso/orders-api:dev .
docker run --rm -p 127.0.0.1:8080:8080 -v orders-data:/data contoso/orders-api:dev

# the stack, with SQL Server
cp .env.example .env            # set MSSQL_SA_PASSWORD (8+ chars, 3 of: upper, lower, digit, symbol; no ; or ")
docker compose up --build       # or: docker compose watch   (rebuilds api when ./src changes)
curl http://localhost:8080/healthz
docker compose down             # keeps the mssql-data volume; down -v deletes it
```

## What we learned / gotchas

- **Chiseled means no shell.** Microsoft Learn: chiseled images "don't contain a shell or package manager" and run as
  the non-root `app` user. So `docker exec -it <api> sh` fails, a shell-form `ENTRYPOINT` can't work, and a
  `curl`-based health check for the API isn't possible; the database has the health check that matters.
  The linter rejects shell-form `ENTRYPOINT`/`CMD` (Docker docs: `/bin/sh -c` doesn't pass `SIGTERM` from
  `docker stop`).
- **Only chiseled images default to non-root.** From the registry: `aspnet:10.0-noble-chiseled-extra` has
  `User=1654`, `aspnet:10.0-noble` has no user set (root). `USER $APP_UID` in the final stage makes it explicit for
  both; a test proves the linter catches the regular image without it.
- **`-extra` for SQL Server.** The plain chiseled image sets `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=true` (no ICU);
  the `-extra` variant includes ICU and tzdata (Learn). Compressed size from the registry: 56.7 MB chiseled,
  72.6 MB chiseled-extra, 104.0 MB regular `aspnet:10.0-noble` (amd64).
- **Port 8080, not 80.** Since .NET 8 the ASP.NET images listen on 8080 (`ASPNETCORE_HTTP_PORTS`), because port 80
  needs root. The linter flags an `EXPOSE` below 1024.
- **The non-root user can't write to `/app`.** SQLite needs a writable folder, so the build stage creates `/data`
  and the final stage copies it with `--chown=$APP_UID:$APP_UID`. Docker copies an image folder's contents into a new
  empty volume mounted over it; the recording checks that the volume is writable by the app (demo.md, check 2).
  The SDK-built image has no such folder (tested), which is why this repo keeps the Dockerfile.
- **`Encrypt` is on by default in Microsoft.Data.SqlClient** (EF Core 7 breaking change). The dev SQL Server
  container has a self-signed certificate, so the Compose connection string adds `TrustServerCertificate=True`,
  which Learn allows "only for controlled development environments". Never in production.
- **Long strings in YAML:** the connection string and the health check use folded scalars (`>-`) to stay readable.
  Folding puts a space before `Password=`; a SqlClient test parses the exact string Compose produces, and a pytest
  test keeps that literal in sync with the file.
- **A missing variable is an empty string, unless you say otherwise.** `${MSSQL_SA_PASSWORD:?set ... in .env}` makes
  `docker compose` stop with that message instead of starting SQL Server with an empty password. In the health check,
  `$$MSSQL_SA_PASSWORD` is read inside the container, so the password never lands in the file (both tested with an
  interpolation of the real file).
- **`depends_on` alone only waits for the container to start.** `condition: service_healthy` waits for the sqlcmd
  health check (`/opt/mssql-tools18/bin/sqlcmd`; `-No` makes encryption optional, the option Learn gives for when
  the secure-by-default sqlcmd 18 can't connect);
  EF Core's `EnableRetryOnFailure` covers the rest.
- **`COPY` of an ignored file breaks the build.** The test walks every `COPY` source against the computed build
  context. `.dockerignore` patterns are relative to the context root: `bin/` only matches the root folder, use
  `**/bin/`.
- **`dotnet publish /t:PublishContainer` needs no Dockerfile and no daemon** for an archive. The SDK (10.0.115 here)
  picked `aspnet:10.0-noble-chiseled-extra` from `<ContainerFamily>`, user `1654`, port 8080 and
  `ENTRYPOINT ["dotnet", "/app/Contoso.Orders.Api.dll"]`. The file it wrote was a plain tar despite the `.tar.gz`
  name, and a relative `ContainerArchiveOutputPath` is resolved from the **project** folder, not from where you run
  the command (we looked for `./images` in the repo root and it was in `src/Contoso.Orders.Api/images`).
- **SQL Server containers are x86-64 only** (Learn: emulation such as Rosetta 2 or Prism isn't supported), fine on
  the recording laptop, not on an Arm machine.
- **Digest pins freeze patches too.** The `FROM` lines pin tag and digest (Learn calls the digest a best practice);
  let Dependabot or Renovate bump them, the same lesson as the dev container pin in episode 3.
- `docker compose config`, `hadolint` and a real `docker build` aren't available on the build machine; the linter
  covers our rules and the recording runs the real tools.

## References
- Microsoft Learn: [Introduction to .NET and Docker](https://learn.microsoft.com/dotnet/core/docker/introduction) (port 8080, `app` user, chiseled: no shell or package manager) ·
  [.NET container images](https://learn.microsoft.com/dotnet/core/docker/container-images) (chiseled and `-extra` variants) ·
  [What's new in containers for .NET 8](https://learn.microsoft.com/dotnet/core/whats-new/dotnet-8/containers) (UID 1654, `$TARGETARCH` with `-a`, chiseled globalization) ·
  [Default ASP.NET Core port changed to 8080](https://learn.microsoft.com/dotnet/core/compatibility/containers/8.0/aspnet-port) ·
  [Default .NET images use Ubuntu](https://learn.microsoft.com/dotnet/core/compatibility/containers/10.0/default-images-use-ubuntu) ·
  [Tutorial: Containerize a .NET app](https://learn.microsoft.com/dotnet/core/docker/build-container) (multi-stage, digest pinning) ·
  [Containerize a .NET app with dotnet publish](https://learn.microsoft.com/dotnet/core/containers/sdk-publish) and [reference](https://learn.microsoft.com/dotnet/core/containers/publish-configuration) (`ContainerArchiveOutputPath`, `ContainerFamily`, no daemon needed) ·
  [Container Tools in Visual Studio](https://learn.microsoft.com/visualstudio/containers/container-tools) (`USER app`, `APP_UID`)
- Microsoft Learn, SQL Server: [Quickstart: SQL Server Linux containers with Docker](https://learn.microsoft.com/sql/linux/install-upgrade/quickstart-install-docker) (`2025-latest`, `mssql-tools18`, 2 GB RAM, password policy, x86-64 only) ·
  [Deploy and connect to SQL Server Linux containers](https://learn.microsoft.com/sql/linux/containers/deploy) (`-No`) ·
  [EF Core 7 breaking changes: Encrypt defaults to true](https://learn.microsoft.com/ef/core/what-is-new/ef-core-7.0/breaking-changes) ·
  [Encryption and certificate validation in Microsoft.Data.SqlClient](https://learn.microsoft.com/sql/connect/ado-net/encryption-and-certificate-validation) (`TrustServerCertificate` for development only)
- Docker docs: [Dockerfile reference](https://docs.docker.com/reference/dockerfile/) (exec vs shell form and signals, `RUN --mount=type=cache`, `COPY --chown`) ·
  [Volumes](https://docs.docker.com/engine/storage/volumes/) (contents copied into a new empty volume) ·
  [Compose file watch](https://docs.docker.com/compose/how-tos/file-watch/) (Compose 2.22+, `rebuild`) ·
  [Compose Specification schema](https://github.com/compose-spec/compose-spec/blob/main/schema/compose-spec.json)
- Images: tags, digests, users and sizes read from the mcr.microsoft.com registry API on 21 Nov 2026.
- Blog: [Docker for Developers — Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-02-docker-for-developers-complete-guide-2025/)
