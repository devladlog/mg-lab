#!/usr/bin/env python3
"""MG Lab video pipeline: script.yaml -> narrated 1080p episode, vertical Shorts, SRT and thumbnail.

Usage:
  python make_episode.py ../episodes/01-power-platform-alm/script.yaml --out ./build/ep01
Options:
  --only-shorts / --skip-shorts / --voice am_michael / --speed 1.0

Needs: ffmpeg on PATH, pip install -r requirements.txt, Kokoro model files in ./models
(kokoro-v1.0.onnx + voices-v1.0.bin from github.com/thewh1teagle/kokoro-onnx releases),
brand assets in ./assets (background.png, music.mp3 optional, intro_clip.mp4 optional).
"""
import argparse, os, re, subprocess, json, math, shutil
from pathlib import Path
import yaml
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

HERE = Path(__file__).resolve().parent
FONTS = HERE / "fonts"
ASSETS = HERE / "assets"
MODELS = HERE / "models"

# ---- brand ---------------------------------------------------------------
YELLOW = (255, 214, 0, 255)
BLUE = (59, 130, 246)
WHITE = (255, 255, 255)
MUTED = (186, 192, 212)
CODE_BG = (13, 14, 28, 235)
TOKEN_COLORS = {
    "Keyword": (198, 146, 255), "Name.Tag": (130, 170, 255), "Name.Attribute": (130, 170, 255),
    "Literal.String": (152, 222, 140), "String": (152, 222, 140), "Literal.Number": (255, 184, 108),
    "Number": (255, 184, 108), "Comment": (110, 118, 150), "Operator": (137, 221, 255),
    "Punctuation": (190, 196, 220), "Name.Builtin": (255, 203, 107), "Name.Variable": (255, 203, 107),
}


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def wrap(draw, text, f, max_w):
    lines = []
    for para in str(text).split("\n"):
        line = ""
        for w in para.split():
            t = (line + " " + w).strip()
            if draw.textlength(t, font=f) <= max_w:
                line = t
            else:
                if line:
                    lines.append(line)
                line = w
        lines.append(line)
    return lines


def background(W, H):
    bg = ASSETS / "background.png"
    if bg.exists():
        im = Image.open(bg).convert("RGB")
        r = max(W / im.width, H / im.height)
        im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1), Image.LANCZOS)
        x, y = (im.width - W) // 2, (im.height - H) // 2
        im = im.crop((x, y, x + W, y + H)).filter(ImageFilter.GaussianBlur(6))
        im = ImageEnhance.Brightness(im).enhance(0.35)
    else:
        im = Image.new("RGB", (W, H), (8, 8, 20))
    return im.convert("RGBA")


# Series branding; overridden from script.yaml (series_label / series_name / file_prefix).
SERIES = {"label": "MG LAB", "name": "MG Lab", "prefix": "mglab"}


def header(d, W, ep, label=None):
    label = label or SERIES["label"]
    d.text((70, 48), "MG", font=font("Inter-Bold.otf", 46), fill=WHITE)
    d.text((160, 62), f"{label}  ·  EPISODE {ep:02d}", font=font("Inter-Medium.otf", 24), fill=MUTED)
    d.text((W - 70, 62), "momentogalatico.com", font=font("Inter-Medium.otf", 24), fill=MUTED, anchor="ra")


# ---- slide renderers (1920x1080) ------------------------------------------
def code_image(code, lang, max_w, max_h, base=34):
    from pygments import lex
    from pygments.lexers import get_lexer_by_name, TextLexer
    try:
        lexer = get_lexer_by_name(lang)
    except Exception:
        lexer = TextLexer()
    lines = code.rstrip("\n").split("\n")
    size = base
    while size > 16:
        f = font("JetBrainsMono-Regular.ttf", size)
        lh = int(size * 1.45)
        longest = max(len(l) for l in lines) if lines else 1
        if longest * f.getlength("M") <= max_w - 80 and lh * len(lines) <= max_h - 70:
            break
        size -= 2
    f = font("JetBrainsMono-Regular.ttf", size)
    lh = int(size * 1.45)
    w = int(max(len(l) for l in lines) * f.getlength("M")) + 80
    h = lh * len(lines) + 70
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w, h), radius=22, fill=CODE_BG, outline=(70, 80, 130, 255), width=2)
    x0, y = 40, 35
    x = x0
    for ttype, value in lex(code.rstrip("\n"), lexer):
        tname = str(ttype).replace("Token.", "")
        color = WHITE
        for k, c in TOKEN_COLORS.items():
            if tname.startswith(k):
                color = c
                break
        parts = value.split("\n")
        for i, p in enumerate(parts):
            if i > 0:
                y += lh
                x = x0
            if p:
                d.text((x, y), p, font=f, fill=color)
                x += f.getlength(p)
    return img


def render_slide(scene, ep, W=1920, H=1080):
    im = background(W, H)
    d = ImageDraw.Draw(im)
    header(d, W, ep)
    t = scene["type"]
    if t in ("title", "outro"):
        fb = font("Inter-Bold.otf", 120)
        lines = wrap(d, scene["heading"], fb, W - 280)
        y = H / 2 - (len(lines) * 135) / 2 - 40
        for l in lines:
            d.text((W / 2, y), l, font=fb, fill=WHITE, anchor="ma")
            y += 135
        d.rectangle((W / 2 - 160, y + 20, W / 2 + 160, y + 30), fill=BLUE)
        if scene.get("sub"):
            d.text((W / 2, y + 70), scene["sub"], font=font("Inter-Medium.otf", 48), fill=MUTED, anchor="ma")
    else:
        live = t == "screen" and scene.get("_live")
        if live:  # live recordings get most of the frame: smaller heading, wider window
            d.text((80, 112), scene["heading"], font=font("Inter-Bold.otf", 56), fill=WHITE)
            d.rectangle((80, 188, 260, 194), fill=BLUE)
        else:
            d.text((110, 170), scene["heading"], font=font("Inter-Bold.otf", 72), fill=WHITE)
            d.rectangle((110, 268, 330, 276), fill=BLUE)
        if t == "bullets":
            fb = font("Inter-SemiBold.otf", 54)
            y = 340
            for b in scene["bullets"]:
                d.ellipse((120, y + 20, 140, y + 40), fill=BLUE)
                for i, l in enumerate(wrap(d, b, fb, W - 340)):
                    d.text((175, y), l, font=fb, fill=WHITE)
                    y += 68
                y += 34
        elif t == "code":
            ci = code_image(scene["code"], scene.get("lang", "text"), W - 220, H - 340)
            im.alpha_composite(ci, (110 + max(0, (W - 220 - ci.width) // 2), 315))
        elif t == "screen":
            # real (masked) screen capture inside a neutral browser frame
            src = Path(scene.get("_poster") or scene["image"])
            if not src.is_absolute():
                src = Path(scene.get("_base", ".")) / src
            shot = Image.open(src).convert("RGBA")
            crop = scene.get("crop")  # [x, y, w, h] in source pixels
            if crop:
                shot = shot.crop((crop[0], crop[1], crop[0] + crop[2], crop[1] + crop[3]))
            top = 222 if live else 320
            maxw, maxh = (W - 120, H - top - 40 - 52) if live else (W - 220, H - 360)
            sc = min(maxw / shot.width, maxh / (shot.height + (0 if live else 44)))
            sw, sh = int(shot.width * sc), int(shot.height * sc)
            fx, fy = (W - sw) // 2, top
            frame = Image.new("RGBA", (sw + 8, sh + 52), (0, 0, 0, 0))
            fd = ImageDraw.Draw(frame)
            fd.rounded_rectangle((0, 0, sw + 7, sh + 51), radius=18, fill=(28, 32, 60, 255), outline=(70, 80, 140, 255), width=2)
            for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
                fd.ellipse((18 + i * 26, 16, 34 + i * 26, 32), fill=c)
            fd.text((sw // 2, 14), scene.get("bar", "demo environment"), font=font("Inter-Medium.otf", 22), fill=MUTED, anchor="ma")
            frame.alpha_composite(shot.resize((sw, sh), Image.LANCZOS), (4, 48))
            scene["_video_box"] = (fx, fy + 48, sw, sh)  # where a live recording is overlaid
            hl = scene.get("highlight")  # [x, y, w, h] in (cropped) source pixels
            if hl:
                hx, hy = 4 + hl[0] * sc, 48 + hl[1] * sc
                fd.rounded_rectangle((hx - 6, hy - 6, hx + hl[2] * sc + 6, hy + hl[3] * sc + 6), radius=10, outline=YELLOW, width=6)
            im.alpha_composite(frame, (fx - 4, fy))
        elif t == "diagram":
            nodes, labels = scene["nodes"], scene.get("labels", [""] * len(scene["nodes"]))
            n = len(nodes)
            bw, bh, gap = 270, 170, (W - 220 - n * 270) / (n - 1)
            y = 470
            for i, (nd, lb) in enumerate(zip(nodes, labels)):
                x = 110 + i * (bw + gap)
                d.rounded_rectangle((x, y, x + bw, y + bh), radius=26, fill=(20, 24, 52, 235), outline=BLUE, width=4)
                d.text((x + bw / 2, y + 48), nd, font=font("Inter-Bold.otf", 58), fill=WHITE, anchor="ma")
                d.text((x + bw / 2, y + bh + 30), lb, font=font("Inter-Medium.otf", 32), fill=MUTED, anchor="ma")
                if i < n - 1:
                    ax0, ax1, ay = x + bw + 18, x + bw + gap - 18, y + bh / 2
                    d.line((ax0, ay, ax1, ay), fill=BLUE, width=6)
                    d.polygon([(ax1, ay), (ax1 - 22, ay - 14), (ax1 - 22, ay + 14)], fill=BLUE)
    return im.convert("RGB")


# ---- TTS -------------------------------------------------------------------
_kokoro = None


def tts(text, path, voice, speed):
    global _kokoro
    import soundfile as sf
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    lang = "en-gb" if voice.startswith("b") else "en-us"
    audio, sr = _kokoro.create(" ".join(text.split()), voice=voice, speed=speed, lang=lang)
    sf.write(path, audio, sr)
    return len(audio) / sr


def sentences(text):
    s = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return [x for x in s if x]


def srt_time(t):
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s - int(s)) * 1000):03d}"


def caption_chunks(text, max_words=9):
    out = []
    for s in sentences(text):
        w = s.split()
        while w:
            out.append(" ".join(w[:max_words]))
            w = w[max_words:]
    return out


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


# ---- assembly ---------------------------------------------------------------
PAD = 0.7  # seconds of silence after each scene


def still_segment(img_path, wav, dur, out, size="1920x1080", zoom=True):
    w, h = size.split("x")
    frames = int(math.ceil(dur * 30))
    vf = (f"scale={int(w)*2}:-1,zoompan=z='min(1+0.00005*on,1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={size}:fps=30"
          if zoom else f"scale={w}:{h},fps=30")
    run(["ffmpeg", "-y", "-loop", "1", "-i", str(img_path), "-i", str(wav), "-filter_complex",
         f"[0:v]{vf},format=yuv420p,fade=t=in:st=0:d=0.3,fade=t=out:st={dur-0.3:.2f}:d=0.3[v];[1:a]apad,atrim=0:{dur:.2f}[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", str(out)])


def video_duration(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).decode())


def content_crop(clip, pad=18, min_aspect=2.6, bg_thresh=40):
    """[x, y, w, h] around everything that ever appears on screen in a terminal recording (frames sampled every
    second), so the empty part of the window doesn't shrink the text. Left edge stays at 0 so prompts line up."""
    import numpy as np
    W, H = map(int, subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height", "-of", "csv=p=0:s=x", str(clip)]).decode().strip().split("x"))
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(clip), "-vf", "fps=1,format=gray",
                                   "-f", "rawvideo", "-"])
    frames = np.frombuffer(raw, np.uint8).reshape(-1, H, W)
    mask = (frames > bg_thresh).any(axis=0)
    ys, xs = np.where(mask)
    if not len(xs):
        return None
    x1 = min(W, int(xs.max()) + pad)
    y1 = min(H, int(ys.max()) + pad)
    w, h = x1, y1
    h = min(H, max(h, int(w / min_aspect)))  # never a thin strip
    return [0, 0, w - w % 2, h - h % 2]


def video_segment(slide_png, clip, box, wav, speech, out, rate=1.0, crop=None):
    """Live recording played inside the screen frame of the slide. The segment lasts as long as the longer of the
    narration and the clip (at `rate`), so a live run is never cut; the clip holds its last frame if the voice is longer."""
    x, y, w, h = box
    clip_dur = video_duration(clip) / rate
    dur = max(speech + PAD, clip_dur + 0.8)
    run(["ffmpeg", "-y", "-loop", "1", "-i", str(slide_png), "-i", str(clip), "-i", str(wav), "-filter_complex",
         f"[1:v]setpts=PTS/{rate},{f'crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]},' if crop else ''}scale={w}:{h}:force_original_aspect_ratio=decrease,crop='min(iw,{w})':'min(ih,{h})',pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
         f"tpad=stop_mode=clone:stop_duration={dur:.2f}[clip];"
         f"[0:v]scale=1920:1080,fps=30[bg];[bg][clip]overlay={x}:{y}:shortest=0,format=yuv420p,"
         f"fade=t=in:st=0:d=0.3,fade=t=out:st={dur-0.3:.2f}:d=0.3[v];[2:a]apad,atrim=0:{dur:.2f}[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", str(out)])
    return dur


def concat(parts, out, music=None, music_db=-24):
    lst = out.parent / (out.stem + "_list.txt")
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    tmp = out.parent / (out.stem + "_raw.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(tmp)])
    if music and Path(music).exists():
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(tmp)]).decode())
        run(["ffmpeg", "-y", "-i", str(tmp), "-stream_loop", "-1", "-i", str(music), "-filter_complex",
             f"[1:a]volume={music_db}dB,afade=t=in:d=2,afade=t=out:st={dur-3:.2f}:d=3[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
        tmp.unlink()
    else:
        shutil.move(tmp, out)
    lst.unlink()


def make_thumbnail(script, out):
    W, H = 1280, 720
    im = background(W, H)
    im = Image.alpha_composite(im, Image.new("RGBA", (W, H), (0, 0, 0, 40)))
    d = ImageDraw.Draw(im)
    d.text((60, 50), SERIES["label"], font=font("Inter-Bold.otf", 40), fill=BLUE)
    d.text((W - 60, 50), f"#{script['episode']:02d}", font=font("Inter-Bold.otf", 40), fill=WHITE, anchor="ra")
    fb = font("Inter-Bold.otf", 118)
    lines = script.get("thumbnail_text", script["title"]).split("\n")
    y = H / 2 - len(lines) * 128 / 2 - 10
    for l in lines:
        d.text((60, y), l, font=fb, fill=WHITE)
        y += 128
    d.rectangle((60, y + 10, 300, y + 22), fill=BLUE)
    d.text((60, H - 80), script.get("subtitle", ""), font=font("Inter-SemiBold.otf", 36), fill=MUTED)
    im.convert("RGB").save(out, quality=92)



def short_panel(scene, ep, W=1080, max_h=760):
    """Content panel for vertical Shorts: enlarged code, bullets or the 16:9 slide for diagrams/titles."""
    t = scene["type"]
    if t == "code":
        return code_image(scene["code"], scene.get("lang", "text"), W - 60, max_h, base=40)
    if t == "bullets":
        img = Image.new("RGBA", (W - 60, max_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((10, 0), scene["heading"], font=font("Inter-Bold.otf", 60), fill=WHITE)
        d.rectangle((10, 85, 200, 93), fill=BLUE)
        y, fb = 130, font("Inter-SemiBold.otf", 50)
        for b in scene["bullets"]:
            d.ellipse((14, y + 18, 32, y + 36), fill=BLUE)
            for l in wrap(d, b, fb, W - 160):
                d.text((60, y), l, font=fb, fill=WHITE)
                y += 62
            y += 22
        return img.crop((0, 0, W - 60, min(max_h, y + 10)))
    slide = render_slide(scene, ep).convert("RGBA")
    return slide.resize((W, int(W * 9 / 16)), Image.LANCZOS)

def short_crop(scene, max_w=960):
    """Region of a live recording shown in a Short: the scene's short_crop, else the left max_w pixels of the
    content crop (prompts and most output start at the left), so the text is readable on a phone."""
    if scene.get("short_crop"):
        return scene["short_crop"]
    x, y, w, h = scene["crop"]
    w = min(w, max_w)
    return [x, y, w - w % 2, h]


def live_short_panel(scene, W=1080, max_h=1000):
    """Shorts panel for a live recording: heading on top, then a hole the clip is overlaid into at full width."""
    cw, ch = short_crop(scene)[2:]
    vh = min(max_h - 90, int(W * ch / cw))
    vh -= vh % 2
    img = Image.new("RGBA", (W, 90 + vh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = 48
    while size > 30 and d.textlength(scene["heading"], font=font("Inter-Bold.otf", size)) > W - 80:
        size -= 2
    d.text((40, 0), scene["heading"], font=font("Inter-Bold.otf", size), fill=WHITE)
    d.rectangle((40, 66, 200, 72), fill=BLUE)
    d.rectangle((0, 90, W, 90 + vh), fill=(0, 0, 0, 255))
    return img, (0, 90, W, vh)


def make_short(scene, script, wav, dur, slide_png, out, workdir, clip=None):
    """Vertical 1080x1920: slide in the middle, captions burned in below, end card. A live screen scene plays its
    recording (cropped to the text, full width) instead of a still."""
    W, H = 1080, 1920
    chunks = caption_chunks(scene["narration"], 7)
    total_chars = sum(len(c) for c in chunks)
    vbox = None
    if clip is not None and scene.get("crop"):
        slide, vbox = live_short_panel(scene)
        rate = float(scene.get("video_rate", 1.0))
        extra = max(0.0, video_duration(clip) / rate + 0.5 - dur)
    else:
        slide, extra = short_panel(scene, script["episode"]), 0.0
    frames_dir = workdir / f"short_{scene['id']}"
    frames_dir.mkdir(exist_ok=True)
    concat_list, t = [], 0.0
    for i, c in enumerate(chunks):
        seg = dur * len(c) / total_chars + (extra if i == len(chunks) - 1 else 0.0)
        im = background(W, H)
        d = ImageDraw.Draw(im)
        d.text((60, 110), SERIES["label"], font=font("Inter-Bold.otf", 44), fill=BLUE)
        d.text((W - 60, 110), f"EP {script['episode']:02d}", font=font("Inter-Bold.otf", 44), fill=WHITE, anchor="ra")
        for j, l in enumerate(wrap(d, script["title"], font("Inter-Bold.otf", 64), W - 120)[:2]):
            d.text((60, 220 + j * 76), l, font=font("Inter-Bold.otf", 64), fill=WHITE)
        im.alpha_composite(slide, ((W - slide.width) // 2, 400))
        fc = font("Inter-Bold.otf", 62)
        lines = wrap(d, c, fc, W - 140)
        y = 400 + slide.height + 70
        for l in lines:
            d.text((W / 2, y), l, font=fc, fill=(255, 230, 120), anchor="ma", stroke_width=4, stroke_fill=(0, 0, 0))
            y += 80
        p = frames_dir / f"{i:03d}.png"
        im.convert("RGB").save(p)
        concat_list.append(f"file '{p.resolve()}'\nduration {seg:.3f}\n")
        t += seg
    end = background(W, H)
    d = ImageDraw.Draw(end)
    d.text((W / 2, 760), "Full episode", font=font("Inter-Bold.otf", 90), fill=WHITE, anchor="ma")
    d.text((W / 2, 870), "on YouTube", font=font("Inter-Bold.otf", 90), fill=WHITE, anchor="ma")
    d.rectangle((W / 2 - 150, 1000, W / 2 + 150, 1010), fill=BLUE)
    d.text((W / 2, 1060), f"{SERIES['name']} · @momentogalatico", font=font("Inter-SemiBold.otf", 48), fill=MUTED, anchor="ma")
    pe = frames_dir / "end.png"
    end.convert("RGB").save(pe)
    concat_list.append(f"file '{pe.resolve()}'\nduration 2.5\nfile '{pe.resolve()}'\n")
    lst = frames_dir / "list.txt"
    lst.write_text("".join(concat_list))
    total = dur + extra + 2.5
    music = ASSETS / "music.mp3"
    inputs = ["-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(wav)]
    if music.exists():
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        af = f"[1:a]apad,atrim=0:{total:.2f}[v1];[2:a]volume=-22dB,atrim=0:{total:.2f},afade=t=out:st={total-1.5:.2f}:d=1.5[m];[v1][m]amix=inputs=2:normalize=0[a]"
    else:
        af = f"[1:a]apad,atrim=0:{total:.2f}[a]"
    vf = "[0:v]fps=30,format=yuv420p[v]"
    if vbox:
        ci = 3 if music.exists() else 2
        inputs += ["-i", str(clip)]
        cx, cy, cw, ch = short_crop(scene)
        bx, by, bw, bh = vbox
        oy = 400 + by
        shown = dur + extra  # the clip plays during the narration, then the end card covers it
        vf = (f"[0:v]fps=30,format=yuv420p[bg];[{ci}:v]setpts=PTS/{rate},crop={cw}:{ch}:{cx}:{cy},"
              f"scale={bw}:{bh}:force_original_aspect_ratio=decrease,crop='min(iw,{bw})':'min(ih,{bh})',"
              f"pad={bw}:{bh}:0:0:color=black,tpad=stop_mode=clone:stop_duration={shown:.2f}[clip];"
              f"[bg][clip]overlay={bx}:{oy}:enable='lt(t,{shown:.2f})',format=yuv420p[v]")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[a]",
         "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", str(out)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--out", default="build")
    ap.add_argument("--voice")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--skip-shorts", action="store_true")
    ap.add_argument("--only-shorts", action="store_true")
    a = ap.parse_args()
    script = yaml.safe_load(Path(a.script).read_text(encoding="utf-8"))
    voice = a.voice or script.get("voice", "am_michael")
    out = Path(a.out)
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    SERIES.update(label=script.get("series_label", "MG LAB"), name=script.get("series_name", "MG Lab"),
                  prefix=script.get("file_prefix", "mglab"))
    ep = script["episode"]
    for sc in script["scenes"]:
        sc["_base"] = str(Path(a.script).parent)

    parts, srt, t = [], [], 0.0
    durations, seg_durs = {}, {}
    for i, sc in enumerate(script["scenes"]):
        png = work / f"{i:02d}_{sc['id']}.png"
        wav = work / f"{i:02d}_{sc['id']}.wav"
        clip = None
        if sc["type"] == "screen" and sc.get("video"):
            clip = Path(sc["video"]) if Path(sc["video"]).is_absolute() else Path(sc["_base"]) / sc["video"]
            if clip.exists():
                poster = work / f"{i:02d}_{sc['id']}_poster.png"
                run(["ffmpeg", "-y", "-sseof", "-0.1", "-i", str(clip), "-frames:v", "1", "-update", "1", str(poster)])
                sc["_poster"] = str(poster)
                if "crop" not in sc and sc.get("autocrop", True):
                    sc["crop"] = content_crop(clip)
                sc["_live"] = True
                sc["_clip"] = str(clip)
            else:
                print(f"  ! {sc['id']}: video {clip} missing, using the still image", flush=True)
                clip = None
        render_slide(sc, ep).save(png)
        if not wav.exists():
            tts(sc["narration"], wav, voice, a.speed)
        import soundfile as sf
        info = sf.info(str(wav))
        speech = info.frames / info.samplerate
        durations[sc["id"]] = (speech, wav, png)
        dur = speech + PAD
        if clip is not None:
            dur = max(dur, video_duration(clip) / float(sc.get("video_rate", 1.0)) + 0.8)
        seg_durs[sc["id"]] = dur
        chunks = caption_chunks(sc["narration"])
        total = sum(len(c) for c in chunks)
        ct = t
        for c in chunks:
            seg = speech * len(c) / total
            srt.append((ct, ct + seg, c))
            ct += seg
        if not a.only_shorts:
            seg_mp4 = work / f"{i:02d}_{sc['id']}.mp4"
            if clip is not None:
                video_segment(png, clip, sc["_video_box"], wav, speech, seg_mp4, float(sc.get("video_rate", 1.0)), sc.get("crop"))
            else:
                still_segment(png, wav, dur, seg_mp4, zoom=sc["type"] not in ("code", "screen"))
            parts.append(seg_mp4)
        t += dur
        print(f"[{i+1}/{len(script['scenes'])}] {sc['id']}: {speech:.1f}s", flush=True)

    base = f"{SERIES['prefix']}-ep{ep:02d}-{script['slug']}"
    if not a.only_shorts:
        concat(parts, out / f"{base}.mp4", ASSETS / "music.mp3")
        (out / f"{base}.srt").write_text(
            "".join(f"{n+1}\n{srt_time(s)} --> {srt_time(e)}\n{txt}\n\n" for n, (s, e, txt) in enumerate(srt)), encoding="utf-8")
        make_thumbnail(script, out / f"{base}-thumbnail.jpg")
        chapters, ct = [], 0.0
        for sc in script["scenes"]:
            chapters.append(f"{int(ct//60)}:{int(ct%60):02d} {sc['heading']}")
            ct += seg_durs[sc["id"]]
        (out / f"{base}-chapters.txt").write_text("\n".join(chapters), encoding="utf-8")
    if not a.skip_shorts:
        for sc in script["scenes"]:
            if sc.get("short"):
                speech, wav, png = durations[sc["id"]]
                make_short(sc, script, wav, speech, png, out / f"{base}-short-{sc['short']}.mp4", work,
                           Path(sc["_clip"]) if sc.get("_clip") else None)
                print("short:", sc["short"], flush=True)
    print("done ->", out)


if __name__ == "__main__":
    main()
