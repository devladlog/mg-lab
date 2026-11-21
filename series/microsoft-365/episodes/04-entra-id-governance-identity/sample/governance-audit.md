# Entra ID governance audit

As of 2026-11-20 09:30 UTC. 6 active and 2 eligible role assignments, 1 access reviews, 1 lifecycle workflows, 6 findings.

| Severity | Target | Rule | Detail |
|---|---|---|---|
| High | Legacy Admin | PermanentActivePrivileged | Global Administrator is permanently active. Keep zero permanent active assignments except emergency access accounts: make it eligible in PIM. |
| High | Ops Admin | PermanentActivePrivileged | User Administrator is permanently active. Keep zero permanent active assignments except emergency access accounts: make it eligible in PIM. |
| High | Tenant | LicenceEnding | Governance licence ends 2026-12-20 (29 days): 2 eligible assignment(s) will be removed and 1 time-bound active assignment(s) become permanent. |
| Medium | Tenant | NoGuestReview | No access review covers guests: guests stay in Microsoft 365 groups until someone notices. |
| Info | Alex Demo | ActivatedNow | Groups Administrator activated through PIM until 2026-11-20 13:00 UTC. |
| Info | Leaver - Sales members on their last day | LeaverNotScheduled | Enabled but not scheduled: it only runs on demand. |
