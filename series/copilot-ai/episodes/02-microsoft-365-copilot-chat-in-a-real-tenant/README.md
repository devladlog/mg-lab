# DEVLADLOG Copilot & AI #2 - Microsoft Copilot Chat in a Real Tenant

Copilot Chat is already in every Entra work account of Contoso. This episode uses it as a normal, **unlicensed** user in
the lab tenant, walks the admin controls, and then reads what Copilot leaves in the Microsoft Purview audit log, with a
small tool you can run:

- `Export-CopilotInteractions.ps1` exports `CopilotInteraction` audit records (paged `Search-UnifiedAuditLog`);
- `copilot_chat_audit` summarises them: who, which app host, web search used (`AISystemPlugin.Id = BingWebSearch`),
  agents, files touched and their sensitivity labels, model provider, jailbreak/XPIA/DLP-deferred flags, and the split
  between users who hold the Microsoft 365 Copilot add-on and those who do not.

Series plan: [`../../README.md`](../../README.md). Shared lab: [`../../../LAB.md`](../../../LAB.md). Previous: episode 1,
[the Copilot landscape](../01-the-copilot-landscape-every-copilot-licence-and-wh/). Category episodes this builds on:
[Microsoft 365 Copilot for Microsoft 365](../../../microsoft-365/episodes/08-microsoft-365-copilot-for-microsoft-365/) and
[Microsoft Purview compliance](../../../microsoft-365/episodes/05-microsoft-purview-compliance/).
Next: episode 3, *Copilot Studio: Your First Agent with SharePoint Knowledge*.

| Path | What it is |
|---|---|
| [`src/scripts/Export-CopilotInteractions.ps1`](src/scripts/Export-CopilotInteractions.ps1) | Real collector. Needs `Connect-ExchangeOnline` and the *Audit Logs* or *View-Only Audit Logs* role. Read-only |
| [`src/copilot_chat_audit/parse.py`](src/copilot_chat_audit/parse.py) | Reads CSV (portal or script), JSON, JSON lines; normalises one `CopilotInteraction` per record |
| [`src/copilot_chat_audit/summary.py`](src/copilot_chat_audit/summary.py) | The numbers: by user/host/app identity, web share, agents, models, flags, licence split |
| [`src/copilot_chat_audit/cli.py`](src/copilot_chat_audit/cli.py) | `python -m copilot_chat_audit EXPORT [--licensed users.txt] [--since YYYY-MM-DD] [--json]` |
| [`src/samples/`](src/samples) | Fictional export built from the documented schema (tests only), licensed-user list, and the vendor summary used for the upload demo |
| [`tests/`](tests) | 18 pytest tests, including two that run the PowerShell script under `pwsh` |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (15 scenes, about 800 words) and shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/02-microsoft-365-copilot-chat-in-a-real-tenant
python3 -m pip install -r src/requirements.txt    # pytest only: the tool is standard library
python3 -m pytest -q                               # 18 passed (needs pwsh for 2 of them)
cd src
python3 -m copilot_chat_audit samples/copilot-interactions-sample.csv --licensed samples/licensed-users.txt
```

Against the tenant (needs the tenant, read-only):

```powershell
Connect-ExchangeOnline -UserPrincipalName <admin UPN>
./src/scripts/Export-CopilotInteractions.ps1 -StartDate (Get-Date).AddDays(-2) -OutFile $HOME/copilot-interactions.csv
python -m copilot_chat_audit $HOME/copilot-interactions.csv --json
```

Verified here: pytest 18 passed (Python 3.13, PowerShell 7). Not verified without the tenant: the first real export,
and in particular whether unlicensed Copilot Chat users produce records and which properties they carry (see `demo.md`,
"Open points").

## What we learned / gotchas

- **Basic cannot use Microsoft Graph.** Learn: Copilot Chat (Basic) answers from the web; organisational content only if
  you upload it, work with open content in Outlook or Teams, or use a pay-as-you-go agent. The mailbox question in the
  demo is built to show exactly that; if the real product behaves differently, the script says to stop and rewrite.
- **Web search has its own admin policy**, *Allow web search in Copilot*, available only in the Cloud Policy service.
  Three options; not configured means web search is on. If the optional-connected-experiences policy is Disabled it also
  restricts Copilot Chat and other experiences. Users have a *Web content* toggle that is dimmed when the admin turns web
  search off. GCC and DoD tenants: off by default.
- **Blocking is all or nothing.** Blocking the Copilot app through Integrated Apps is tenant-wide, licensed users
  included. Removing Copilot Chat only for unlicensed users means not deploying the app to them and allowing it in Teams
  only for licensed users.
- **Pinning:** *Copilot > Settings > Pin Microsoft Copilot Chat* (AI Administrator role); changes take up to 48 hours.
  The article also says Copilot Chat can no longer be unpinned from the navigation for all tenants, so do not promise
  users an "off" switch here (the article states two different January 2026 dates; we quote none).
- **Network:** allow `*.cloud.microsoft`; never block `copilot.cloud.microsoft` to stop personal accounts, use tenant
  restrictions v2 instead.
- **Audit is metadata.** Each `CopilotInteraction` record has user, time, `AppHost`, thread and message IDs (not text),
  `AccessedResources` with sensitivity label IDs, `AISystemPlugin` (value `BingWebSearch` when the public web was used)
  and, when recorded, `ModelTransparencyDetails`. Prompt text is a Purview eDiscovery / DSPM for AI matter. Audit
  (Standard) retains 180 days; Microsoft's own audit logs for Copilot are in Standard, while audit of *non-Microsoft*
  AI apps is pay-as-you-go.
- **`Search-UnifiedAuditLog` paging:** `-ResultSize` max 5,000 per call; with `-SessionCommand ReturnLargeSet` and one
  `-SessionId` you page to at most 50,000 records, unsorted. Never switch `SessionCommand` for the same session. Learn
  recommends the Management Activity API for programmatic downloads, so treat the script as an ad-hoc admin tool. The
  script warns when it hits the cap.
- **Audit latency:** Microsoft makes no promise; core services are typically 60 to 90 minutes, others longer. Generate
  the demo traffic the day before.
- **`AppIdentity` location** is not shown in Learn's JSON example; the parser reads the top level and `CopilotEventData`.
- The tool's own `ClientRegion`, `ClientIP` and `OrganizationId` fields are real tenant data in a real export: keep
  exports out of the repository.

## References

Microsoft Learn
- [Microsoft Copilot overview](https://learn.microsoft.com/copilot/plan/copilot-overview)
- [Manage Copilot Chat](https://learn.microsoft.com/copilot/manage/manage-copilot-chat)
- [Web search in Microsoft Copilot and Copilot Chat: data, privacy and the *Allow web search in Copilot* policy](https://learn.microsoft.com/copilot/plan/manage-public-web-access)
- [Pin Microsoft Copilot Chat in the Microsoft 365 apps](https://learn.microsoft.com/copilot/implement/pin-copilot-chat-navbar)
- [Audit logs for Copilot and AI applications](https://learn.microsoft.com/purview/audit-copilot)
- [Copilot interaction events (schema)](https://learn.microsoft.com/office/office-365-management-api/copilot-schema)
- [Search-UnifiedAuditLog](https://learn.microsoft.com/powershell/module/exchange/search-unifiedauditlog)
- [Search the audit log (roles, latency, retention)](https://learn.microsoft.com/purview/audit-search)
- [Purchase and manage agents in Copilot Chat](https://learn.microsoft.com/copilot/manage/manage-agents-copilot-chat)

No devladlog.com blog guide: this series is built from vendor documentation only.
