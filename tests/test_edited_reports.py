"""Decoded reports changed with attrs.evolve encode the change (#46, #48)."""

import attrs
import pytest

from aprs import (
    APRSFrame,
    InformationField,
    Position,
    PositionFormat,
    PositionReport,
)

# --- a changed altitude is encoded (#46) -------------------------------------


def _with_altitude(report, altitude_ft):
    return attrs.evolve(
        report, position=attrs.evolve(report.position, altitude_ft=altitude_ft)
    )


@pytest.mark.parametrize(
    "packet",
    [
        "A>B:!4610.00N/12255.00W>/A=000500 hi",
        "A>B:!4610.00N/12255.00W>090/025/A=000500 hi",
        "A>B:!4610.00N/12255.00W>hi /A=000500 there",
        "A>B:;OBJ      *092345z4610.00N/12255.00W>/A=000500",
        "A>B:)ITEM!4610.00N/12255.00W>/A=-00012",
    ],
)
def test_decoded_altitude_reencodes_unchanged(packet):
    frame = APRSFrame.from_str(packet)
    assert str(APRSFrame.from_bytes(bytes(frame))) == packet
    assert bytes(frame.info) == packet.split(":", 1)[1].encode()


def test_changed_altitude_replaces_the_old_one():
    report = APRSFrame.from_str("A>B:!4610.00N/12255.00W>hi /A=000500 there").info
    assert (
        bytes(_with_altitude(report, 9999)) == b"!4610.00N/12255.00W>hi /A=009999 there"
    )


def test_removed_altitude_is_dropped_from_the_comment():
    report = APRSFrame.from_str("A>B:!4610.00N/12255.00W>/A=000500 hi").info
    assert bytes(_with_altitude(report, None)) == b"!4610.00N/12255.00W> hi"


def test_compressed_altitude_leaves_the_comment_alone():
    pos = Position(position_format=PositionFormat.Compressed, altitude_ft=1000)
    report = PositionReport(position=pos, comment=b"/A=000001 text")
    assert bytes(report).endswith(b"/A=000001 text")


def test_new_altitude_goes_before_the_comment():
    report = PositionReport(position=Position(altitude_ft=12), comment="hi")
    assert bytes(report).endswith(b"-/A=000012hi")


# --- edits to an undecoded info field (#48) ----------------------------------


@pytest.mark.parametrize("packet", ["A>B:hello", "A>B:,invalid data", "A>B:"])
def test_raw_info_reencodes_unchanged(packet):
    info = APRSFrame.from_str(packet).info
    assert type(info) is InformationField
    assert bytes(info) == info.raw


def test_raw_info_edit_is_encoded():
    info = APRSFrame.from_str("A>B:hello").info
    assert bytes(attrs.evolve(info, comment=b"bye")) == b"bye"
    info = APRSFrame.from_str("A>B:,invalid").info
    assert bytes(attrs.evolve(info, comment=b"other")) == b",other"
