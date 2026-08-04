"""Custom SQLAlchemy column types.

SQLite has no native date/time or decimal storage, so both are handled
explicitly here instead of relying on driver-level coercion:

* :class:`UtcDateTime` stores timezone-aware datetimes as ISO-8601 UTC text and
  always returns timezone-aware UTC datetimes.
* :class:`DecimalText` stores :class:`decimal.Decimal` as text so numeric values
  typed by the user (comparison metrics, position sizes) never pass through a
  binary float.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import String, Text, TypeDecorator
from sqlalchemy.engine import Dialect


class UtcDateTime(TypeDecorator[dt.datetime]):
    """Timezone-aware datetime persisted as ``YYYY-MM-DDTHH:MM:SS.ffffff+00:00``."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = dt.datetime.fromisoformat(value)
        if not isinstance(value, dt.datetime):
            raise TypeError(f"expected datetime, got {type(value)!r}")
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.UTC)
        return value.astimezone(dt.UTC).isoformat()

    def process_result_value(self, value: Any, dialect: Dialect) -> dt.datetime | None:
        if value is None:
            return None
        if isinstance(value, dt.datetime):
            parsed = value
        else:
            parsed = dt.datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.UTC)
        return parsed.astimezone(dt.UTC)


class IsoDate(TypeDecorator[dt.date]):
    """Calendar date persisted as ``YYYY-MM-DD`` text (no timezone semantics)."""

    impl = String(10)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = dt.date.fromisoformat(value)
        if isinstance(value, dt.datetime):
            value = value.date()
        return value.isoformat()

    def process_result_value(self, value: Any, dialect: Dialect) -> dt.date | None:
        if value is None:
            return None
        if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
            return value
        return dt.date.fromisoformat(str(value)[:10])


class DecimalText(TypeDecorator[Decimal]):
    """Exact decimal persisted as text."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return format(value, "f")
        try:
            return format(Decimal(str(value)), "f")
        except InvalidOperation as exc:  # pragma: no cover - guarded by schemas
            raise ValueError(f"{value!r} is not a valid decimal") from exc

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))


def utcnow() -> dt.datetime:
    """Current time as an aware UTC datetime."""

    return dt.datetime.now(dt.UTC)
