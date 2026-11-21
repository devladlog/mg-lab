# Microsoft Purview audit

As of 2026-11-21 10:00 UTC. 3 sensitivity labels, 1 label policies, 2 DLP policies, 2 DLP rules, 2 retention labels, 13 findings.

| Severity | Target | Rule | Detail |
|---|---|---|---|
| High | DLP rule: HR - secret label | LabelConditionWithTeams | Policy 'Old - HR labels' includes Teams, which can't define content by sensitivity label, so the label condition can't work. Move the rule to a policy without Teams. |
| High | Retention policy: Legal records | DistributionError | DistributionStatus 'Error'. Check DistributionResults and fix the errors (warnings can be ignored). |
| Medium | DLP policy: Contoso - Card numbers | SimulationOverdue | In TestWithNotifications for 32 days. A simulation runs for up to 15 days: review the results, then promote it or re-run the simulation. |
| Medium | DlpPolicy: Contoso - Confidential label | NotDeployed | In compliance.json but not in the tenant. |
| Medium | DlpRule: Card numbers - high count | NotDeployed | In compliance.json but not in the tenant. |
| Medium | DlpRule: Confidential - external | NotDeployed | In compliance.json but not in the tenant. |
| Medium | Retention label: Contoso Contract - 7 years | RetentionLabelNotPublished | Not published by any retention label policy (or auto-applied). |
| Medium | Sensitivity label: Legacy-Secret | LabelNotPublished | Not in any label policy, so nobody can apply it. |
| Medium | SensitivityLabel: Contoso-Confidential | NotDeployed | In compliance.json but not in the tenant. |
| Low | LabelPolicy: Contoso labels - pilot | Drift | Tenant policy doesn't publish: Contoso-Confidential. |
| Info | Retention label: Legal Hold Record | RecordLabel | Record label: once applied to content, it cannot be removed. |
| Info | Retention policy: Contoso retention labels | DistributionPending | Still distributing. Wait until it is no longer Pending before you change it. |
| Info | Retention policy: Legal records | PreservationLock | Preservation Lock is on: no one, including an administrator, can turn it off or make it less restrictive. |
