"""Encoding objects built in code, rather than decoded from a packet."""

from decimal import Decimal

import pytest

from aprs import APRSFrame, CourseSpeed, Message, PositionReport
from aprs.classes import DataType
from aprs.constants import PositionFormat
from aprs.geo_util import dec2dm_lat, dec2dm_lng
from aprs.position import Position


@pytest.mark.parametrize(
    "lat, expected",
    [
        (49.0583333, b"4903.50N"),
        (-0.5, b"0030.00S"),
        (Decimal("-0"), b"0000.00S"),
        (0.0, b"0000.00N"),
        (89.9999999, b"9000.00N"),
    ],
)
def test_dec2dm_lat(lat, expected):
    assert dec2dm_lat(lat) == expected


@pytest.mark.parametrize(
    "long, expected",
    [
        (-72.0291667, b"07201.75W"),
        (-0.25, b"00015.00W"),
        (-0.0, b"00000.00W"),
        (180, b"18000.00E"),
        (-72.99999999, b"07300.00W"),
    ],
)
def test_dec2dm_lng(long, expected):
    assert dec2dm_lng(long) == expected


def position_report(**position_kwargs) -> bytes:
    return bytes(
        PositionReport(
            raw=b"",
            data_type=DataType.POSITION_W_O_TIMESTAMP,
            data=b"",
            position=Position(lat=49.5, long=-72.75, symbol_code=b">", **position_kwargs),
        )
    )


def test_uncompressed_with_ambiguity():
    assert position_report(ambiguity=2) == b"!4930.  N/07245.  W>"


def test_uncompressed_altitude_comment():
    assert position_report(altitude_ft=1234) == b"!4930.00N/07245.00W>/A=001234"
    assert position_report(altitude_ft=-12) == b"!4930.00N/07245.00W>/A=-00012"


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({}, b"!/5L!!<*e8>  #"),
        ({"data_ext": CourseSpeed(course=88, speed=36.2)}, b"!/5L!!<*e8>7P#"),
        ({"altitude_ft": 10004}, b"!/5L!!<*e8>S]S"),
        ({"altitude_ft": 10004, "compression_type": ord("3") - 33}, b"!/5L!!<*e8>S]3"),
    ],
)
def test_compressed_defaults(kwargs, expected):
    # -72.75 is "<*e8"; APRS101's "<*e7" example is -72.750004
    encoded = position_report(position_format=PositionFormat.Compressed, **kwargs)
    assert encoded == expected
    # and it decodes back to the same values
    decoded = APRSFrame.from_str("N0CALL>APRS:" + encoded.decode()).info
    if "altitude_ft" in kwargs:
        assert decoded.altitude_ft == pytest.approx(kwargs["altitude_ft"], rel=0.002)


@pytest.mark.parametrize(
    "number, expected",
    [
        (None, b":WU2Z     :hi"),
        (b"", b":WU2Z     :hi{"),
        (b"42", b":WU2Z     :hi{42"),
    ],
)
def test_message_number(number, expected):
    message = Message(
        raw=b"",
        data_type=DataType.MESSAGE,
        data=b"",
        addressee=b"WU2Z",
        text=b"hi",
        number=number,
    )
    assert bytes(message) == expected


@pytest.mark.parametrize(
    "text",
    [
        # issue #7: telemetry headers ride in messages and exceed 67 chars
        b"PARM.Vbat,Temp,Press,Alt,Light,Door,Heat,Fan,Lamp,Pump,Valve,Alarm,Spare",
        b"x" * 100,
    ],
)
def test_message_text_not_truncated(text):
    info = b":N0CALL-1 :" + text
    frame = APRSFrame.ui(
        destination="APZ001",
        source="N0CALL-1",
        path=["WIDE1-1"],
        info=info,
    )
    assert frame.info.text == text
    assert bytes(frame.info) == info
    assert bytes(frame).endswith(info)
    assert bytes(APRSFrame.from_bytes(bytes(frame)).info) == info
