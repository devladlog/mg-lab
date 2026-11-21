# Microsoft 365 Apps activation audit

_As of 2026-11-21 12:00:00Z._

5 activation row(s) in the report (one per user and product).

**4 finding(s):** 0 High / 1 Medium / 1 Low / 2 Info

| Severity | Type | Who | Detail |
|---|---|---|---|
| Medium | DesktopAtLimit | sam.demo@contoso.example | 4 Windows + 1 Mac activations. Learn: a licence covers up to 5 desktops; past 10 devices the least recently used one is deactivated automatically. |
| Low | StaleActivation | jordan.demo@contoso.example | Last activated 172 days ago (limit 90). Licensed but not using the desktop apps, or a leaver whose licence is still assigned. |
| Info | MobileOnly | riley.demo@contoso.example | 3 mobile activation(s) and no desktop activation. |
| Info | SharedComputer | taylor.demo@contoso.example | Activated on a shared computer (shared computer activation does not count against the desktop limit). |

