# MG Lab #01 — Power Platform ALM that actually works

Managed solutions, source control and GitHub Actions.

📺 Video: *link added on release*

## The target

```
DEV (unmanaged) → Git (unpacked source, PR review) → Build (managed + Solution Checker) → TEST (auto) → PROD (approved)
```

One artifact, built once, promoted through every environment.

## Five rules

1. **Three environments, minimum** — DEV, TEST, PROD, all with Dataverse. Use the free Power Apps Developer Plan for personal DEV.
2. **Your own publisher and prefix** — never build in the Default solution.
3. **Managed outside DEV** — unmanaged only where makers build.
4. **Environment variables + one deployment settings file per environment** — nothing environment-specific inside apps and flows.
5. **Git + pipeline** — nobody imports into production by hand.

## What's in this folder

| File | Purpose |
|------|---------|
| `workflows/export-unpack.yml` | On demand: export unmanaged + managed from DEV, unpack (Both), open a pull request |
| `workflows/build-release.yml` | On push to `main`: pack managed, run Solution Checker, import to TEST, then PROD after approval |
| `settings/deployment-settings.test.json` / `.prod.json` | Environment variable values and connection references per environment |
| `scripts/local-setup.ps1` | The same steps locally with the pac CLI |
| `script.yaml` | Episode script (used by the video pipeline) |

## Set it up in your own repo

1. **Service principal**: app registration in Microsoft Entra ID → client secret.
2. **Application user** for that app in DEV, TEST and PROD, with a least-privilege security role that can import solutions.
3. **GitHub repository variables**: `PP_APP_ID`, `PP_TENANT_ID`, `DEV_ENVIRONMENT_URL`.
4. **GitHub secret**: `PP_CLIENT_SECRET` (rotate it; never commit it).
5. **GitHub environments** `test` and `production`, each with variable `ENVIRONMENT_URL`; add *Required reviewers* to `production`.
6. Copy both workflows to `.github/workflows/`, set `SOLUTION_NAME`, run **export-and-unpack**, merge the PR, watch **build-and-release**.
7. Generate real settings files with `pac solution create-settings` and fill in the connection IDs from each target environment.

## Notes

- `stage-and-upgrade: true` applies the upgrade in one step, so components removed in DEV are removed downstream.
- `check-solution` with `fail-on-analysis-error: true` makes Solution Checker a real quality gate.
- The actions are pinned to `@v1`; pin to a commit SHA if your policy requires it.

## References

- [GitHub Actions for Microsoft Power Platform](https://learn.microsoft.com/power-platform/alm/devops-github-available-actions)
- [Pre-populate connection references and environment variables](https://learn.microsoft.com/power-platform/alm/conn-ref-env-variables-build-tools)
- [pac solution reference](https://learn.microsoft.com/power-platform/developer/cli/reference/solution)
