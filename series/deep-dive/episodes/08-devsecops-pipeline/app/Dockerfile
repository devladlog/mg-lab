# syntax=docker/dockerfile:1
# Both base images are pinned by digest (read from mcr.microsoft.com on 2026-11-21); Dependabot's docker ecosystem
# proposes new digests as pull requests, so the pin does not turn into a stale image.

FROM mcr.microsoft.com/dotnet/sdk:10.0@sha256:bef136a371963aaa46ec97882845ef6f54dec15728bb4b128b1c2a400ffbc9b4 AS build
WORKDIR /src
COPY Directory.Build.props ./
COPY src/PurchaseStatus.Api/PurchaseStatus.Api.csproj src/PurchaseStatus.Api/packages.lock.json src/PurchaseStatus.Api/
RUN dotnet restore src/PurchaseStatus.Api --locked-mode
COPY src/ src/
RUN dotnet publish src/PurchaseStatus.Api -c Release -o /out --no-restore -p:UseAppHost=false

# Chiseled: no shell, no package manager, non-root user "app" (Learn: .NET container images).
FROM mcr.microsoft.com/dotnet/aspnet:10.0-noble-chiseled@sha256:7c625e44e5d588b4d7b2a913e94ca4bd5098ce47442da404829e4c7936a764e1 AS final
WORKDIR /app
COPY --from=build /out .
ENV ASPNETCORE_HTTP_PORTS=8080
EXPOSE 8080
# 1654 is the UID of the non-root user "app" in the .NET images; numeric so runAsNonRoot checks and hadolint DL3066 can resolve it.
USER 1654
ENTRYPOINT ["dotnet", "PurchaseStatus.Api.dll"]
