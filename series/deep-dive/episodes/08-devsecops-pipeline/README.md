# DEVLADLOG Deep Dive #8: DevSecOps pipeline (GitHub Actions, Azure DevOps, container security)

Contoso's purchase-request platform (episodes 3, 4 and 7) is now a small ASP.NET Core service, `PurchaseStatus.Api`
(`GET /api/status/{id}`, `GET /healthz`), shipped as a container. The question for this episode: **what has to be true
before an image built from a pull request is allowed to reach Azure Container Apps**, with no stored cloud secret
and a trail you can audit later?

```
pull request / push to main
  ├─ build-test     dotnet restore --locked-mode (NuGet Audit, NU1903/NU1904 are errors) -> build -> test
  ├─ secrets-scan   detect-secrets against a committed baseline
  ├─ codeql         CodeQL C#, security-extended, build-mode none
  ├─ dependency-review (PR only)   fails on high severity
  └─ container      hadolint -> docker build -> Trivy JSON -> vuln_gate.py (waivers expire) -> SBOM -> save image
publish-and-deploy  (main only, environment prod-lab = reviewer approval, needs container + codeql)
  azure/login with OIDC (federated credential, no secret) -> push -> attest provenance -> az containerapp update @digest
```

| Path (under `app/`) | What it is |
|---|---|
| `.github/workflows/ci.yml` | The pipeline above. Every action pinned to a commit SHA, `permissions: {}` at the top, least privilege per job, `persist-credentials: false` |
| `.github/dependabot.yml` | github-actions, nuget, docker, pip; 7-day cooldown on each |
| `azure-pipelines.yml` | The same gates on Azure Pipelines; service connection with workload identity federation; `prod-lab` environment approval |
| `Dockerfile`, `.dockerignore` | SDK and chiseled ASP.NET 10 base images pinned by digest, numeric non-root user 1654 |
| `src/PurchaseStatus.Api`, `tests/PurchaseStatus.Api.Tests` | The service (security headers, no stack traces) and 7 xUnit tests. NuGet lock files committed |
| `security/vuln_gate.py` | Stdlib-only gate over Trivy JSON: blocks fixable CRITICAL/HIGH, honours `waivers.json` (owner, reason, expiry within 90 days); expired waivers block; stale waivers are reported |
| `security/tests/` | 14 gate tests (synthetic Trivy-format fixtures) and 17 pipeline-policy tests |
| `security/requirements-ci.txt` | detect-secrets and hadolint, hash-pinned (`pip install --require-hashes`) |
| `infra/main.bicep`, `main.bicepparam` | ACR Basic (admin off), deploy identity with a federated credential for the environment only, AcrPush, Contributor on the app only, pull identity with AcrPull, Log Analytics, Container Apps (scale to zero) |

## Test locally (no Azure, no Docker)

```bash
cd app
dotnet restore PurchaseStatus.slnx --locked-mode && dotnet test PurchaseStatus.slnx      # Passed: 7
python -m pytest security -q                                                            # 31 passed (14 gate + 17 policy)
actionlint .github/workflows/ci.yml                                                     # clean
zizmor --offline --persona auditor .github                                              # no findings
hadolint Dockerfile                                                                     # clean
git ls-files -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline             # exit 0; a planted key exits non-zero
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep        # no warnings
```

The policy tests are mutation-checked: unpinning an action, enabling the ACR admin user, or widening the federated
subject each makes a named test fail.

## What is NOT verified here (needs tenant, GitHub, Azure DevOps or a Docker host)

- **No Docker daemon in the build container.** The image was never built and **Trivy was never run**. `vuln_gate.py`
  is tested on hand-made files in the documented Trivy JSON shape (`Results[].Vulnerabilities[]` with `FixedVersion`,
  `Severity`), ids `CVE-0000-xxxx`. Check the first real report against the gate on the first CI run.
- **The workflow has not run on GitHub.** Validated with actionlint and zizmor `--offline`; zizmor's online audits
  (impostor commits, known-vulnerable actions) need the GitHub API and were not run. Action SHAs and input names were read
  from the real repositories with `git ls-remote` and the `action.yml` files at those SHAs.
- **`azure-pipelines.yml` is only YAML-linted**, not checked against the Azure Pipelines schema, never run.
- **`infra/main.bicep` compiles and lints but was never deployed.** Open points for the first deploy: the role assignment
  for AcrPull can take minutes to propagate, so the first Container App create may fail on the registry and need a re-run;
  Contributor scoped to the app is enough for `az containerapp update` in theory, not yet seen.
- The Trivy version (v0.76.2) and the Trivy image digest in the Azure Pipelines file were read from the registry/tags
  on the day; re-read them when you run it.
- CodeQL `build-mode: none` for C# and attestation permissions are as documented, not run.

## What we learned / gotchas

- **A tag is not a pin.** Tags move, so `uses: x@v4` runs whatever the tag points to today. Pin the 40-character SHA and keep
  the tag in a comment; Dependabot updates both. The test fails the build if a tag sneaks in.
- **Dependabot cooldown:** zizmor flags updates without a cooldown; a short delay stops you adopting a release minutes after
  a compromised publish. We use 7 days.
- **`permissions: {}` first.** Jobs then ask for what they need. Only the deploy job gets `id-token: write`.
- **OIDC subject = the environment.** The federated credential trusts
  `repo:<owner>/<repo>:environment:prod-lab`, not the repository or a branch, so only a job that passed the environment's
  reviewer gate can obtain an Azure token. The ids in the environment are identifiers, not secrets.
- **Scan before you push, push what you scanned.** The image is saved as a tarball after the scan, and the deploy job loads
  that tarball, so the bytes pushed are the bytes scanned. Deploy by digest, never by tag.
- **Waivers must expire.** A waiver without owner, reason and a date within 90 days is rejected; once past its date it stops
  hiding the finding. Report-only scanners get ignored; a gate with expiring exceptions does not.
- **Chiseled images** have no shell or package manager, include the non-root `app` user (UID 1654) and need
  `InvariantGlobalization` (no ICU). Use the numeric `USER 1654`: Kubernetes `runAsNonRoot` needs a UID and hadolint DL3066 flags names.
- **NuGet:** lock files plus `--locked-mode` make restore fail on drift; NuGet Audit warnings NU1903 and NU1904 are errors
  here. A `--` inside an XML comment in `Directory.Build.props` is invalid XML (MSB4024), which cost us a run.
- **Azure DevOps:** use the workload identity federation service connection, not a client secret. Learn says the older
  Azure DevOps token issuer is being retired (check the date on the page before you rely on it).

## References

- [Use the Azure Login action with OpenID Connect](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect) · [Federated credential on a user-assigned managed identity](https://learn.microsoft.com/entra/workload-id/workload-identity-federation-create-trust-user-assigned-managed-identity)
- [Azure Resource Manager service connection (workload identity federation)](https://learn.microsoft.com/azure/devops/pipelines/library/connect-to-azure) · [Auditing NuGet packages](https://learn.microsoft.com/nuget/concepts/auditing-packages)
- [.NET container images (chiseled, invariant globalization)](https://learn.microsoft.com/dotnet/core/docker/container-images) · [What's new in containers for .NET 8 (non-root user, UID 1654)](https://learn.microsoft.com/dotnet/core/whats-new/dotnet-8/containers) · [Introduction to .NET and Docker (users)](https://learn.microsoft.com/dotnet/core/docker/introduction)
- [Azure Container Registry roles (AcrPush, AcrPull)](https://learn.microsoft.com/azure/container-registry/container-registry-roles) · [Container Apps: image pull with managed identity](https://learn.microsoft.com/azure/container-apps/managed-identity-image-pull)
- Blog: [DevSecOps pipeline: Azure DevOps, GitHub Actions and container security](https://www.devladlog.com/articles/deep-dive/2025-05-19-devsecops-pipeline-azure-devops-github-actions-container-security/)
