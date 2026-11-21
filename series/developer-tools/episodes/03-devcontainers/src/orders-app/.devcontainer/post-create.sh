#!/usr/bin/env bash
# postCreateCommand: runs inside the dev container after it is created, and again after every rebuild,
# so every step must be safe to repeat.
set -euo pipefail
cd "$(dirname "$0")/.."

# 1. The NuGet cache is a named volume (see "mounts"). Docker creates new volumes owned by root,
#    and the tools run as the non-root remoteUser, so take ownership once.
nuget="${NUGET_PACKAGES:-$HOME/.nuget/packages}"
if [ -d "$nuget" ] && [ ! -w "$nuget" ]; then
  echo "Taking ownership of $nuget"
  sudo chown -R "$(id -u):$(id -g)" "$nuget"
fi

# 2. Episode 1 guardrails: versioned hooks and safe Git defaults (hooks are not copied by git clone).
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  bash scripts/setup-dev.sh
else
  echo "Not a Git work tree: skipping hook setup"
fi

# 3. Restore once now, so the first build, the test explorer and IntelliSense don't wait for it.
dotnet restore OrdersApp.slnx --verbosity quiet

# 4. One line that proves which toolchain this container has.
summary="dotnet $(dotnet --version)"
command -v python3 >/dev/null && summary+=" | $(python3 --version)"
command -v gh >/dev/null && summary+=" | gh $(gh --version | head -n1 | awk '{print $3}')"
echo "Dev container ready: $summary"
