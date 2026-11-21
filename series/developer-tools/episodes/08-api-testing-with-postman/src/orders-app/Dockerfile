# syntax=docker/dockerfile:1
# Contoso orders API. Build with the .NET SDK image, run on the small chiseled ASP.NET image.
#   docker build -t contoso/orders-api:dev .
#   docker run --rm -p 127.0.0.1:8080:8080 -v orders-data:/data contoso/orders-api:dev

# ---- build stage: SDK, never shipped ---------------------------------------------------------
# Tag for humans, digest for reproducible builds (let Dependabot or Renovate bump both).
FROM mcr.microsoft.com/dotnet/sdk:10.0-noble@sha256:bef136a371963aaa46ec97882845ef6f54dec15728bb4b128b1c2a400ffbc9b4 AS build
ARG TARGETARCH
WORKDIR /src

# 1. Restore from the project file and its lock file only: reused until a package changes.
#    --locked-mode: the exact graph in packages.lock.json, or the build fails (episode 5).
COPY global.json Directory.Build.props ./
COPY src/Contoso.Orders.Api/Contoso.Orders.Api.csproj src/Contoso.Orders.Api/packages.lock.json src/Contoso.Orders.Api/
RUN --mount=type=cache,id=nuget,target=/root/.nuget/packages \
    dotnet restore src/Contoso.Orders.Api/Contoso.Orders.Api.csproj -a $TARGETARCH --locked-mode

# 2. Then the source. Editing a .cs file only re-runs from here.
COPY src/ src/
RUN --mount=type=cache,id=nuget,target=/root/.nuget/packages \
    dotnet publish src/Contoso.Orders.Api/Contoso.Orders.Api.csproj -c Release \
      -a $TARGETARCH --no-restore -o /app \
 && mkdir /data

# ---- final stage: what actually runs ---------------------------------------------------------
# Chiseled = no shell, no package manager, non-root by default.
# "-extra" adds ICU and tzdata.
FROM mcr.microsoft.com/dotnet/aspnet:10.0-noble-chiseled-extra@sha256:cae5b962bfb786606def03d250c6a645cc98839095c89e806e4bd8978a68115b AS final
WORKDIR /app
COPY --from=build /app .
# An empty /data owned by the app user, for SQLite (mount a volume here to keep the data).
COPY --from=build --chown=$APP_UID:$APP_UID /data /data
# The commit this image was built from, reported by /healthz (CI passes --build-arg APP_VERSION=<sha>).
ARG APP_VERSION=dev
ENV Database__Provider=Sqlite \
    ConnectionStrings__Orders="Data Source=/data/orders.db" \
    App__Version=$APP_VERSION
USER $APP_UID
EXPOSE 8080
ENTRYPOINT ["./Contoso.Orders.Api"]
