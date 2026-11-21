"""Generates the per-series plan READMEs, episode-01 stubs and the series index from series.yaml."""
import datetime as dt, re, yaml
from pathlib import Path

ROOT = Path(__file__).parent
data = yaml.safe_load((ROOT / "series.yaml").read_text(encoding="utf-8"))
BASE = data["base"]
ORDER = ["powerapps", "azure", "sharepoint", "net", "power-automate", "ai", "power-bi", "microsoft-365",
         "sql", "dynamics-365", "programming-languages", "windows-server", "developer-tools", "deep-dive"]
by_slug = {s["slug"]: s for s in data["series"]}
FORMATS = ["Complete Guide", "Architecture Patterns and Decision Framework", "Implementation Blueprint and Hands-On Walkthrough",
           "Developer Implementation Guide", "Operations, Security, and Optimization Playbook"]

def slugify(t): return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:48]

# Video premieres: Tue + Thu 18:00 Lisbon from 1 Dec 2026, skipping 24 and 31 Dec
def video_slots():
    d = dt.date(2026, 12, 1)
    while True:
        if d.weekday() in (1, 3) and d not in (dt.date(2026, 12, 24), dt.date(2026, 12, 31)):
            yield d
        d += dt.timedelta(days=1)
slots = video_slots()
first_video = {slug: next(slots) for slug in ORDER}
spotlight = {slug: dt.date(2026, 11, 23) + dt.timedelta(days=i) for i, slug in enumerate(ORDER)}

index_rows = []
for slug in ORDER:
    s = by_slug[slug]
    d = ROOT / slug
    topics = s["topics"]
    track = next(t for t, v in data["tracks"].items() if slug in v)
    rows = "\n".join(f"| {i:02d} | {t['name']} | [Complete Guide]({BASE}{t['guide']}) |" for i, t in enumerate(topics, 1))
    needs = "\n".join(f"- [ ] {n}" for n in s["needs"])
    note = f"\n> {s['note']}\n" if s.get("note") else ""
    ep1 = topics[0]
    ep1_dir = f"episodes/01-{slugify(ep1['name'])}"
    readme = f"""# {s['name']}

**Blog category:** [{s['category']}]({BASE}/articles/{slug}/) · ~{s['articles']} articles · track: {track}
**Audience:** {s['audience']}
**YouTube playlist:** `{s['name']}` · **Hashtags:** {s['hashtags']}

Two series run side by side:

1. **Video series** — one {data['video']['length']} episode per blog topic, plus {data['video']['shorts_per_episode']} Shorts.
   Each episode builds the topic *for real* (working code/config in `episodes/NN-*/`), then links to the topic's five articles.
2. **DEVLADLOG Spotlight** (social) — LinkedIn page + Facebook, {data['social']['slot']}; each post links one article,
   rotating through the five formats ({', '.join(FORMATS[:2])}, …).

## Calendar
| What | When |
|---|---|
| First Spotlight post | {spotlight[slug]:%a %d %b %Y} 09:30, then every 14 days |
| Episode 01 target premiere | {first_video[slug]:%a %d %b %Y} 18:00, then every ~7 weeks (14 series share Tue/Thu slots) |
| Shorts | 13:00 on the days after each premiere, alternating with MG Lab Shorts |

## Episode backlog (one per topic, in order)
| # | Topic | Source article |
|---|---|---|
{rows}
{note}
Each topic also has Architecture, Implementation Blueprint, Developer Guide and Operations Playbook articles on the blog;
link all five in the episode description.

## What's needed before filming
{needs}
- [ ] Masking: `pipeline/mask.js` in the browser, `series_label: "{s['label']}"` in each `script.yaml`
- [ ] Episode 01 script: [`{ep1_dir}/script.yaml`]({ep1_dir}/script.yaml)

## Quality bar (applies to every episode)
- Every command and snippet shown must have run in the lab tenant. No placeholder scripts.
- Facts checked against Microsoft Learn; client names and real identifiers never on screen.
- After each episode, update the matching blog articles with the working code from the episode folder.

## Publishing checklist (per episode)
- [ ] Render: `python pipeline/make_episode.py series/{slug}/{ep1_dir}/script.yaml --out build/{slug}-ep01`
- [ ] YouTube + LinkedIn page via Metricool (AI label on), then personal LinkedIn + Facebook with the YouTube link
- [ ] Add to the `{s['name']}` playlist, upload the exact `.srt`
- [ ] Schedule the Shorts (YouTube Shorts, TikTok, Instagram Reel, LinkedIn) with AI labels
"""
    d.mkdir(parents=True, exist_ok=True)
    (d / "README.md").write_text(readme, encoding="utf-8")
    ep = d / ep1_dir
    ep.mkdir(parents=True, exist_ok=True)
    stub = f"""# {s['name']} — episode 01 (stub: write the scenes after building the demo)
episode: 1
slug: {slugify(ep1['name'])}
series_label: "{s['label']}"
series_name: "{s['name']}"
file_prefix: "{slug}"
title: "{ep1['name']}"
subtitle: "Built for real, in a lab tenant"
voice: am_michael
thumbnail_text: "{ep1['name'].upper()[:40]}"
youtube:
  title: "{ep1['name']} (Real Demo) | {s['name']} #1"
  tags: []
sources:
  - {BASE}{ep1['guide']}
scenes:
  - id: hook
    type: title
    heading: "{ep1['name']}"
    sub: "Built for real, in a lab tenant"
    short: hook
    narration: >
      TODO
  - id: outro
    type: outro
    heading: "Code on GitHub, guides on devladlog.com"
    sub: "github.com/devladlog/mg-lab"
    narration: >
      TODO
"""
    (ep / "script.yaml").write_text(stub, encoding="utf-8")
    index_rows.append(f"| [{s['name']}]({slug}/) | [{s['category']}]({BASE}/articles/{slug}/) | {len(topics)} | {ep1['name']} | {first_video[slug]:%d %b} | {spotlight[slug]:%d %b} |")

index = f"""# DEVLADLOG category series

One **video series** and one **social Spotlight series** per [devladlog.com]({BASE}) category (14).
Data lives in [`series.yaml`](series.yaml); regenerate the READMEs and stubs with `python series/build_series.py`.

| Series | Blog category | Episodes planned | Episode 01 | Ep 01 target | First Spotlight |
|---|---|---|---|---|---|
{chr(10).join(index_rows)}

**Video cadence:** Tue + Thu 18:00 Lisbon, rotating through the series (each series gets an episode about every 7 weeks).
**Spotlight cadence:** daily 09:30 Lisbon, one series per day (14-day rotation), LinkedIn page + Facebook.
**MG Lab** continues as the flagship cross-topic series; Shorts stay at 13:00.

Videos use the same pipeline as MG Lab (`pipeline/make_episode.py`) with `series_label`, `series_name` and `file_prefix`
set in each `script.yaml`.
"""
(ROOT / "README.md").write_text(index, encoding="utf-8")
print("\n".join(index_rows))
