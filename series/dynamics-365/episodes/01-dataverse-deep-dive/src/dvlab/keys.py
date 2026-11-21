"""Build the alternate-key part of a Web API URL: accounts(accountnumber='ABC123').

Learn documents that GET/PATCH by alternate key don't work when the key value contains any of
/ < > * % & : \\ ? +  -- so we refuse those values up front with a clear error instead of
sending a request that fails with a confusing 400/404.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Mapping, Union
from uuid import UUID

UNSUPPORTED_KEY_CHARS = set('/<>*%&:\\?+')

KeyValue = Union[str, int, Decimal, float, date, datetime, UUID]


class KeyValueError(ValueError):
    pass


def _literal(value: KeyValue) -> str:
    if isinstance(value, bool):
        raise KeyValueError("Boolean columns can't be part of an alternate key.")
    if isinstance(value, str):
        bad = sorted(UNSUPPORTED_KEY_CHARS.intersection(value))
        if bad:
            raise KeyValueError(
                f"Alternate key value {value!r} contains {' '.join(bad)}: "
                "Dataverse can't GET/PATCH by an alternate key with these characters."
            )
        return "'" + value.replace("'", "''") + "'"   # OData: a quote inside a string is doubled
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, Decimal, float)):
        return str(value)
    raise KeyValueError(f"Unsupported key type {type(value).__name__}")


def key_segment(key: Mapping[str, KeyValue]) -> str:
    """{'mgl_requestcode': 'PR-0001'} -> "(mgl_requestcode='PR-0001')"; multi-part keys keep their order."""
    if not key:
        raise KeyValueError("An alternate key needs at least one column.")
    return "(" + ",".join(f"{col}={_literal(val)}" for col, val in key.items()) + ")"
