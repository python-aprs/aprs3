"""Encoding objects built in code, rather than decoded from a packet."""

from decimal import Decimal

import attr
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
    # issue #26: 0 ft is a valid altitude, not an absent one
    assert position_report(altitude_ft=0) == b"!4930.00N/07245.00W>/A=000000"


def test_altitude_zero_from_evolved_frame():
    # issue #26 reproduction: a constructed report must keep /A=000000
    frame = APRSFrame.from_str("N0CALL>APRS:=4903.50N/07201.75W-")
    assert isinstance(frame.info, PositionReport)
    report = attr.evolve(
        frame.info,
        position=attr.evolve(frame.info._position, altitude_ft=0),
    )
    assert bytes(report) == b"=4903.50N/07201.75W-/A=000000"


def test_compressed_altitude_zero_is_encoded():
    # issue #26: the compressed cs bytes must carry an altitude code for 0 ft,
    # not the "no altitude" spaces. 1.002**c cannot represent 0 exactly, so the
    # lowest valid code (c_ext = 0, decoded as 1 ft) is used.
    encoded = position_report(altitude_ft=0, position_format=PositionFormat.Compressed)
    assert encoded == b"!/5L!!<*e8>!!S"
    decoded = APRSFrame.from_str("N0CALL>APRS:" + encoded.decode()).info
    assert isinstance(decoded, PositionReport)
    assert decoded.altitude_ft == pytest.approx(1.0)


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
    assert isinstance(decoded, PositionReport)
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
    assert isinstance(frame.info, Message)
    assert frame.info.text == text
    assert bytes(frame.info) == info
    assert bytes(frame).endswith(info)
    assert bytes(APRSFrame.from_bytes(bytes(frame)).info) == info


def test_compressed_course_360_is_north():
    """Issue #23: 360 encodes as code 0; code 90 ("{") would mean a range."""
    north = position_report(
        data_ext=CourseSpeed(course=360, speed=10),
        position_format=PositionFormat.Compressed,
    )
    zero = position_report(
        data_ext=CourseSpeed(course=0, speed=10),
        position_format=PositionFormat.Compressed,
    )
    assert north == zero
    assert north[11:12] == b"!"


def test_uncompressed_long_ambiguity():
    """Issue #25."""
    assert position_report(ambiguity=1, long_ambiguity=0) == b"!4930.0 N/07245.00W>"
    assert position_report(ambiguity=0, long_ambiguity=2) == b"!4930.00N/07245.  W>"


def test_report_without_position_does_not_encode():
    report = PositionReport(raw=b"", data_type=DataType.POSITION_W_O_TIMESTAMP, data=b"")
    with pytest.raises(ValueError, match="position"):
        bytes(report)


def test_report_without_data_type_does_not_encode():
    report = PositionReport(raw=b"", data_type=None, data=b"", position=Position())
    with pytest.raises(ValueError, match="data type"):
        bytes(report)


# --- issue #44: decoded reports encode back to the bytes heard ---


@pytest.mark.parametrize(
    "raw",
    [
        # messages: addressee not left-aligned, empty or reply-ack numbers
        b": U2Z     :race {*in text",
        b":  N0CALL :hello{12",
        b":N0CALL   :hi{",
        b":N0CALL   :hi {AB}",
        # PHG with a non-digit, decoded leniently
        b"!4903.50N/07201.75W#PHG72N0/Dire Wolf digi",
        # object with an unusual live/killed byte
        b";LEADER   E092345z4903.50N/07201.75W>088/036",
        # item name with surrounding spaces
        b") ID #2_4903.50N/07201.75WA comment",
        # status with a timestamp that isn't DHM zulu
        b">092345/4903.50N/07201.75W>088/036",
    ],
)
def test_decoded_report_reencodes_exactly(raw):
    line = "N0CALL>APRS:" + raw.decode("latin1")
    frame = APRSFrame.from_str(line)
    assert bytes(frame.info) == raw
    assert str(frame) == line


def test_changed_report_encodes_from_its_fields():
    heard = APRSFrame.from_str("N0CALL>APRS:: U2Z     :hello{1").info
    assert isinstance(heard, Message)
    changed = attr.evolve(heard, text=b"bye")
    assert bytes(changed) == b":U2Z      :bye{1"


def test_built_report_ignores_unrelated_raw():
    message = Message(
        raw=b"not a message",
        data_type=DataType.MESSAGE,
        data=b"",
        addressee=b"N0CALL",
        text=b"hi",
    )
    assert bytes(message) == b":N0CALL   :hi"
