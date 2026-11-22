"""Represent various timestamp formats"""

import dataclasses
from datetime import UTC, datetime, timedelta

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


def decode_timestamp_dhm(data: bytes) -> datetime:
    ts_format = TimestampFormat(data[6:7])
    tzinfo = None if ts_format == TimestampFormat.DayHoursMinutesLocal else UTC
    now = datetime.now(tz=tzinfo)
    ts = datetime.strptime(data[:6].decode("ascii"), timestamp_formats_map[ts_format])
    maybe_ts = ts.replace(year=now.year, month=now.month, tzinfo=tzinfo)
    if maybe_ts > (now + FUTURE_TIMESTAMP_THRESHOLD):
        # can't have a timestamp in the future, so assume it's from last month
        if maybe_ts.month == 1:
            return maybe_ts.replace(year=maybe_ts.year - 1, month=12)
        return maybe_ts.replace(month=maybe_ts.month - 1)
    return maybe_ts


def decode_timestamp_hms(data: bytes) -> datetime:
    now = utcnow_tz()
    ts = datetime.strptime(
        data[:6].decode("ascii"),
        timestamp_formats_map[TimestampFormat.HoursMinutesSecondsZulu],
    )
    maybe_ts = ts.replace(year=now.year, month=now.month, day=now.day, tzinfo=UTC)
    if maybe_ts > (now + FUTURE_TIMESTAMP_THRESHOLD):
        # can't have a timestamp (too far) in the future, so assume it's from yesterday
        return maybe_ts - timedelta(days=1)
    return maybe_ts


def decode_timestamp_mdhm(data: bytes) -> datetime:
    now = utcnow_tz()
    ts = datetime.strptime(
        data[:8].decode("ascii"),
        timestamp_formats_map[TimestampFormat.MonthDayHoursMinutesZulu],
    ).replace(
        year=now.year,
        tzinfo=UTC,
    )
    if ts > (now + FUTURE_TIMESTAMP_THRESHOLD):
        # can't have a timestamp in the future, so assume it's from last year
        return ts.replace(year=ts.year - 1)
    return ts


@dataclasses.dataclass(frozen=True)
class Timestamp:
    """Represents a timestamp for an APRS information field."""

    timestamp_format: TimestampFormat = TimestampFormat.DayHoursMinutesZulu
    timestamp: datetime = dataclasses.field(default_factory=utcnow_tz)

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Timestamp":
        try:
            ts_format = TimestampFormat(raw[6:7])
            if ts_format in [
                TimestampFormat.DayHoursMinutesLocal,
                TimestampFormat.DayHoursMinutesZulu,
            ]:
                return cls(ts_format, decode_timestamp_dhm(raw))
            return cls(ts_format, decode_timestamp_hms(raw))
        except ValueError:
            # assume Month Day Hours Minutes
            return cls(
                TimestampFormat.MonthDayHoursMinutesZulu, decode_timestamp_mdhm(raw)
            )

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
    timestamp: Timestamp | None
