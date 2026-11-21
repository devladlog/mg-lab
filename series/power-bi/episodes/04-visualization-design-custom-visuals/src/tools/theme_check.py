#!/usr/bin/env python3
"""theme-check: accessibility checks for a Power BI report theme JSON file.

Rules
  TC001 error    text colour vs background below 4.5:1  (Learn accessibility checklist, WCAG 2.1 SC 1.4.3)
  TC002 warning  data colour vs background below 3:1    (WCAG 2.1 SC 1.4.11, non-text contrast)
  TC003 error    good and bad look alike for red-green colour vision deficiency (simulated)
  TC004 warning  two of the first N data colours look alike for normal vision or a simulated deficiency

Colour science: WCAG relative luminance and contrast ratio; colour vision deficiency simulated with the
Machado, Oliveira and Fernandes (2009) matrices at full severity, in linear RGB; "look alike" = CIEDE2000
difference below a threshold. The thresholds for TC003/TC004 are our heuristics, not Microsoft numbers.

Usage:
    python theme_check.py <theme.json> [--first 6] [--json]
"""
import argparse
import json
import math
import sys
from pathlib import Path

TEXT_MIN = 4.5
GRAPHIC_MIN = 3.0
SENTIMENT_MIN_DE = 20.0
DATA_MIN_DE = 10.0

# Machado et al. 2009, severity 1.0, applied to linear RGB
CVD = {
    "protanopia": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "deuteranopia": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    "tritanopia": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]],
}


def hex_to_rgb(h: str):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#" + "".join(f"{round(max(0, min(1, c)) * 255):02X}" for c in rgb)


def to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def to_srgb(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def luminance(h):
    r, g, b = (to_linear(c) for c in hex_to_rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def simulate(h, kind):
    lin = [to_linear(c) for c in hex_to_rgb(h)]
    m = CVD[kind]
    out = [sum(m[i][j] * lin[j] for j in range(3)) for i in range(3)]
    return rgb_to_hex([to_srgb(c) for c in out])


def to_lab(h):
    r, g, b = (to_linear(c) for c in hex_to_rgb(h))
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / 1.00000
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def ciede2000(lab1, lab2):
    """CIEDE2000 colour difference (Sharma, Wu, Dalal 2005)."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cbar ** 7 / (Cbar ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if C1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if C2p else 0.0
    dLp, dCp = L2 - L1, C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    else:
        dhp = h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    else:
        hbp = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dtheta = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / math.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def delta_e(a, b, vision="normal"):
    if vision != "normal":
        a, b = simulate(a, vision), simulate(b, vision)
    return ciede2000(to_lab(a), to_lab(b))


def text_colours(theme):
    out = []
    for key in ("foreground", "firstLevelElements", "secondLevelElements"):
        if key in theme:
            out.append((key, theme[key]))
    for cls, props in theme.get("textClasses", {}).items():
        if "color" in props:
            out.append((f"textClasses.{cls}", props["color"]))
    return out


def check(theme, first=6):
    findings = []
    add = lambda rule, sev, msg: findings.append({"rule": rule, "severity": sev, "message": msg})
    bg = theme.get("background", "#FFFFFF")

    for name, colour in text_colours(theme):
        r = contrast(colour, bg)
        if r < TEXT_MIN:
            add("TC001", "error", f"{name} {colour} on {bg}: {r:.2f}:1, needs {TEXT_MIN}:1")

    data = theme.get("dataColors", [])
    for i, colour in enumerate(data[:first]):
        r = contrast(colour, bg)
        if r < GRAPHIC_MIN:
            add("TC002", "warning", f"dataColors[{i}] {colour} on {bg}: {r:.2f}:1, needs {GRAPHIC_MIN}:1")

    if "good" in theme and "bad" in theme:
        for vision in ("normal", "protanopia", "deuteranopia"):
            de = delta_e(theme["good"], theme["bad"], vision)
            if de < SENTIMENT_MIN_DE:
                add("TC003", "error", f"good {theme['good']} vs bad {theme['bad']} ({vision}): "
                                      f"difference {de:.1f}, needs {SENTIMENT_MIN_DE:.0f}")

    for vision in ("normal", "protanopia", "deuteranopia", "tritanopia"):
        for i in range(min(first, len(data))):
            for j in range(i + 1, min(first, len(data))):
                de = delta_e(data[i], data[j], vision)
                if de < DATA_MIN_DE:
                    add("TC004", "warning", f"dataColors[{i}] {data[i]} vs [{j}] {data[j]} ({vision}): "
                                            f"difference {de:.1f}, needs {DATA_MIN_DE:.0f}")
    return findings


def summary(theme, first=6):
    """Numbers worth showing: contrast of every colour and the closest pair per vision type."""
    bg = theme.get("background", "#FFFFFF")
    data = theme.get("dataColors", [])[:first]
    closest = {}
    for vision in ("normal", "protanopia", "deuteranopia", "tritanopia"):
        pairs = [(delta_e(data[i], data[j], vision), i, j) for i in range(len(data)) for j in range(i + 1, len(data))]
        de, i, j = min(pairs)
        closest[vision] = {"pair": [i, j], "delta_e": round(de, 1)}
    return {
        "text_contrast": {n: round(contrast(c, bg), 2) for n, c in text_colours(theme)},
        "data_contrast": [round(contrast(c, bg), 2) for c in data],
        "good_vs_bad": {v: round(delta_e(theme["good"], theme["bad"], v), 1)
                        for v in ("normal", "protanopia", "deuteranopia")} if "good" in theme else {},
        "closest_data_pair": closest,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("theme")
    ap.add_argument("--first", type=int, default=6, help="how many data colours a typical visual uses")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    theme = json.loads(Path(a.theme).read_text(encoding="utf-8"))
    findings = check(theme, a.first)
    if a.json:
        print(json.dumps({"findings": findings, "summary": summary(theme, a.first)}, indent=2))
    else:
        for f in findings:
            print(f"  {f['severity'].upper():7}  {f['rule']}  {f['message']}")
        errors = sum(f["severity"] == "error" for f in findings)
        print(f"{theme.get('name', a.theme)}: {errors} error(s), {len(findings) - errors} warning(s)")
    sys.exit(1 if any(f["severity"] == "error" for f in findings) else 0)


if __name__ == "__main__":
    main()
