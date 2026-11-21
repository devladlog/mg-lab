# DEVLADLOG Deep Dive #9: Zero Trust network architecture (Conditional Access, Intune, private endpoints)

Contoso's purchase platform (episodes 3, 4 and 7) now holds real money decisions. The question for this episode: **what has
to be true before a request reaches it**, no matter where it comes from? Three checks, each one in code you can test:
how strongly the user proved who they are (Conditional Access), whether the device is healthy and managed (Intune
compliance), and whether there is a public door at all (private endpoint, deny by default).

```
sign-in ─► Conditional Access (3 policies, report-only first)
           ├─ CT001 block legacy authentication          pilot group, break-glass excluded
           ├─ CT002 admin roles ─► phishing-resistant authentication strength
           └─ CT003 Office 365 from Windows ─► compliant device + MFA, 12 h sessions
                                   ▲
                       Intune compliance policy "CT Windows corporate baseline" (BitLocker, secure boot, OS build)
data   ─► Key Vault (public access Disabled) ◄── private endpoint ◄── workload VM (managed identity, no public IP,
          10.60.0.0/24 network, NSG: deny-all-inbound 4096, deny-internet-outbound 4000)       role: Secrets User)
```

Scope on purpose: Defender and Sentinel are **not** in this episode (the blog Complete Guide covers them; I could not
run or verify those snippets without a Defender-for-Endpoint tenant). The device signal here is Intune compliance only.

| Path | What it is |
|---|---|
| [`entra/policies/`](entra/policies) | Three Conditional Access policies as Graph request bodies with `{{tokens}}` for group and strength ids. All `enabledForReportingButNotEnforced` |
| [`intune/windows-compliance.json`](intune/windows-compliance.json) | `windows10CompliancePolicy` (Graph v1.0): password, OS build, BitLocker, secure boot, code integrity, one `block` action after 24 h |
| [`scripts/ZeroTrust.psm1`](scripts/ZeroTrust.psm1) | `Expand-CaTemplate`, `Test-CaPolicy` (linter), `Publish-CaPolicy` (create or update by name, `-WhatIf`, `-Enforce`), `Resolve-AuthStrengthId`, `Initialize-LabGroup`, `Publish-CompliancePolicy`, `Get-CaReportOnlyImpact` |
| [`scripts/Deploy-ZeroTrust.ps1`](scripts/Deploy-ZeroTrust.ps1) | Glue: groups, strength lookup, three policies, compliance policy + assignment. `-WhatIf` supported. Needs tenant |
| [`infra/main.bicep`](infra/main.bicep), [`main.bicepparam`](infra/main.bicepparam) | VNet + NSG, Key Vault (no public access, RBAC), private endpoint + private DNS zone, Ubuntu VM with system identity and no public IP, one role assignment |
| [`scripts/Test-PrivateAccess.ps1`](scripts/Test-PrivateAccess.ps1), [`vm-check.sh`](scripts/vm-check.sh) | The outside-versus-inside demo: DNS, Key Vault call from the laptop (Forbidden), then the same checks run on the VM via `az vm run-command invoke` (token from IMDS, secret read, no internet) |
| [`tests/`](tests) | 57 Pester tests (44 module/policy, 13 infra) |

## Test locally (no Azure, no tenant)

```bash
pwsh -NoProfile -c 'Invoke-Pester ./tests'        # Tests Passed: 57, Failed: 0 (about 1 minute)
bicep build infra/main.bicep --stdout > /dev/null && bicep lint infra/main.bicep   # clean
bicep build-params infra/main.bicepparam --stdout > /dev/null
```

What the tests do and do not prove:

- **Policies:** every template is expanded with dummy GUIDs and must pass `Test-CaPolicy` (report-only, break-glass group
  excluded, targets somebody, values from the documented Graph enums, never `mfa` together with an authentication
  strength, `block` never combined). Negative tests feed the linter bad policies.
- **Publish logic** runs against a **mock** of `Invoke-MgGraphRequest` (create vs update by name, `-WhatIf` makes no write,
  `-Enforce` is the only path to `enabled`, two policies with the same name stop the run, paging in the sign-in report).
  The suite was also run with the real `Microsoft.Graph.Authentication` 2.41.2 module loaded, so the mock is checked
  against the real cmdlet's parameters. It proves our logic and request shapes, **not** that the tenant accepts them.
- **Compliance JSON** may only use property names Learn lists for `windows10CompliancePolicy` v1.0 and must have exactly one `block` action.
- **Bicep** is compiled with the real `bicep build` and the ARM output is asserted (public access, private endpoint group id and
  DNS zone, NSG 4096, no public IP, SSH key only, one role assignment). Not deployed here: no Azure access in this container.
- `vm-check.sh` is syntax-checked (`bash -n`); `Test-PrivateAccess.ps1 -PrintOnly` is tested.
- Tested with PowerShell 7.6, Pester 6.2.0, Bicep CLI current in the container.

## Deploy and run (needs the lab tenant and Azure subscription)

Full runbook, costs, masking and tear-down in [`demo.md`](demo.md). Short version:

```powershell
Connect-MgGraph -Scopes Policy.ReadWrite.ConditionalAccess,Policy.Read.All,Group.ReadWrite.All,DeviceManagementConfiguration.ReadWrite.All
./scripts/Deploy-ZeroTrust.ps1 -WhatIf       # reads only
./scripts/Deploy-ZeroTrust.ps1               # creates groups, 3 report-only policies, the compliance policy
az group create -n rg-mglab-deep-dive-09 -l westeurope
az deployment group create -g rg-mglab-deep-dive-09 -f infra/main.bicep -p adminPublicKey="$(cat ./zt-lab.pub)"
./scripts/Test-PrivateAccess.ps1 -ResourceGroup rg-mglab-deep-dive-09 -VaultName <vault> -VmName vm-mgl09-workload
```

## What we learned / gotchas

- **Report-only is evaluation, not enforcement, and it has four outcomes.** Learn lists *Report-only: Success, Failure,
  User action required, Not applied*; they appear on the **Report-only** tab of a sign-in and in `appliedConditionalAccessPolicies`
  as `reportOnlySuccess`, `reportOnlyFailure`, `reportOnlyInterrupted`, `reportOnlyNotApplied`. `Get-CaReportOnlyImpact` counts exactly these.
- **Report-only compliance checks can prompt non-Windows users.** Learn warns that a report-only policy requiring a compliant
  device can prompt macOS, iOS and Android users to pick a device certificate, repeatedly, until the device is compliant.
  Learn's advice is to exclude those platforms; CT003 goes further and includes **only** `windows`.
- **No compliance policy assigned = compliant, by default.** Intune's tenant-wide setting *Mark devices with no compliance
  policy assigned as* defaults to *Compliant*. A "require compliant device" policy is only as strict as the compliance
  policies actually assigned. The baseline here is assigned to the pilot group.
- **`mfa` and an authentication strength cannot be in the same policy** (Learn: the built-in MFA strength equals the *Require MFA* control).
  CT002 uses the strength only. The built-in strengths are *Multifactor*, *Passwordless MFA* and *Phishing-resistant MFA*
  (Windows Hello for Business or platform credential, FIDO2, certificate-based multifactor). The script looks the strength id
  up by name (`policyType` is `builtIn`) instead of hard-coding a GUID.
- **Authentication strength does not restrict the first sign-in.** Learn: policies run after first-factor authentication, so a
  user can still type a password, but must then satisfy the strength.
- **Targeting.** Office 365 is one app group in Conditional Access (`"Office365"` in Graph); Learn recommends it over targeting
  individual apps because of service dependencies. Legacy clients are `exchangeActiveSync` and `other`. Directory roles are
  targeted by role template id (the five ids are from the Entra permissions reference).
- **Intune compliance:** the Graph `scheduledActionsForRule` must have one and only one `block` action (Learn), and the rule
  name is always `PasswordRequired` ("scheduled actions are created per policy"). Devices that stop reporting are treated as
  non-compliant after the validity period (default 30 days, 1 to 120).
- **The Graph v1.0 `windows10CompliancePolicy` page lists no Defender, TPM or firewall properties** (last updated 2024-09). Those
  exist as settings in the Intune admin center; I did not use them because I could not verify their Graph names, which is why
  this baseline is BitLocker, secure boot, code integrity, encryption, password and OS build.
- **Key Vault soft delete cannot be switched off and the name stays reserved.** Retention is 7 to 90 days, fixed at creation,
  and a soft-deleted vault's name cannot be reused until it expires. The lab uses 7, no purge protection, so tear-down can
  `az keyvault purge`. Purge protection is irreversible.
- **Private endpoint plumbing:** group id `vault`, private DNS zone `privatelink.vaultcore.azure.net`, public forwarders
  `vault.azure.net` and `vaultcore.azure.net` (Learn, private endpoint DNS). The VNet link must not auto-register records.
  With public access Disabled and no allow-list, the service rejects every public request (Learn, Key Vault private link).
- **New VNets default to private subnets** for API versions released after 31 March 2026: no implicit internet egress unless you add an
  explicit outbound method (Learn, default outbound access). The Bicep sets `defaultOutboundAccess: false` explicitly and
  also denies `Internet` outbound in the NSG, so the demo does not depend on that default.
- **Bicep linter** flagged a literal admin user name (`adminusername-should-not-be-literal`): it is a parameter now.
- **Strict mode caught real bugs in my first draft:** an empty `[string[]]` return unrolls to nothing (so `.Count` failed) and
  `Invoke-MgGraphRequest` returns hashtables, where a missing key such as `'@odata.nextLink'` throws under strict mode: use the indexer.
- **Not verified in the lab yet (needs tenant/subscription):** that the Graph accepts `grantControls.authenticationStrength: { id }`
  in the POST body exactly as written (Learn documents the relationship but I found no request sample; the tenant will say on
  first deploy); that the Key Vault secret resource deploys while public access is Disabled (it is a management-plane call, but I
  did not find it stated on Learn); `Standard_B1s` availability and the VM run-command output shape; how long a newly enrolled
  Windows 11 VM takes to report compliance; that the report-only tab shows what the demo narration says (the recorder must change the
  narration if it does not); the `$filter=createdDateTime ge ...` sign-in query at your sign-in volume (it pages, but a busy tenant needs more than the lab).

## References

- [Create conditionalAccessPolicy (Graph)](https://learn.microsoft.com/graph/api/conditionalaccessroot-post-policies) · [conditionalAccessPolicy](https://learn.microsoft.com/graph/api/resources/conditionalaccesspolicy) · [grant controls](https://learn.microsoft.com/graph/api/resources/conditionalaccessgrantcontrols) · [conditions](https://learn.microsoft.com/graph/api/resources/conditionalaccessconditionset) · [applications (Office365)](https://learn.microsoft.com/graph/api/resources/conditionalaccessapplications)
- [Analyze Conditional Access policy impact: report-only](https://learn.microsoft.com/entra/identity/conditional-access/concept-conditional-access-report-only) · [Block legacy authentication](https://learn.microsoft.com/entra/identity/conditional-access/policy-block-legacy-authentication) · [Conditions: client apps](https://learn.microsoft.com/entra/identity/conditional-access/concept-conditional-access-conditions#client-apps) · [Target resources: Office 365](https://learn.microsoft.com/entra/identity/conditional-access/concept-conditional-access-cloud-apps#office-365)
- [Authentication strengths](https://learn.microsoft.com/entra/identity/authentication/concept-authentication-strengths) · [Authentication strengths API](https://learn.microsoft.com/graph/api/resources/authenticationstrengths-overview) · [authenticationStrengthPolicy](https://learn.microsoft.com/graph/api/resources/authenticationstrengthpolicy)
- [appliedConditionalAccessPolicy](https://learn.microsoft.com/graph/api/resources/appliedconditionalaccesspolicy) · [List signIns (AuditLog.Read.All)](https://learn.microsoft.com/graph/api/signin-list) · [Entra built-in roles and template ids](https://learn.microsoft.com/entra/identity/role-based-access-control/permissions-reference)
- [windows10CompliancePolicy](https://learn.microsoft.com/graph/api/resources/intune-deviceconfig-windows10compliancepolicy) · [create](https://learn.microsoft.com/graph/api/intune-deviceconfig-windows10compliancepolicy-create) · [assign](https://learn.microsoft.com/graph/api/intune-deviceconfig-devicecompliancepolicy-assign) · [scheduled action for rule](https://learn.microsoft.com/graph/api/resources/intune-deviceconfig-devicecompliancescheduledactionforrule) · [Intune device compliance](https://learn.microsoft.com/intune/intune-service/protect/device-compliance-get-started) · [Automatic MDM enrollment (MDM user scope)](https://learn.microsoft.com/intune/intune-service/enrollment/windows-enroll)
- [Key Vault private link](https://learn.microsoft.com/azure/key-vault/general/private-link-service) · [Private endpoint DNS zone values](https://learn.microsoft.com/azure/private-link/private-endpoint-dns) · [Key Vault soft delete](https://learn.microsoft.com/azure/key-vault/general/soft-delete-overview) · [Bicep: Microsoft.KeyVault/vaults](https://learn.microsoft.com/azure/templates/microsoft.keyvault/vaults) · [Key Vault Secrets User](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/security)
- [Network security groups (default rules)](https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview) · [Default outbound access](https://learn.microsoft.com/azure/virtual-network/ip-services/default-outbound-access) · [Token from a VM's managed identity (IMDS)](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/how-to-use-vm-token) · [az vm run-command](https://learn.microsoft.com/cli/azure/vm/run-command)
- Blog: [Zero Trust Network Architecture: Complete Guide](https://www.devladlog.com/articles/deep-dive/2026-02-16-zero-trust-network-architecture-azure-ad-conditional-access-intune-defender/)
