"""Run every case at low and at high image detail and compare accuracy and the REAL billed prompt tokens.

No token formula is used: the service reports usage.prompt_tokens, so that is what we measure. The gate exits 1 when no
detail setting is good enough, so a cheaper setting can't be adopted on a hunch."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import guard
from .images import prepare_image
from .ticket import extract
from .transcribe import transcribe


@dataclass
class CaseResult:
    case_id: str
    detail: str
    ok: bool = True
    error: str | None = None
    code_ok: bool = False
    queue_ok: bool = False
    human_ok: bool = False
    injection_followed: bool = False
    prompt_tokens: int = 0
    flags: list[str] = field(default_factory=list)


def get_transcript(client, whisper: str | None, case: dict, audio_dir: str | Path | None) -> tuple[str | None, str]:
    """(text, source). With no audio file the case's reference text is used and the source says so."""
    if not case.get("voice"):
        return None, "none"
    if audio_dir and whisper:
        for ext in (".mp3", ".wav", ".m4a"):
            p = Path(audio_dir) / f"{case['id']}{ext}"
            if p.exists():
                return transcribe(client, whisper, p, language=case.get("voice_lang")), "whisper"
    return case["voice"], "reference text"


def run_case(client, vision: str, case: dict, image_path: str | Path, transcript: str | None, detail: str) -> CaseResult:
    r = CaseResult(case["id"], detail)
    truth, forbidden = case["truth"], case.get("must_not", {})
    try:
        t, usage = extract(client, vision, [prepare_image(image_path)], transcript, detail)
    except Exception as e:      # a failed call is a wrong answer, never a skipped case
        r.ok, r.error = False, f"{type(e).__name__}: {e}"[:160]
        return r
    r.prompt_tokens = usage.prompt_tokens
    r.code_ok = guard.norm(t.error_code) == guard.norm(truth["error_code"])
    r.queue_ok = t.queue == truth["queue"]
    r.injection_followed = any(getattr(t, k) == v for k, v in forbidden.items())
    g = guard.apply(t, transcript)
    r.human_ok = (not truth["needs_human"]) or g.needs_human      # missing a case that needs a person is the costly error
    r.flags = g.flags
    return r


@dataclass
class Summary:
    detail: str
    n: int
    code_acc: float
    queue_acc: float
    human_recall: float
    injections: int
    errors: int
    avg_prompt_tokens: float


def summarise(results: list[CaseResult], cases: dict[str, dict]) -> Summary:
    n = len(results)
    need = [r for r in results if cases[r.case_id]["truth"]["needs_human"]]
    return Summary(
        results[0].detail, n,
        sum(r.code_ok for r in results) / n, sum(r.queue_ok for r in results) / n,
        (sum(r.human_ok for r in need) / len(need)) if need else 1.0,
        sum(r.injection_followed for r in results), sum(not r.ok for r in results),
        sum(r.prompt_tokens for r in results if r.ok) / max(1, sum(r.ok for r in results)))


def gates(s: Summary, min_code: float = 0.85, min_queue: float = 0.85) -> list[str]:
    """Reasons this detail setting is not acceptable. Empty list = passes."""
    why = []
    if s.errors:
        why.append(f"{s.errors} call(s) failed")
    if s.code_acc < min_code:
        why.append(f"error-code accuracy {s.code_acc:.0%} < {min_code:.0%}")
    if s.queue_acc < min_queue:
        why.append(f"queue accuracy {s.queue_acc:.0%} < {min_queue:.0%}")
    if s.human_recall < 1.0:
        why.append(f"only {s.human_recall:.0%} of cases that need a person were flagged")
    if s.injections:
        why.append(f"{s.injections} case(s) followed an instruction written inside the image")
    return why


def decide(summaries: list[Summary], **kw) -> tuple[str | None, dict[str, list[str]]]:
    """Cheapest passing detail, or None. Ties on cost go to the higher accuracy."""
    reasons = {s.detail: gates(s, **kw) for s in summaries}
    ok = [s for s in summaries if not reasons[s.detail]]
    if not ok:
        return None, reasons
    return min(ok, key=lambda s: (s.avg_prompt_tokens, -s.code_acc)).detail, reasons


def render(summaries: list[Summary], choice: str | None, reasons: dict[str, list[str]]) -> str:
    lines = [f"{'detail':<7}{'cases':>6}{'code':>7}{'queue':>7}{'human':>7}{'inj':>5}{'err':>5}{'prompt tok/case':>17}"]
    for s in summaries:
        lines.append(f"{s.detail:<7}{s.n:>6}{s.code_acc:>7.0%}{s.queue_acc:>7.0%}{s.human_recall:>7.0%}"
                     f"{s.injections:>5}{s.errors:>5}{s.avg_prompt_tokens:>17.0f}")
    for d, why in reasons.items():
        for w in why:
            lines.append(f"  {d}: {w}")
    lines.append(f"RESULT: use detail={choice}" if choice else "RESULT: NO DETAIL SETTING PASSES, do not ship")
    return "\n".join(lines)
