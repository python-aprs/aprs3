"""Report and Position fields are keyword-only; match patterns use the meaningful fields (#53)."""

import pytest

from aprs import (
    APRSFrame,
    InformationField,
    ItemReport,
    Message,
    ObjectReport,
    Position,
    PositionReport,
    StatusReport,
)


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
