"""common substructure parsers for APRS formats."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import math
from typing import Tuple

from .base91 import from_decimal, to_decimal
from .constants import TimestampFormat, timestamp_formats_map
from .decimaldegrees import dm2decimal
from .geo_util import ambiguate, dec2dm_lat, dec2dm_lng


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


def encode_position_uncompressed(
    lat,
    long,
    sym_table_id,
    symbol_code,
    ambiguity=None,
) -> bytes:
    return b"".join(
        [
            ambiguate(dec2dm_lat(lat), ambiguity),
            sym_table_id,
            ambiguate(dec2dm_lng(long), ambiguity),
            symbol_code,
        ]
    )


def decompress_lat(data: str) -> float:
    return 90 - to_decimal(data) / 380926


def compress_lat(data: float) -> bytes:
    return from_decimal(int(round(380926 * (90 - data))), width=4).encode("ascii")


def decompress_long(data: str) -> float:
    return -180 + to_decimal(data) / 190463


def compress_long(data: float) -> bytes:
    return from_decimal(int(round(190463 * (180 + data))), width=4).encode("ascii")


def decode_position_compressed(data: bytes):
    """
    :return: dict with keys lat, long, sym_table_id, symbol_code, data_ext
    """
    text = data.decode("latin1")
    if chr(data[0]) in POSITION_UNCOMPRESSED_SIGNATURE:
        raise ValueError("{!r} is not a compressed position".format(data[:13]))
    sym_table_id = data[0:1]
    lat = Decimal(str(decompress_lat(text[1:5])))
    long = Decimal(str(decompress_long(text[5:9])))
    symbol_code = data[9:10]
    c_ext = text[10:12]
    comp_type = data[12]
    init_kwargs = {}

    if c_ext[0] == " ":
        data_ext = b""
    else:
        if c_ext[0] == "{":
            from .classes import RNG

            data_ext = RNG(range=2 * 1.08 ** to_decimal(c_ext[1]))
        elif ord("!") <= ord(c_ext[0]) <= ord("z"):
            from .classes import CourseSpeed

            data_ext = CourseSpeed(
                course=to_decimal(c_ext[0]) * 4, speed=1.08 ** to_decimal(c_ext[1]) - 1
            )

        if comp_type % 0b11000 == 0b10000:
            # extract altitude
            init_kwargs["altitude_ft"] = 1.002 ** to_decimal(c_ext)

    return dict(
        sym_table_id=sym_table_id,
        lat=lat,
        long=long,
        symbol_code=symbol_code,
        data_ext=data_ext,
        **init_kwargs,
    )


def encode_position_compressed(
    lat,
    long,
    sym_table_id,
    symbol_code,
    ambiguity=None,
    data_ext=None,
    altitude_ft=None,
) -> bytes:
    data = [
        sym_table_id,
        compress_lat(lat),
        compress_long(long),
        symbol_code,
    ]
    if data_ext:
        from .classes import CourseSpeed, RNG

        if isinstance(data_ext, CourseSpeed):
            data.append(from_decimal(data_ext.course // 4, 1).encode("ascii"))
            data.append(
                from_decimal(int(round(math.log(data_ext.speed + 1, 1.08))), 1).encode(
                    "ascii"
                )
            )
            data.append(b"#")
        elif isinstance(data_ext, RNG):
            data.append(b"{")
            data.append(
                from_decimal(int(round(math.log(data_ext.range / 2, 1.08))), 1).encode(
                    "ascii"
                )
            )
            data.append(b"#")
    elif altitude_ft:
        data.append(
            from_decimal(int(round(math.log(altitude_ft, 1.002))), 1).encode("ascii")
        )
        data.append(b"#")
    else:
        data.append(b"  #")
    return b"".join(data)


def decode_timestamp_dhm(data: bytes) -> datetime:
    ts_format = TimestampFormat(data[6:7])
    tzinfo = None if ts_format == TimestampFormat.DayHoursMinutesLocal else timezone.utc
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
    now = datetime.now(tz=timezone.utc)
    ts = datetime.strptime(
        data[:6].decode("ascii"),
        timestamp_formats_map[TimestampFormat.HoursMinutesSecondsZulu],
    )
    maybe_ts = ts.replace(
        year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc
    )
    if maybe_ts > (now + FUTURE_TIMESTAMP_THRESHOLD):
        # can't have a timestamp (too far) in the future, so assume it's from yesterday
        return maybe_ts - timedelta(days=1)
    return maybe_ts


def decode_timestamp_mdhm(data: bytes) -> datetime:
    now = datetime.now(tz=timezone.utc)
    ts = datetime.strptime(
        data[:8].decode("ascii"),
        timestamp_formats_map[TimestampFormat.MonthDayHoursMinutesZulu],
    ).replace(
        year=now.year,
        tzinfo=timezone.utc,
    )
    if ts > (now + FUTURE_TIMESTAMP_THRESHOLD):
        # can't have a timestamp in the future, so assume it's from last year
        return ts.replace(year=ts.year - 1)
    return ts


def decode_timestamp(data: bytes) -> Tuple[TimestampFormat, datetime]:
    try:
        ts_format = TimestampFormat(data[6:7])
        if ts_format in [
            TimestampFormat.DayHoursMinutesLocal,
            TimestampFormat.DayHoursMinutesZulu,
        ]:
            return ts_format, decode_timestamp_dhm(data)
        return ts_format, decode_timestamp_hms(data)
    except ValueError:
        # assume Month Day Hours Minutes
        return TimestampFormat.MonthDayHoursMinutesZulu, decode_timestamp_mdhm(data)
