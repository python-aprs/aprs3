"""common substructure parsers for APRS formats."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .constants import TimestampFormat
from .decimaldegrees import dm2decimal


POSITION_UNCOMPRESSED_SIGNATURE = tuple(chr(c) for c in range(ord(b"0"), ord(b"9")))
# when receiving timestamps, consider 1 hour ahead of our clock
# to be "plausible" rather than adjusting the year/month/day to
# have the timestamp exist in the past
FUTURE_TIMESTAMP_THRESHOLD = timedelta(hours=1)


def decode_position_uncompressed(data: bytes):
    """
    :return: dict with keys lat, long, sym_table_id, symbol_code
    """
    text = data.decode("ascii")
    if not text.startswith(POSITION_UNCOMPRESSED_SIGNATURE):
        raise ValueError("{!r} is not an uncompressed position".format(data[:19]))
    lat_degrees = int(text[:2])
    lat_minutes = Decimal(text[2:7])
    lat_sign = -1 if text[7:8] == "S" else 1
    lat = dm2decimal(lat_degrees, lat_minutes) * lat_sign
    sym_table_id = data[8:9]
    long_degrees = int(text[9:12])
    long_minutes = Decimal(text[12:17])
    long_sign = -1 if text[17:18] == "W" else 1
    long = dm2decimal(long_degrees, long_minutes) * long_sign
    symbol_code = data[18:19]
    return dict(
        lat=lat,
        sym_table_id=sym_table_id,
        long=long,
        symbol_code=symbol_code,
    )


def decode_timestamp_dhm(data: bytes) -> datetime:
    ts_format = TimestampFormat(data[6:7])
    tzinfo = None if ts_format == TimestampFormat.DayHoursMinutesLocal else timezone.utc
    now = datetime.now(tz=tzinfo)
    ts = datetime.strptime(data[:6].decode("ascii"), "%d%H%M")
    maybe_ts = ts.replace(year=now.year, month=now.month, tzinfo=tzinfo)
    if maybe_ts > (now + FUTURE_TIMESTAMP_THRESHOLD):
        # can't have a timestamp in the future, so assume it's from last month
        if maybe_ts.month == 1:
            return maybe_ts.replace(year=maybe_ts.year - 1, month=12)
        return maybe_ts.replace(month=maybe_ts.month - 1)
    return maybe_ts


def decode_timestamp_hms(data: bytes) -> datetime:
    now = datetime.now(tz=timezone.utc)
    ts = datetime.strptime(data[:6].decode("ascii"), "%H%M%S")
    maybe_ts = ts.replace(
        year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc
    )
    if maybe_ts > (now + FUTURE_TIMESTAMP_THRESHOLD):
        # can't have a timestamp (too far) in the future, so assume it's from yesterday
        return maybe_ts - timedelta(days=1)
    return maybe_ts


def decode_timestamp_mdhm(data: bytes) -> datetime:
    now = datetime.now(tz=timezone.utc)
    ts = datetime.strptime(data[:8].decode("ascii"), "%m%d%H%M").replace(
        year=now.year,
        tzinfo=timezone.utc,
    )
    if ts > (now + FUTURE_TIMESTAMP_THRESHOLD):
        # can't have a timestamp in the future, so assume it's from last year
        return ts.replace(year=ts.year - 1)
    return ts


def decode_timestamp(data: bytes) -> datetime:
    try:
        ts_format = TimestampFormat(data[6:7])
        if ts_format in [
            TimestampFormat.DayHoursMinutesLocal,
            TimestampFormat.DayHoursMinutesZulu,
        ]:
            return decode_timestamp_dhm(data)
        return decode_timestamp_hms(data)
    except ValueError:
        # assume Month Day Hours Minutes
        return decode_timestamp_mdhm(data)
