# syntax=docker/dockerfile:1
# Built in the cloud with `az acr build` (no Docker daemon needed on the laptop). Base image digests are the ones
# read from mcr.microsoft.com for episode 8 on 2026-11-21.
FROM mcr.microsoft.com/dotnet/sdk:10.0@sha256:bef136a371963aaa46ec97882845ef6f54dec15728bb4b128b1c2a400ffbc9b4 AS build
WORKDIR /src
COPY FinanceReview.Worker.csproj ./
RUN dotnet restore
COPY *.cs ./
RUN dotnet publish -c Release -o /out --no-restore -p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0-noble-chiseled@sha256:7c625e44e5d588b4d7b2a913e94ca4bd5098ce47442da404829e4c7936a764e1 AS final
WORKDIR /app
COPY --from=build /out .
ENV ASPNETCORE_HTTP_PORTS=8080
EXPOSE 8080
# numeric UID of the non-root "app" user in the .NET images, so Kubernetes runAsNonRoot can verify it
USER 1654
ENTRYPOINT ["dotnet", "FinanceReview.Worker.dll"]
