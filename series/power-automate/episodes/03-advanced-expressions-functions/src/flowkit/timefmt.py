"""Timestamps, time zones and number formatting for the flowkit evaluator.

Two details from the functions reference shape this module:

* A timestamp has a *kind*. ``utcNow()`` and ``convertToUtc()`` return UTC values that end in ``Z``;
  ``convertFromUtc()`` returns "the timestamp converted to the target time zone without the timezone
  UTC offset", e.g. ``2018-01-01T00:00:00.0000000``. Date functions keep the kind of their input.
* Time zones are Windows time zone names (``GMT Standard Time``, ``W. Europe Standard Time``...),
  not IANA names. We map the handful we use to IANA zones and let Python's zoneinfo do the DST maths.

Assumption (flowkit, not documented): when a timestamp without an offset is compared or converted
to ticks, it is treated as UTC. That is the strict reading that exposes the "summer time" bug in
episode 3; demo.md has a step that confirms it in the lab tenant.

References:
  https://learn.microsoft.com/azure/logic-apps/expression-functions-reference#convertFromUtc
  https://learn.microsoft.com/azure/logic-apps/expression-functions-reference#formatNumber
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo


class TimeError(ValueError):
    pass


UTC_KIND, LOCAL_KIND = "utc", "unspecified"

# Windows time zone id -> IANA zone. Only zones used in this repo's flows and tests.
WINDOWS_ZONES = {
    "UTC": "UTC",
    "Coordinated Universal Time": "UTC",
    "GMT Standard Time": "Europe/London",          # (UTC+00:00) Dublin, Edinburgh, Lisbon, London
    "W. Europe Standard Time": "Europe/Berlin",    # (UTC+01:00) Amsterdam, Berlin, Bern, Rome...
    "Romance Standard Time": "Europe/Paris",       # (UTC+01:00) Brussels, Copenhagen, Madrid, Paris
    "Pacific Standard Time": "America/Los_Angeles",
    "Eastern Standard Time": "America/New_York",
}


@dataclass(frozen=True)
class Stamp:
    """A wall-clock time plus its kind ('utc' or 'unspecified')."""
    wall: datetime  # naive
    kind: str

    def as_utc(self) -> datetime:
        return self.wall.replace(tzinfo=timezone.utc)


_ISO_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?)?(Z|[+-]\d{2}:\d{2})?$"
)
_US_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?: (\d{1,2}):(\d{2})(?::(\d{2}))?)?$")


def parse_stamp(text) -> Stamp:
    if not isinstance(text, str):
        raise TimeError(f"Expected a timestamp string, got {type(text).__name__}: {text!r}")
    t = text.strip()
    m = _ISO_RE.match(t)
    if m:
        y, mo, d, h, mi, s, frac, tz = m.groups()
        micro = int((frac or "0")[:6].ljust(6, "0"))
        wall = datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0), micro)
        if not tz:
            return Stamp(wall, LOCAL_KIND)
        if tz != "Z":
            sign = 1 if tz[0] == "+" else -1
            wall = wall - sign * timedelta(hours=int(tz[1:3]), minutes=int(tz[4:6]))
        return Stamp(wall, UTC_KIND)
    m = _US_RE.match(t)  # invariant culture: MM/dd/yyyy [HH:mm[:ss]] (used in the reference examples)
    if m:
        mo, d, y, h, mi, s = m.groups()
        return Stamp(datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0)), LOCAL_KIND)
    raise TimeError(f"{text!r} is not a valid timestamp")


def parse_timestamp(text) -> datetime:
    """Aware UTC datetime (a timestamp without an offset is treated as UTC, see module docstring)."""
    return parse_stamp(text).as_utc()


def zone(name: str) -> ZoneInfo:
    if name not in WINDOWS_ZONES:
        raise TimeError(f"Unknown or unmapped time zone {name!r}. Use a Windows time zone id, "
                        f"e.g. 'GMT Standard Time' (mapped here: {sorted(WINDOWS_ZONES)})")
    return ZoneInfo(WINDOWS_ZONES[name])


def from_utc(stamp: Stamp, tz_name: str) -> Stamp:
    local = stamp.as_utc().astimezone(zone(tz_name))
    return Stamp(local.replace(tzinfo=None), UTC_KIND if WINDOWS_ZONES[tz_name] == "UTC" else LOCAL_KIND)


def to_utc(stamp: Stamp, tz_name: str) -> Stamp:
    """Interpret the wall clock in tz_name and return UTC. A 'Z' input is already UTC."""
    if stamp.kind == UTC_KIND:
        return stamp
    aware = stamp.wall.replace(tzinfo=zone(tz_name))
    return Stamp(aware.astimezone(timezone.utc).replace(tzinfo=None), UTC_KIND)


# ----------------------------------------------------------------------------- formatting
_NAMES = {
    "en-us": (["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
              ["January", "February", "March", "April", "May", "June", "July", "August", "September",
               "October", "November", "December"]),
    # Only the locales whose output appears in the reference examples (formatDateTime).
    "fr-fr": (["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
              ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
               "octobre", "novembre", "décembre"]),
    "es-es": (["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
              ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
               "octubre", "noviembre", "diciembre"]),
}


def _names(locale: str | None):
    key = (locale or "en-us").lower()
    if key not in _NAMES:
        raise TimeError(f"flowkit has no day/month names for locale {locale!r} (supported: {sorted(_NAMES)})")
    return _NAMES[key]


def format_stamp(stamp: Stamp, fmt: str | None = "o", locale: str | None = None) -> str:
    dt = stamp.wall
    fmt = fmt or "o"
    if fmt in ("o", "O"):
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond:06d}0" + ("Z" if stamp.kind == UTC_KIND else "")
    if fmt == "s":
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    if fmt == "D":
        fmt = "dddd, MMMM d, yyyy"   # en-US long date: "Monday, January 1, 2018"
    elif fmt == "d":
        fmt = "M/d/yyyy"
    elif len(fmt) == 1:
        raise TimeError(f"flowkit doesn't implement the standard date format {fmt!r}")
    days, months = _names(locale)
    tokens = re.findall(r"yyyy|yy|MMMM|MMM|MM|M|dddd|ddd|dd|d|HH|H|hh|h|mm|ss|fffffff|fff|tt|K|'[^']*'|\\.|.", fmt)
    out = []
    for t in tokens:
        if t == "yyyy": out.append(f"{dt.year:04d}")
        elif t == "yy": out.append(f"{dt.year % 100:02d}")
        elif t == "MMMM": out.append(months[dt.month - 1])
        elif t == "MMM": out.append(months[dt.month - 1][:3])
        elif t == "MM": out.append(f"{dt.month:02d}")
        elif t == "M": out.append(str(dt.month))
        elif t == "dddd": out.append(days[dt.weekday()])
        elif t == "ddd": out.append(days[dt.weekday()][:3])
        elif t == "dd": out.append(f"{dt.day:02d}")
        elif t == "d": out.append(str(dt.day))
        elif t == "HH": out.append(f"{dt.hour:02d}")
        elif t == "H": out.append(str(dt.hour))
        elif t == "hh": out.append(f"{(dt.hour % 12) or 12:02d}")
        elif t == "h": out.append(str((dt.hour % 12) or 12))
        elif t == "mm": out.append(f"{dt.minute:02d}")
        elif t == "ss": out.append(f"{dt.second:02d}")
        elif t == "fffffff": out.append(f"{dt.microsecond:06d}0")
        elif t == "fff": out.append(f"{dt.microsecond // 1000:03d}")
        elif t == "tt": out.append("AM" if dt.hour < 12 else "PM")
        elif t == "K": out.append("Z" if stamp.kind == UTC_KIND else "")
        elif t.startswith("'"): out.append(t[1:-1])
        elif t.startswith("\\"): out.append(t[1:])
        else: out.append(t)
    return "".join(out)


def format_timestamp(dt: datetime, fmt: str = "o") -> str:
    """Format an aware UTC datetime (kept for callers from episodes 1 and 2)."""
    return format_stamp(Stamp(dt.astimezone(timezone.utc).replace(tzinfo=None), UTC_KIND), fmt)


def ticks(stamp: Stamp) -> int:
    """100-nanosecond intervals since 0001-01-01T00:00:00, like .NET DateTime.Ticks."""
    delta = stamp.wall - datetime(1, 1, 1)
    return (delta.days * 86400 + delta.seconds) * 10_000_000 + delta.microseconds * 10


def timespan(delta: timedelta) -> str:
    """.NET TimeSpan default format: [-][d.]hh:mm:ss[.fffffff] (dateDifference returns this)."""
    sign = "-" if delta < timedelta(0) else ""
    delta = abs(delta)
    days, rem = delta.days, delta.seconds
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    out = f"{sign}{str(days) + '.' if days else ''}{h:02d}:{m:02d}:{s:02d}"
    if delta.microseconds:
        out += f".{delta.microseconds:06d}0"
    return out


# ----------------------------------------------------------------------------- numbers
# Culture data only for the locales the reference shows output for (en-US default, is-IS).
_CULTURES = {
    "en-us": {"group": ",", "decimal": ".", "currency": "$", "currency_pattern": "{s}{n}"},
    "is-is": {"group": ".", "decimal": ",", "currency": "kr", "currency_pattern": "{n} {s}"},
}


def _culture(locale: str | None) -> dict:
    key = (locale or "en-us").lower()
    if key not in _CULTURES:
        raise TimeError(f"flowkit has no number culture data for {locale!r} (supported: {sorted(_CULTURES)}); "
                        f"use a custom pattern such as '#,##0.00' with 'en-US' if you need a stable result")
    return _CULTURES[key]


def _digits(value, decimals: int) -> tuple[str, str, bool]:
    """(integer digits, fraction digits, negative), rounded half away from zero."""
    d = Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    neg = d < 0
    text = f"{abs(d):f}"
    whole, _, frac = text.partition(".")
    return whole, frac, neg


def _group(whole: str, sep: str) -> str:
    out = []
    while len(whole) > 3:
        out.insert(0, whole[-3:])
        whole = whole[:-3]
    out.insert(0, whole)
    return sep.join(out)


def format_number(value, fmt: str, locale: str | None = None) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TimeError(f"formatNumber() expects a number, got {value!r}")
    c = _culture(locale)
    m = re.fullmatch(r"([CcNnFfDd])(\d{0,2})", fmt)
    if m:
        kind, prec = m.group(1).upper(), m.group(2)
        if kind == "D":
            if not isinstance(value, int):
                raise TimeError("The 'D' format only supports integers")
            text = str(abs(value)).rjust(int(prec or 0), "0")
            return ("-" if value < 0 else "") + text
        decimals = int(prec) if prec else 2
        whole, frac, neg = _digits(value, decimals)
        if kind in ("N", "C"):
            whole = _group(whole, c["group"])
        number = whole + (c["decimal"] + frac if decimals else "")
        if kind == "C":
            number = c["currency_pattern"].format(s=c["currency"], n=number)
        return ("-" if neg else "") + number
    # custom pattern: optional literal prefix/suffix around a run of 0 # , .
    m = re.fullmatch(r"([^0#,.]*)([0#,]+)(?:\.([0#]+))?([^0#,.]*)", fmt)
    if not m:
        raise TimeError(f"flowkit doesn't implement the number format {fmt!r}")
    prefix, int_part, frac_part, suffix = m.groups()
    frac_part = frac_part or ""
    max_dec, min_dec = len(frac_part), frac_part.count("0")
    whole, frac, neg = _digits(value, max_dec)
    frac = frac.rstrip("0").ljust(min_dec, "0") if max_dec else ""
    min_int = int_part.replace(",", "").count("0")
    whole = whole.lstrip("0").rjust(min_int, "0") if whole != "0" or min_int else ""
    if "," in int_part:
        whole = _group(whole, c["group"])
    number = whole + (c["decimal"] + frac if frac else "")
    return ("-" if neg else "") + prefix + number + suffix
