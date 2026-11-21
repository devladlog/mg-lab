#!/usr/bin/env python3
"""Validate social.yaml drafts against SOCIAL_BRIEF.md. Usage: check_social.py <episode-folder>..."""
import re
import sys
from pathlib import Path

import yaml

HYPE = ["game-changer", "game changer", "revolutionary", "unlock", "supercharge", "dive in", "deep dive into"]
FORBIDDEN = [r"onmicrosoft\.com", r"sharepoint\.com/", r"crm\d*\.dynamics\.com", r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"]
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def words(t):
    return len(re.findall(r"\b[\w'’-]+\b", t))


def tags(t):
    return re.findall(r"(?<!\w)#[A-Za-z]\w*", t)


def check(folder: Path):
    errs = []
    sf, sc = folder / "social.yaml", folder / "script.yaml"
    if not sf.exists():
        return [f"{folder}: missing social.yaml"]
    s = yaml.safe_load(sf.read_text(encoding="utf-8"))
    script = yaml.safe_load(sc.read_text(encoding="utf-8")) if sc.exists() else {}
    e = lambda m: errs.append(f"{folder.name}: {m}")
    if s.get("status") != "draft-hold-for-review":
        e("status must be draft-hold-for-review")
    if s.get("ai_label") is not True:
        e("ai_label must be true")
    if script and s.get("episode") != script.get("episode"):
        e("episode number differs from script.yaml")
    texts = []

    def block(key, lo, hi, maxtags, emoji_max, disclose=True):
        t = ((s.get(key) or {}).get("text") or "").strip()
        if not t:
            return e(f"{key}.text missing")
        texts.append(t)
        n = words(t)
        if not lo <= n <= hi:
            e(f"{key}: {n} words (want {lo}-{hi})")
        if len(tags(t)) > maxtags:
            e(f"{key}: {len(tags(t))} hashtags (max {maxtags})")
        if len(EMOJI.findall(t)) > emoji_max:
            e(f"{key}: too many emoji")
        if "{YOUTUBE_URL}" not in t:
            e(f"{key}: no {{YOUTUBE_URL}}")
        if disclose and "Narration uses an AI voice." not in t:
            e(f"{key}: missing AI voice line")

    block("linkedin_company", 120, 230, 5, 0)
    block("linkedin_personal", 60, 150, 3, 2)
    block("facebook", 50, 120, 3, 2)

    want = [sc_["short"] for sc_ in script.get("scenes", []) if sc_.get("short")] if script else None
    shorts = s.get("shorts") or []
    got = [x.get("id") for x in shorts]
    if want is not None and got != want:
        e(f"shorts ids {got} != script.yaml shorts {want}")
    for x in shorts:
        sid = x.get("id")
        yt = x.get("youtube_short_title") or ""
        if not yt or len(yt) > 90 or not yt.rstrip().endswith("#Shorts"):
            e(f"short {sid}: youtube_short_title must be <=90 chars and end with #Shorts")
        ig = x.get("instagram_reel") or {}
        cap = (ig.get("caption") or "").strip()
        texts.append(cap)
        if not 40 <= words(cap) <= 130:
            e(f"short {sid}: instagram caption {words(cap)} words (want 40-120)")
        if len(tags(cap)) > 5:
            e(f"short {sid}: instagram >5 hashtags")
        if "link in bio" not in cap.lower():
            e(f"short {sid}: instagram caption lacks 'link in bio'")
        cov = ig.get("cover_text") or ""
        if not cov or len(cov) > 32:
            e(f"short {sid}: cover_text missing or >32 chars")
        tk = ((x.get("tiktok") or {}).get("caption") or "").strip()
        texts.append(tk)
        if not tk or len(tk) > 300:
            e(f"short {sid}: tiktok caption missing or >300 chars")
        if len(tags(tk)) > 5:
            e(f"short {sid}: tiktok >5 hashtags")
    alltext = "\n".join(texts)
    low = alltext.lower()
    for h in HYPE:
        if h in low:
            e(f"hype word: {h}")
    for pat in FORBIDDEN:
        if re.search(pat, alltext, re.I):
            e(f"possible real identifier matches {pat}")
    if re.search(r"https?://", alltext):
        e("literal URL found; use placeholders")
    return errs


def main(argv):
    folders = [Path(a) for a in argv] or []
    allerrs = []
    for f in folders:
        allerrs += check(f)
    for x in allerrs:
        print("ERROR", x)
    print(f"{len(folders)} folders checked, {len(allerrs)} errors")
    return 1 if allerrs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
