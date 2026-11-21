# Demo shot list — DEVLADLOG Dev Tools #4, Docker for developers

Everything except the three `screen` scenes is already real: the Dockerfile, `.dockerignore` and compose.yaml
excerpts, the linter output (including the naive Dockerfile), the SDK-built image and its config, `dotnet test`
(20 passed) and `pytest` (56 passed with `SDK_CONTAINER=1`). The build machine has **no Docker daemon**, so
`docker build`, `docker run`, Compose, SQL Server and `compose watch` are recorded here for the first time. No
Microsoft 365 tenant, Azure resource or GitHub repository is needed. Status: **needs the recording laptop**.

## Lab environment

| Machine | What | Notes |
|---|---|---|
| Recording laptop (Windows 11, x64) | WSL 2 with **Ubuntu**, **Docker Desktop** (WSL 2 engine, WSL integration for Ubuntu), VS Code | Same setup as episode 3. SQL Server containers are x86-64 only (Learn), so this must be the x64 laptop, not an Arm machine. |
| Containers (created by Compose, deleted at the end) | `contoso-orders-api-1` built from the Dockerfile; `contoso-orders-db-1` from `mcr.microsoft.com/mssql/server:2025-latest` (Developer edition, `MSSQL_PID=Developer`) | SQL Server needs at least 2 GB RAM (Learn): give Docker Desktop 4 GB or more and **shut down the Hyper-V lab VMs** (CON-SQL01 alone can take 6 GB). The lab's CON-SQL01 is **not** used. |
| Volumes | `orders-data` (single-container SQLite run), `contoso-orders_mssql-data` (Compose) | Deleted at tear-down. |
| Licences | SQL Server **Developer** edition (free, non-production). Docker Desktop: confirm Momento Galático is within Docker's free-use terms, otherwise a paid seat. | Cost: none. |

Network: pulls `mcr.microsoft.com/dotnet/sdk:10.0-noble`, `mcr.microsoft.com/dotnet/aspnet:10.0-noble-chiseled-extra`
(both pinned by digest in the Dockerfile) and `mcr.microsoft.com/mssql/server:2025-latest`. Pull them once off camera.

## Setup (off camera)

In the Ubuntu (WSL) terminal:

```bash
mkdir -p ~/src && rm -rf ~/src/orders-app
cp -r <mg-lab>/series/developer-tools/episodes/04-docker-for-developers/src/orders-app ~/src/
cd ~/src/orders-app && rm -rf src/*/bin src/*/obj tests/*/bin tests/*/obj
export PS1='$ '
docker pull mcr.microsoft.com/mssql/server:2025-latest
docker build -t contoso/orders-api:dev .          # warm-up build: pulls the base images, fills the NuGet cache
python3 tools/container_lint.py                    # ✓ 0 error(s), 0 warning(s)
docker compose config --quiet 2>&1 | head -3       # expect the MSSQL_SA_PASSWORD error until .env exists
```

Do **not** create `.env` yet (the `stack` screen starts without it). Choose a password that meets the SQL Server
policy (8+ characters, three of: upper case, lower case, digits, symbols) and has no `;` or `"`. Never show it.

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `buildrun` | `screens/buildrun.jpg` | 1) Edit one line in `src/Contoso.Orders.Api/Program.cs` (e.g. the `status` text stays, add a comment), then `docker build -t contoso/orders-api:dev .`: the BuildKit output with the **restore** step `CACHED` and the publish step re-run. 2) `docker images contoso/orders-api` (size column visible). 3) `docker run -d --name orders -p 127.0.0.1:8080:8080 -v orders-data:/data contoso/orders-api:dev`, then `curl -s localhost:8080/healthz` → `"status":"ok"`, `"database":"Sqlite"`, `"user":"app"`, `"inContainer":true`, `"os"` Ubuntu 24.04. Two or three captures stitched is fine. |
| `stack` | `screens/stack.jpg` | 1) `docker rm -f orders`, then `docker compose up -d` **without** `.env`: the error naming `MSSQL_SA_PASSWORD` and `set MSSQL_SA_PASSWORD in .env`. 2) Off camera: `cp .env.example .env` and set the password. 3) `docker compose up --build -d`, then `docker compose ps` showing `db` **(healthy)** and `api` Up (run `ps` again until healthy; with `start_period: 30s` it takes about half a minute). 4) `curl -s localhost:8080/healthz` → `"database":"SqlServer"`. 5) Docker Desktop → Containers: the `contoso-orders` group expanded with `api` and `db`. |
| `watch` | `screens/watch.jpg` | VS Code (WSL window on `~/src/orders-app`), `Program.cs` left, integrated terminal right running `docker compose watch`. Add a field to `/healthz` (e.g. `version = "watch-demo"`), save; capture the terminal while Compose rebuilds `api` and recreates the container, then `curl -s localhost:8080/healthz` with the new field. Second capture: `docker compose exec api sh` failing because the chiseled image has no shell (capture the real error text). Revert the edit afterwards. |

## Checks to make during recording (fix the README if any differs)
1. `docker build` succeeds with `COPY --chown=$APP_UID:$APP_UID` (BuildKit must expand `$APP_UID` from the base
   image; if it reports an unknown user, change it to `--chown=1654:1654`, the UID Learn documents, rerun the tests
   and update README).
2. The single-container run can write: `curl -s -X POST localhost:8080/orders -H 'Content-Type: application/json'
   -d '{"customer":"Alex Demo","total":19.99}'` returns 201; `docker rm -f orders` and run it again with the same
   volume: `GET /orders/<id>` still returns it. This confirms the new `orders-data` volume started with the app user's
   ownership of `/data`.
3. `docker compose exec api sh` fails (no shell). Record the exact message for the edit.
4. Persistence in Compose: `docker compose down` (no `-v`), `docker compose up -d`, the order posted through the
   stack is still there.
5. `docker compose config` (with `.env`) prints the connection string with `TrustServerCertificate=True;
   Password=...`: **don't capture it** (it contains the password), just confirm it renders.
6. `docker image inspect contoso/orders-api:dev --format '{{.Config.User}}'` shows the non-root user (expected
   `1654`, or the literal `$APP_UID` depending on how BuildKit records it); note which in the README.

## Masking
- The `.env` file and the password: never open `.env` on camera, never run `docker compose config` on camera,
  never `docker inspect` the `db` container (its `Env` contains the password).
- WSL user name in paths and prompts (`export PS1='$ '`; open folders from `~/src`).
- Docker Desktop account avatar (top right) and VS Code Accounts menu.

## Tear-down
1. `docker compose down -v` (removes containers, network and `contoso-orders_mssql-data`).
2. `docker rm -f orders 2>/dev/null; docker volume rm orders-data`.
3. `docker image rm contoso/orders-api:dev` (and the base images if disk space is needed:
   `docker image rm mcr.microsoft.com/mssql/server:2025-latest`).
4. Optional: `docker builder prune` to drop the build cache, including the NuGet cache mount.
5. `rm -rf ~/src/orders-app` (this deletes `.env` too).
