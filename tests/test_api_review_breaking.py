"""Breaking changes from the API review (#53, #54)."""

from decimal import Decimal

import attrs
import pytest

from aprs import (
    APRSFrame,
    InformationField,
    ItemReport,
    Message,
    ObjectReport,
    Position,
    PositionFormat,
    PositionReport,
    StatusReport,
    Timestamp,
)

from .test_corpus import CORPUS_PARAMS, fixed_now  # noqa: F401  (autouse fixture)

# --- #53: keyword-only fields and __match_args__ ---------------------------


def test_position_fields_are_keyword_only():
    with pytest.raises(TypeError):
        Position(46.1, -122.9)  # ty: ignore[too-many-positional-arguments]
    assert Position(lat=46.1, lon=-122.9).long == -122.9


@pytest.mark.parametrize(
    "cls",
    [InformationField, PositionReport, Message, StatusReport, ObjectReport, ItemReport],
)
def test_report_fields_are_keyword_only(cls):
    with pytest.raises(TypeError):
        cls(b"")


def describe(info) -> str:
    match info:
        case Message(addressee, text):
            return f"message to {addressee.decode()}: {text.decode()}"
        case StatusReport(status):
            return f"status {status.decode()}"
        case ObjectReport(name, lat, long) | ItemReport(name, lat, long):
            return f"{name.decode()} at {lat:.2f},{long:.2f}"
        case PositionReport(lat, long):
            return f"position {lat:.2f},{long:.2f}"
    return "other"


@pytest.mark.parametrize(
    "packet, expected",
    [
        ("A>B::N0CALL   :hi{1", "message to N0CALL: hi"),
        ("A>B:>on the air", "status on the air"),
        ("A>B:;OBJ      *092345z4610.00N/12255.00W>", "OBJ at 46.17,-122.92"),
        ("A>B:)ITEM!4610.00N/12255.00W>", "ITEM at 46.17,-122.92"),
        ("A>B:!4610.00N/12255.00W>", "position 46.17,-122.92"),
        ("A>B:hello", "other"),
    ],
)
def test_match_patterns(packet, expected):
    assert describe(APRSFrame.from_str(packet).info) == expected


def test_position_match():
    match Position(lat=1.5, lon=2.5):
        case Position(lat, long):
            assert (lat, long) == (1.5, 2.5)


# --- #54: equality ignores raw bytes; lat/long are floats ------------------


def test_built_report_equals_decoded():
    decoded = APRSFrame.from_str("A>B:=4610.00N/12255.00W-Home").info
    built = PositionReport(
        position=Position(lat=46 + 10 / 60, lon=-(122 + 55 / 60)), comment="Home"
    )
    assert bytes(built) == bytes(decoded)
    assert built == decoded
    assert "raw=" not in repr(decoded) and "data=" not in repr(decoded)


def test_message_built_equals_decoded():
    decoded = APRSFrame.from_str("A>B::N0CALL   :hello{12").info
    assert decoded == Message.new("N0CALL", "hello", number="12")
    assert hash(decoded) == hash(Message.new("N0CALL", "hello", number="12"))


def test_lat_long_are_floats_with_exact_decimals():
    report = APRSFrame.from_str("A>B:!4903.50N/07201.75W-").info
    assert isinstance(report, PositionReport) and report.position is not None
    assert type(report.lat) is float and type(report.long) is float
    assert report.position.lat_decimal == Decimal("49") + Decimal("3.50") / 60
    assert report.position.long_decimal == -(Decimal("72") + Decimal("1.75") / 60)
    assert float(report.position.lat_decimal) == report.lat


def test_decimals_for_built_positions():
    pos = Position(lat=Decimal("46.5"), long=1)
    assert pos.lat == 46.5 and type(pos.long) is float
    assert pos.lat_decimal == Decimal("46.5")
    assert Position(lat=46.1).lat_decimal == Decimal("46.1")
    # a copy with another latitude doesn't keep the old exact value
    assert attrs.evolve(pos, lat=10.25).lat_decimal == Decimal("10.25")


@pytest.mark.parametrize("expected_class, tnc2", CORPUS_PARAMS)
def test_float_positions_reencode_unchanged(expected_class, tnc2):
    """An evolved copy loses the exact Decimals: its floats must encode the same."""
    info = APRSFrame.from_str(tnc2).info
    position = getattr(info, "position", None)
    if position is None or position.position_format is not PositionFormat.Uncompressed:
        return
    copy = attrs.evolve(position)
    assert copy._lat_decimal is None
    assert bytes(copy) == bytes(position)


def test_timestamped_report_defaults_to_at():
    report = PositionReport(position=Position(), timestamp=Timestamp())
    assert bytes(report).startswith(b"@")
