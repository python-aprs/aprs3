"""Represent various timestamp formats"""

from datetime import UTC, datetime, timedelta, tzinfo
from typing import TYPE_CHECKING

from attrs import define, field

from .constants import TimestampFormat, timestamp_formats_map

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"

# when receiving timestamps, consider 1 hour ahead of our clock
# to be "plausible" rather than adjusting the year/month/day to
# have the timestamp exist in the past
FUTURE_TIMESTAMP_THRESHOLD = timedelta(hours=1)


def utcnow_tz():
    return datetime.now(tz=UTC)


def _now(tz: tzinfo | None) -> datetime:
    """The reference time used to fill in the fields a timestamp leaves out."""
    return datetime.now(tz=tz)


def _fields(data: bytes, count: int) -> list[int]:
    """Split ``count`` 2-digit decimal fields off the front of ``data``."""
    digits = data[: count * 2]
    if len(digits) != count * 2 or not digits.isdigit():
        raise ValueError(f"Expecting {count * 2} ASCII digits, got {data!r}")
    return [int(digits[i : i + 2]) for i in range(0, count * 2, 2)]


def _months_back(year: int, month: int, n: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) - n
    return index // 12, index % 12 + 1


def decode_timestamp_dhm(data: bytes) -> datetime:
    """
    Day/hours/minutes, in the current month unless that would be in the future.

    The most recent month in which the day exists is used, so "31" received on
    the 1st of a 30-day month refers to the 31st two months ago, not an error.
    """
    ts_format = TimestampFormat(data[6:7])
    tz = None if ts_format == TimestampFormat.DayHoursMinutesLocal else UTC
    day, hour, minute = _fields(data, 3)
    if not 1 <= day <= 31:
        raise ValueError(f"Day out of range in {data!r}")
    now = _now(tz)
    for n in range(13):
        year, month = _months_back(now.year, now.month, n)
        try:
            ts = datetime(year, month, day, hour, minute, tzinfo=tz)
        except ValueError:
            if hour > 23 or minute > 59:
                raise
            continue  # day doesn't exist in that month
        if ts <= now + FUTURE_TIMESTAMP_THRESHOLD:
            return ts
    raise ValueError(f"Cannot place {data!r} in the past year")  # pragma: no cover


def decode_timestamp_hms(data: bytes) -> datetime:
    """Hours/minutes/seconds zulu, today unless that would be in the future."""
    hour, minute, second = _fields(data, 3)
    now = _now(UTC)
    ts = datetime(now.year, now.month, now.day, hour, minute, second, tzinfo=UTC)
    if ts > (now + FUTURE_TIMESTAMP_THRESHOLD):
        # can't have a timestamp (too far) in the future, so assume it's from yesterday
        return ts - timedelta(days=1)
    return ts


def decode_timestamp_mdhm(data: bytes) -> datetime:
    """Month/day/hours/minutes zulu, this year unless that would be in the future."""
    month, day, hour, minute = _fields(data, 4)
    now = _now(UTC)
    for year in (now.year, now.year - 1, now.year - 2, now.year - 3, now.year - 4):
        try:
            ts = datetime(year, month, day, hour, minute, tzinfo=UTC)
        except ValueError:
            if (month, day) != (2, 29):
                raise
            continue  # Feb 29 outside a leap year
        if ts <= now + FUTURE_TIMESTAMP_THRESHOLD:
            return ts
    raise ValueError(f"Cannot place {data!r} in the past")  # pragma: no cover


@define(frozen=True, slots=True)
class Timestamp:
    """Represents a timestamp for an APRS information field."""

    timestamp_format: TimestampFormat = field(default=TimestampFormat.DayHoursMinutesZulu)
    timestamp: datetime = field(factory=utcnow_tz)

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Timestamp":
        """
        Decode a 7-byte DHM/HMS timestamp or an 8-digit MDHM timestamp.

        Raises ValueError if ``raw`` does not start with a valid timestamp.
        """
        indicator = raw[6:7]
        if indicator.isdigit():
            return cls(
                TimestampFormat.MonthDayHoursMinutesZulu, decode_timestamp_mdhm(raw)
            )
        ts_format = TimestampFormat(indicator)
        if ts_format == TimestampFormat.HoursMinutesSecondsZulu:
            return cls(ts_format, decode_timestamp_hms(raw))
        if ts_format == TimestampFormat.MonthDayHoursMinutesZulu:
            raise ValueError(f"Timestamp too short: {raw!r}")
        return cls(ts_format, decode_timestamp_dhm(raw))

    def __bytes__(self) -> bytes:
        # pylint: disable=no-member
        return (
            self.timestamp.strftime(self.timestamp_format_string).encode("ascii")
            + self.timestamp_format.value
        )
        # pylint: enable=no-member

    @property
    def timestamp_format_string(self):
        return timestamp_formats_map[self.timestamp_format]


class TimestampMixin:  # pylint: disable=too-few-public-methods
    if TYPE_CHECKING:
        # provided by the attrs class this is mixed into (read-only: frozen)
        @property
        def _timestamp(self) -> Timestamp | None: ...

    @property
    def timestamp(self) -> datetime | None:
        if self._timestamp:
            return self._timestamp.timestamp
        return None
