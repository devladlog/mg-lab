#!/usr/bin/env python3
"""Where were the threads busy? Reads the Speedscope file that `dotnet-trace collect --format Speedscope` writes next to the trace.

With the `dotnet-sampled-thread-time` profile every thread is a speedscope "evented" profile whose stacks end in a pseudo
frame: CPU_TIME or UNMANAGED_CODE_TIME (the converter's labels; in the files from this episode, threads parked in a wait
end in UNMANAGED_CODE_TIME and threads running managed code, calls into SQLite included, end in CPU_TIME). This keeps the
CPU_TIME intervals only ("busy") and reports, per method, **self** time (the method itself was the deepest real frame) and
**inclusive** time (it was anywhere on the stack), as a share of all busy time in the trace. The profile estimates wall clock
time, so this is where threads were busy, not a CPU-seconds measurement.

    python3 tools/speedscope_top.py slow.speedscope.json                   # top 10 by self time
    python3 tools/speedscope_top.py slow.speedscope.json --match Contoso   # + inclusive time of every frame containing "Contoso"
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

BUSY = "CPU_TIME"
IDLE = {"CPU_TIME", "UNMANAGED_CODE_TIME"}


def analyze(doc: dict) -> tuple[float, Counter, Counter, list[str]]:
    """(total busy ms, self ms per frame index, inclusive ms per frame index, frame names)."""
    names = [f["name"] for f in doc["shared"]["frames"]]
    has_pseudo = BUSY in names
    self_ms: Counter = Counter()
    incl_ms: Counter = Counter()
    total = 0.0

    def add(stack: list[int], ms: float) -> None:
        nonlocal total
        if ms <= 0 or not stack:
            return
        if has_pseudo and names[stack[-1]] != BUSY:
            return                                   # waiting, not computing
        real = [f for f in stack if names[f] not in IDLE]
        if not real:
            return
        self_ms[real[-1]] += ms
        for f in set(real):
            incl_ms[f] += ms
        total += ms

    for profile in doc["profiles"]:
        if profile["type"] == "evented":
            stack: list[int] = []
            last = profile["startValue"]
            for event in profile["events"]:
                add(stack, event["at"] - last)
                last = event["at"]
                if event["type"] == "O":
                    stack.append(event["frame"])
                else:                                # "C": close this frame (and anything left open above it)
                    while stack and stack[-1] != event["frame"]:
                        stack.pop()
                    if stack:
                        stack.pop()
        elif profile["type"] == "sampled":
            for sample, weight in zip(profile["samples"], profile["weights"], strict=True):
                add(list(sample), weight)
        else:
            raise ValueError(f"unsupported speedscope profile type: {profile['type']!r}")
    return total, self_ms, incl_ms, names


def short(name: str, width: int = 110) -> str:
    """'Assembly!Namespace.Type.Method(args)' without the argument list, cut to `width`."""
    name = name.split("(")[0] if "(" in name else name
    return name if len(name) <= width else name[: width - 1] + "…"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Where the threads were busy, from a dotnet-trace Speedscope file")
    parser.add_argument("file")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--match", help="also list the inclusive time of every frame whose name contains this text")
    args = parser.parse_args(argv[1:])
    with open(args.file, encoding="utf-8") as handle:
        doc = json.load(handle)
    total, self_ms, incl_ms, names = analyze(doc)
    if total == 0:
        print("no busy samples in this file (was the process idle while tracing?)", file=sys.stderr)
        return 1
    print(f"Busy thread time in the trace: {total / 1000:.1f} s (all threads added up)")
    print(f"\nTop {args.top} by self time")
    for frame, ms in self_ms.most_common(args.top):
        print(f"{100 * ms / total:5.1f}%  {short(names[frame])}")
    if args.match:
        print(f"\nInclusive time of frames containing {args.match!r}")
        for frame, ms in incl_ms.most_common():
            if args.match in names[frame] and not names[frame].startswith("Process"):
                print(f"{100 * ms / total:5.1f}%  {short(names[frame])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
