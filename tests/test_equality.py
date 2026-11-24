"""Equality ignores the bytes heard; lat/long are floats with exact Decimals kept (#54)."""

from decimal import Decimal

import attrs
import pytest

from aprs import (
    APRSFrame,
    Message,
    Position,
    PositionFormat,
    PositionReport,
    Timestamp,
)

from .test_corpus import CORPUS_PARAMS, fixed_now  # noqa: F401  (autouse fixture)


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
