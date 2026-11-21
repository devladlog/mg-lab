from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import evaluate as ev
from . import samples
from .limits import F0_CALLS_PER_MINUTE, MAX_BYTES, MAX_SIDE, MIN_SIDE, V4_FORMATS
from .pipeline import Paced, process, write

ROOT = Path(__file__).resolve().parents[2]


def _backend(args):
    from .azure_backend import AzureVisionBackend, make_client
    return Paced(AzureVisionBackend(make_client(args.endpoint)), args.calls_per_minute)


def main(argv: list[str] | None = None, backend=None) -> int:
    p = argparse.ArgumentParser(prog="photoscan")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("limits", help="print the documented limits (no Azure call)")
    s = sub.add_parser("samples", help="draw the fictional label photos")
    s.add_argument("--out", default="build/photos")
    f = sub.add_parser("fetch-sample", help="download the Learn sample photo (a person at a meeting-room display)")
    f.add_argument("--out", default="build/photos/learn-presentation.png")
    for name in ("analyze", "evaluate"):
        a = sub.add_parser(name)
        a.add_argument("--endpoint")
        a.add_argument("--calls-per-minute", type=int, default=F0_CALLS_PER_MINUTE)
        a.add_argument("--out", default="build/out")
    a = sub.choices["analyze"]
    a.add_argument("photo")
    e = sub.choices["evaluate"]
    e.add_argument("--cases", default=str(ROOT / "data" / "cases.json"))
    e.add_argument("--sample-dir", default="build/photos")
    e.add_argument("--skip-people", action="store_true")
    args = p.parse_args(argv)

    if args.cmd == "limits":
        print(f"formats: {', '.join(sorted(V4_FORMATS))}\nsize: less than {MAX_BYTES // 1_048_576} MB; each side > {MIN_SIDE} and < {MAX_SIDE} px")
        print(f"free tier: {F0_CALLS_PER_MINUTE} calls per minute (Learn FAQ); one image per call")
        print("Image Analysis 4.0 is deprecated; Learn: retired on 25 September 2028")
        return 0
    if args.cmd == "samples":
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for k, v in samples.generate().items():
            (out / (k + (".jpg" if k == "label-phone-rotated" else ".png"))).write_bytes(v)
            print("wrote", k)
        return 0
    if args.cmd == "fetch-sample":
        print("wrote", samples.fetch_sample(Path(args.out)))
        return 0
    backend = backend or _backend(args)
    if args.cmd == "analyze":
        r = process(Path(args.photo).read_bytes(), backend, Path(args.photo).stem)
        s = write(r, Path(args.out))
        a = r.analysis
        print(f"photo      {r.id}   notes: {', '.join(r.notes) or '-'}")
        if a:
            print(f"caption    {a.caption!r} ({a.caption_confidence:.2f})" if a.caption else "caption    -")
            print("tags       " + ", ".join(f"{n} {c:.2f}" for n, c in a.tags[:6]))
            print("objects    " + (", ".join(f"{n} {c:.2f}" for n, c, _ in a.objects[:5]) or "-"))
            print("text       " + (" | ".join(ln.text for ln in a.lines[:6]) or "-"))
            print("people     " + (", ".join(f"{x.confidence:.2f}" for x in a.people) or "none") + f"   blurred: {len(r.blurred)}")
            print("asset tag  " + (", ".join(f"{t.tag} ({t.confidence:.2f}{', corrected' if t.corrected else ''})" for t in r.tags) or "none"))
        print(f"decision   {r.decision}: {'; '.join(r.reasons)}")
        print(f"wrote      {Path(args.out)}/{r.id}.redacted.png, .thumb.png, .json (the original is never written)")
        return 1 if r.error else 0
    rep = ev.evaluate(backend, Path(args.cases), Path(args.sample_dir), args.skip_people)
    print(ev.render(rep))
    return 0 if rep.passed else 1


if __name__ == "__main__":
    sys.exit(main())
