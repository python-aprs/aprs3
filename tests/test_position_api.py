"""Reading positions and symbols: position, HasPosition, lon, distances, Symbol (#51, #52)."""

import math

import attrs
import pytest

from aprs import (
    APRSFrame,
    HasPosition,
    ItemReport,
    Position,
    PositionReport,
    Symbol,
)

# --- public position, HasPosition, lon (#51) ---------------------------------


def test_public_position_and_timestamp():
    frame = APRSFrame.from_str("A>B:@092345z4610.00N/12255.00W>hi")
    report = frame.info
    assert isinstance(report, PositionReport) and report.position is not None
    assert report.position is report._position
    assert frame.position is report.position
    assert report.timestamp_info is report._timestamp
    assert report.lon == report.long == report.position.lon


def test_has_position():
    assert isinstance(APRSFrame.from_str("A>B:!4610.00N/12255.00W>").info, HasPosition)
    assert isinstance(ItemReport(name="I", position=Position()), HasPosition)
    status = APRSFrame.from_str("A>B:>hi")
    assert not isinstance(status.info, HasPosition)
    assert status.position is None


def test_lon_and_symbol_init_aliases():
    pos = Position(lat=1, lon=2, symbol=Symbol.CAR)
    assert pos == Position(lat=1, long=2, symbol_code=b">")
    assert pos.symbol == Symbol.CAR
    assert Position(symbol="\\k").sym_table_id == b"\\"
    # the aliases don't stick: evolve keeps the changed long
    assert attrs.evolve(pos, long=3).long == 3
    with pytest.raises(ValueError, match="long"):
        Position(lon=200)


def test_distance_and_bearing():
    seattle = Position(lat=47.6062, lon=-122.3321)
    portland = APRSFrame.from_str("A>B:!4531.00N/12240.00W>").info
    assert isinstance(portland, HasPosition)
    assert math.isclose(seattle.distance_to(portland), 234, abs_tol=2)
    assert math.isclose(seattle.bearing_to(portland), 187, abs_tol=2)
    assert seattle.distance_to(seattle) == 0
    assert math.isclose(Position().bearing_to((1, 0)), 0, abs_tol=1e-9)
    assert math.isclose(Position().bearing_to((0, -1)), 270)
    with pytest.raises(ValueError, match="no position"):
        seattle.distance_to(ItemReport(name="I"))


# --- Symbol (#52) ------------------------------------------------------------


def test_symbol():
    car = Symbol.from_str("/>")
    assert car == Symbol.CAR == Symbol(table="/", code=">")
    assert (str(car), bytes(car)) == ("/>", b"/>")
    assert Symbol.from_str(car) is car
    assert Symbol.from_str(b"\\k").table == b"\\"
    for bad in ("/", "/>>"):
        with pytest.raises(ValueError, match="two characters"):
            Symbol.from_str(bad)
    with pytest.raises(ValueError, match="one character"):
        Symbol(table="//")


def test_report_symbol():
    report = APRSFrame.from_str("A>B:!4610.00N\\12255.00Wk").info
    assert isinstance(report, PositionReport)
    assert report.symbol == Symbol("\\", "k")
    assert ItemReport(name="I").symbol is None


def test_symbol_fields_accept_str():
    pos = Position(sym_table_id="\\", symbol_code="k")
    assert (pos.sym_table_id, pos.symbol_code) == (b"\\", b"k")
