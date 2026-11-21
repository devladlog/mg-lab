# DEVLADLOG Deep Dive #16 — Enterprise Reporting Platform (Power BI semantic model as code, row-level security, promotion, governance)

Episode 15 ended with a gold layer for Contoso's purchase requests (episodes 3, 4, 7 and 11) in Synapse serverless SQL. This episode is
the reporting layer on top of it: **one semantic model that every department report shares, where each department sees only its own
requests**, kept in Git as text, tested in a build, promoted through stages and checked against a governance policy.

```
gold views (episode 15)   Semantic model (TMDL, in Git)         Fabric deployment pipeline          Power BI service
gold.FactPurchaseRequest  FactPurchaseRequest  measures   ──►   Development ──► Test ──► Production   workspace per stage
gold.DimDepartment   ──►  DimDepartment ◄─ RLS role            parameter rules swap SynapseServer    Viewers: row-level security applies
                          DimDate (marked date table)           deploy request via the REST API       Endorsement: Promoted / Certified
                          SecurityMap (hidden, who sees what)                                         Scanner API ──► policy.json ──► findings
                          dotnet test (TOM) + Pester: the build
```

- **The model is text.** `model/ContosoReporting.SemanticModel/` is a Power BI project semantic model folder in TMDL format
  (`definition.pbism` version 4.0 plus a `definition/` folder). Tables, measures, relationships, the role and three parameters are separate files, so a change is a readable diff.
- **One dynamic role, on the dimension.** `Department Reader` filters `DimDepartment` to the departments listed for `USERPRINCIPALNAME()` in the hidden
  `SecurityMap` table; the filter reaches the facts through the relationship. The mapping table filters itself to the caller. No static department literals, no second rule on the fact table.
- **Measures are the only way in.** Implicit measures are discouraged, the numeric columns are hidden, every measure has a description, format string and folder, ratios use `DIVIDE`.
- **A date table the model builds** (contiguous, marked, month sorted by number): episode 15 left the date dimension out on purpose.
- **Parameters, not literals.** `SynapseServer`, `SynapseDatabase` and `UpnDomain` are Text parameters, so a deployment *parameter rule* can change the endpoint per stage (Learn: data source rules cannot be used on a model whose data source uses parameters, parameter rules can).
- **Governance as code.** `governance/policy.json` + `Get-GovernanceFindings` evaluate scanner API output: production models certified, labelled, on a capacity, certified only by the allowed people, reports bound to a certified model, no content in personal workspaces.

| Path | What it is |
|---|---|
| `model/ContosoReporting.SemanticModel/definition.pbism`, `definition/` | The semantic model (TMDL): `model.tmdl`, `database.tmdl`, `expressions.tmdl`, `relationships.tmdl`, `tables/*.tmdl`, `roles/DepartmentReader.tmdl` |
| `test/ModelTests/` | xUnit tests (23) that load the folder with `TmdlSerializer` (Microsoft.AnalysisServices 19.120.1) and check structure, measures, security and serialisation |
| `scripts/ReportingGovernance.psm1` | `New-ScanRequest`, `Get-GovernanceFindings`, `Get-RlsExpectedCounts`, `New-ExecuteQueriesBody`, `Invoke-RlsCheck`, `New-DeployRequest`, `Invoke-PipelineDeploy` |
| `tests/ReportingGovernance.Tests.ps1` | Pester tests (23) for the module, with the REST calls mocked |
| `governance/policy.json`, `governance/fixtures/` | The policy, a fictional scanner result, the expected request counts per department, the mapping as CSV |
| `script.yaml`, `demo.md` | Narration (15 scenes) and the lab shot list |

## Test locally (no tenant, no capacity)

```bash
cd series/deep-dive/episodes/16-enterprise-reporting-platform
dotnet test test/ModelTests/ModelTests.csproj -m:1     # 23 passed (needs network once for NuGet)
pwsh -NoProfile -c 'Invoke-Pester ./tests'             # Tests Passed: 23
```

What the .NET tests prove: the TMDL parses with the same serializer Power BI Desktop and Fabric tooling use, the model round-trips to TMDL and converts to TMSL JSON,
every `Table[Column]` and `[Measure]` reference in measures and role filters resolves (checked by a small static checker, not a DAX parser), every measure is documented,
the role filters the dimension by `USERPRINCIPALNAME()` and not the fact, the mapping table is hidden and has no relationships, no GUID or tenant name is committed.
Mutation checks done: a typo in a measure column and a `USERNAME()` in the role each fail a test. The Pester tests prove the policy logic against the fixture (8 findings), the
request builders (batch of at most 100 workspaces, deploy body, 300-item and 1,024-character limits) and that `-WhatIf` calls nothing.
The mapping inside the TMDL and the mapping CSV used for the expected counts are checked against each other.

## Not verified in the lab yet

Nothing below has run against a tenant. Record each outcome here after the recording.

- Opening the TMDL folder in Power BI Desktop and publishing it (see `demo.md`: the project is created in Desktop first and its semantic model folder replaced).
- That Power BI loads the M parameters, the calculated date table and the inline `#table` as written, and that `Sql.Database` against the serverless endpoint behaves like the Azure Synapse Analytics SQL connector (credentials, refresh).
- The role in the service: assigning members, *Test as role*, and the row counts from `Invoke-RlsCheck` (expected: 240, 209, 310 and 330 on the sample counts; with real episode 15 data the counts come from `gold.FactPurchaseRequest`: update `governance/fixtures/requests-by-department.csv`).
- The deployment pipeline: stage creation, parameter rule on `SynapseServer`, the REST deploy call and its long-running operation, whether the token for `Invoke-PipelineDeploy` works for the lab user.
- The scanner API run (tenant settings for metadata scanning must be enabled by an admin) and the shape of a real `scanResult` against `Get-GovernanceFindings`.
- Endorsement and certification: needs the Certification tenant setting and a security group; the lab user must be in it.
- A free-licence viewer on the Fabric trial capacity: Learn says free users view only on F64 or larger or Premium; the trial may be F4.
- Fabric Git integration and the Create Semantic Model REST API were not built or tested; only the files are Git-ready.

## What we learned / gotchas

- **RLS applies to Viewers only.** Learn: it does not restrict workspace Admin, Member or Contributor. Test with a user who is a Viewer; `labadmin` proves nothing.
- **Deployment does not copy role members, endorsement, refresh schedule or data source credentials** (Learn, "Item properties that are not copied"): after the first deploy to a stage, assign members, endorse and set credentials again.
- **`impersonatedUserName` on executeQueries** applies RLS for that user, needs Build permission and the tenant setting *Dataset Execute Queries REST API*; service principals are not supported on models with RLS; one query returns one table.
- **Security filters are single-direction by default** (Learn); "Apply security filter in both directions" exists but Learn warns it can hurt performance. This model does not need it: the filter sits on the dimension and the mapping table has no relationships.
- **A free licence is not enough everywhere.** Free users view Power BI content on F64+ or Premium capacity with the Viewer role; the Fabric trial can be an F4.
- **Certification is not self-service.** Only members of the security groups chosen in the Certification tenant setting can certify; anyone with write access can promote.
- **getInfo takes 1 to 100 workspaces per call**, 500 requests per hour, 16 simultaneous.
- **The mapping table here is inline M** so the episode is self-contained. A real one comes from a governed source (HR data, an Entra group export), refreshed with the model.
- **Placeholders must be replaced:** the three parameters in `expressions.tmdl` are `REPLACE-WITH-...` on purpose; deployment rules and the demo set the real values, never the repository.

## References

- TMDL overview and API: https://learn.microsoft.com/analysis-services/tmdl/tmdl-overview · how-to: https://learn.microsoft.com/analysis-services/tmdl/tmdl-how-to
- TmdlSerializer.DeserializeDatabaseFromFolder: https://learn.microsoft.com/dotnet/api/microsoft.analysisservices.tabular.tmdlserializer.deserializedatabasefromfolder
- Power BI Desktop project semantic model folder (definition.pbism version 4.0 and TMDL): https://learn.microsoft.com/power-bi/developer/projects/projects-dataset
- Row-level security with Power BI (Viewers only, dynamic RLS, Security page, bi-directional note): https://learn.microsoft.com/fabric/security/service-admin-row-level-security
- Execute Queries REST API (`impersonatedUserName`, limits, service principals): https://learn.microsoft.com/rest/api/power-bi/datasets/execute-queries
- Deployment pipelines, Deploy Stage Content REST API: https://learn.microsoft.com/rest/api/fabric/core/deployment-pipelines/deploy-stage-content · automation: https://learn.microsoft.com/fabric/cicd/deployment-pipelines/pipeline-automation-fabric
- Deploy content (full, selective): https://learn.microsoft.com/fabric/cicd/deployment-pipelines/deploy-content · the process (properties not copied): https://learn.microsoft.com/fabric/cicd/deployment-pipelines/understand-the-deployment-process
- Deployment rules (data source and parameter rules): https://learn.microsoft.com/fabric/cicd/deployment-pipelines/create-rules
- Scanner API: https://learn.microsoft.com/rest/api/power-bi/admin/workspace-info-post-workspace-info · https://learn.microsoft.com/rest/api/power-bi/admin/workspace-info-get-scan-result
- Endorsement (promotion and certification): https://learn.microsoft.com/power-bi/collaborate-share/service-endorsement-overview · enable certification: https://learn.microsoft.com/fabric/admin/endorsement-certification-enable
- Fabric licenses and capacity (free users and F64): https://learn.microsoft.com/fabric/enterprise/licenses · free-user features: https://learn.microsoft.com/power-bi/fundamentals/end-user-features
- Fabric trial (60 days, F4 or F64): https://learn.microsoft.com/fabric/fundamentals/fabric-trial
