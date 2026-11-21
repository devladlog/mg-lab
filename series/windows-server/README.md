# DEVLADLOG Windows Server

**Blog category:** [Windows Server](https://www.devladlog.com/articles/windows-server/) · ~72 articles · track: azure
**Audience:** Windows Server and infrastructure admins
**YouTube playlist:** `DEVLADLOG Windows Server` · **Hashtags:** #WindowsServer #ActiveDirectory #SysAdmin

Two series run side by side:

1. **Video series** — one 5-7 min, narrated, real demo in the lab tenant (masked), English episode per blog topic, plus 3 Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, daily 09:30 Lisbon, one series per day, 14-day rotation; each post links one article,
   rotating through the five formats (Complete Guide, Architecture Patterns and Decision Framework, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | Fri 04 Dec 2026 09:30, then every 14 days |
| Episode 01 target premiere | Thu 14 Jan 2027 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
| 01 | Windows Server Administration | [Complete Guide](https://www.devladlog.com/articles/windows-server/2025-09-02-windows-server-administration-complete-guide-2025/) |
| 02 | Active Directory Domain Services | [Complete Guide](https://www.devladlog.com/articles/windows-server/2025-08-26-active-directory-domain-services-complete-guide-2025/) |
| 03 | Group Policy Management | [Complete Guide](https://www.devladlog.com/articles/windows-server/2025-08-29-group-policy-management-complete-guide-2025/) |
| 04 | DNS & DHCP Management | [Complete Guide](https://www.devladlog.com/articles/windows-server/2025-10-01-dns-dhcp-management-complete-guide-2025/) |
| 05 | PowerShell Automation | [Complete Guide](https://www.devladlog.com/articles/windows-server/2025-09-09-powershell-automation-complete-guide-2025/) |
| 06 | Windows Admin Center | [Complete Guide](https://www.devladlog.com/articles/windows-server/2025-09-16-windows-admin-center-complete-guide-2025/) |
| 07 | Hyper-V Virtualization | [Complete Guide](https://www.devladlog.com/articles/windows-server/2025-09-06-hyper-v-virtualization-complete-guide-2025/) |
| 08 | Windows Server Security | [Complete Guide](https://www.devladlog.com/articles/windows-server/2025-09-27-windows-server-security-complete-guide-2025/) |
| 09 | Certificate Services | [Complete Guide](https://www.devladlog.com/articles/windows-server/2025-10-05-certificate-services-complete-guide-2025/) |
| 10 | Server Core & Nano Server | [Complete Guide](https://www.devladlog.com/articles/windows-server/2025-09-13-server-core-nano-server-complete-guide-2025/) |
| 11 | Remote Desktop Services | [Complete Guide](https://www.devladlog.com/articles/windows-server/2025-09-24-remote-desktop-services-complete-guide-2025/) |
| 12 | Failover Clustering | [Complete Guide](https://www.devladlog.com/articles/windows-server/2025-09-20-failover-clustering-complete-guide-2025/) |

Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
- [ ] Hyper-V lab on the homelab (HP EliteDesk or a desktop): Windows Server 2025 evaluation VMs (180-day eval)
- [ ] Isolated lab network (Omada VLAN) so lab AD/DNS/DHCP never touch the home network
- [ ] Or Azure VMs with auto-shutdown + budget alert
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: "WINDOWS SERVER"` in each `script.yaml`
- [ ] Episode 01 script: [`episodes/01-windows-server-administration/script.yaml`](episodes/01-windows-server-administration/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/windows-server/episodes/01-windows-server-administration/script.yaml --out build/windows-server-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `DEVLADLOG Windows Server` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
