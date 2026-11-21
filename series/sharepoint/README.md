# DEVLADLOG SharePoint

**Blog category:** [SharePoint](https://www.devladlog.com/articles/sharepoint/) · ~113 articles · track: sharepoint-m365
**Audience:** SharePoint admins, intranet owners and M365 developers
**YouTube playlist:** `DEVLADLOG SharePoint` · **Hashtags:** #SharePoint #Microsoft365 #Intranet

Two series run side by side:

1. **Video series** — one 5-7 min, narrated, real demo in the lab tenant (masked), English episode per blog topic, plus 3 Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, daily 09:30 Lisbon, one series per day, 14-day rotation; each post links one article,
   rotating through the five formats (Complete Guide, Architecture Patterns and Decision Framework, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | Wed 25 Nov 2026 09:30, then every 14 days |
| Episode 01 target premiere | Tue 08 Dec 2026 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
| 01 | Lists & Libraries Best Practices | [Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-03-22-lists-libraries-best-practices-complete-guide-2026/) |
| 02 | JSON Formatting | [Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-04-13-json-formatting-complete-guide-2026/) |
| 03 | Modern Sites & Pages | [Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-03-15-modern-sites-pages-complete-guide-2026/) |
| 04 | Document Management | [Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-03-18-document-management-complete-guide-2026/) |
| 05 | Permissions & Governance | [Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-03-26-permissions-governance-complete-guide-2026/) |
| 06 | Search & Metadata | [Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-03-29-search-metadata-complete-guide-2026/) |
| 07 | Hub Sites & Navigation | [Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-04-02-hub-sites-navigation-complete-guide-2026/) |
| 08 | Intranet Design | [Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-04-09-intranet-design-complete-guide-2026/) |
| 09 | Integration with Teams | [Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-04-17-integration-with-teams-complete-guide-2026/) |
| 10 | SharePoint Syntex | [Complete Guide](https://www.devladlog.com/articles/sharepoint/2026-04-06-sharepoint-syntex-complete-guide-2026/) |

Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
- [ ] MGLabDemo site (exists) + a hub and two associated sites
- [ ] SharePoint admin role (exists)
- [ ] SharePoint Premium / Syntex pay-as-you-go for the Syntex episode
- [ ] PnP app 'MG Lab PnP' (exists) for scripted setup
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: "SHAREPOINT"` in each `script.yaml`
- [ ] Episode 01 script: [`episodes/01-lists-libraries-best-practices/script.yaml`](episodes/01-lists-libraries-best-practices/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/sharepoint/episodes/01-lists-libraries-best-practices/script.yaml --out build/sharepoint-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `DEVLADLOG SharePoint` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
