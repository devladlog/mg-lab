#!/usr/bin/env bash
# Builds the image with the .NET SDK and pushes it to ACR. No Dockerfile, no Docker daemon:
# az acr login --expose-token gives an Entra-based registry token; the SDK reads it from two env vars.
# The base image is the copy imported into the same registry, so one credential covers both registries
# the SDK talks to (Learn: the env-var credentials are used for the source AND the destination registry).
# Usage: infra/push-image.sh <acr-name> <version>     e.g. infra/push-image.sh acrordersxxxx 1.0.0
set -euo pipefail
ACR=${1:?usage: push-image.sh <acr-name> <version>}
VERSION=${2:?usage: push-image.sh <acr-name> <version>}
HERE=$(cd "$(dirname "$0")" && pwd)
LOGIN=$(az acr show --name "$ACR" --query loginServer -o tsv)

if ! az acr repository show --name "$ACR" --image dotnet/aspnet:10.0 --output none 2>/dev/null; then
  echo "== import base image (no Docker needed)"
  az acr import --name "$ACR" --source mcr.microsoft.com/dotnet/aspnet:10.0 --image dotnet/aspnet:10.0
fi

echo "== build + push $LOGIN/contoso/orders-api:$VERSION"
DOTNET_CONTAINER_REGISTRY_UNAME=00000000-0000-0000-0000-000000000000 \
DOTNET_CONTAINER_REGISTRY_PWORD=$(az acr login --name "$ACR" --expose-token --query accessToken -o tsv) \
  dotnet publish "$HERE/../src/Contoso.Orders.Api" -c Release /t:PublishContainer \
    -p Version="$VERSION" \
    -p ContainerRegistry="$LOGIN" \
    -p ContainerBaseImage="$LOGIN/dotnet/aspnet:10.0"

az acr repository show-tags --name "$ACR" --repository contoso/orders-api -o table
