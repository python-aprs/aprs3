"""Usability fixes from the API review (#46-#52)."""

import math

import attrs
import pytest

import aprs
from aprs import (
    APRSFrame,
    DataType,
    HasPosition,
    InformationField,
    ItemReport,
    Message,
    ObjectReport,
    Position,
    PositionFormat,
    PositionReport,
    StatusReport,
    Symbol,
    Timestamp,
)

from .test_aprsis_session import logresp_script
from .test_io import threaded_server

# --- #46: a changed altitude is encoded ---------------------------------


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


# --- #47: str info --------------------------------------------------------


def test_ui_accepts_str_info():
    frame = APRSFrame.ui("APRS", "N0CALL", info=">café")
    assert isinstance(frame.info, StatusReport)
    assert frame.info.status_str == "café"


def test_from_any_accepts_bytearray_and_str():
    assert bytes(InformationField.from_any(bytearray(b">hi"))) == b">hi"
    status = InformationField.from_any(">hi")
    assert isinstance(status, StatusReport) and status.status == b"hi"


# --- #48: edits to an undecoded info field --------------------------------


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


# --- #49: build reports without raw, data and data_type -------------------


@pytest.mark.parametrize(
    "report, data_type",
    [
        (PositionReport(position=Position()), DataType.POSITION_W_O_TIMESTAMP_MSG),
        (
            PositionReport(position=Position(), timestamp=Timestamp()),
            DataType.POSITION_W_TIMESTAMP_MSG,
        ),
        (Message(addressee="N0CALL", text="hi"), DataType.MESSAGE),
        (StatusReport(status="on the air"), DataType.STATUS),
        (
            ObjectReport(name="OBJ", timestamp=Timestamp(), position=Position()),
            DataType.OBJECT,
        ),
        (ItemReport(name="ITEM", position=Position()), DataType.ITEM),
        (aprs.MicEReport(position=Position()), DataType.CURRENT_MIC_E_DATA_2),
        (InformationField(comment=b"free text"), None),
    ],
)
def test_report_defaults(report, data_type):
    assert report.data_type is data_type
    assert report.raw == report.data == b""


def test_built_report_matches_the_long_form():
    short = PositionReport(position=Position(lat=46.1, lon=-122.9), comment="Home")
    long = PositionReport(
        raw=b"",
        data=b"",
        data_type=DataType.POSITION_W_O_TIMESTAMP_MSG,
        position=Position(lat=46.1, long=-122.9),
        comment=b"Home",
    )
    assert short == long
    assert bytes(short) == b"=4606.00N/12254.00W-Home"


def test_explicit_data_type_is_kept():
    report = PositionReport(
        data_type=DataType.POSITION_W_O_TIMESTAMP, position=Position()
    )
    assert bytes(report).startswith(b"!")


# --- #50: str in, str out ---------------------------------------------------


def test_str_fields_are_stored_as_bytes():
    msg = Message(addressee="N0CALL", text="hi ☕", number="12")
    assert (msg.addressee, msg.text, msg.number) == (b"N0CALL", "hi ☕".encode(), b"12")
    assert (msg.addressee_str, msg.text_str) == ("N0CALL", "hi ☕")
    obj = ObjectReport(
        name="OBJ", timestamp=Timestamp(), position=Position(), comment="c"
    )
    assert (obj.name, obj.name_str, obj.comment, obj.comment_str) == (
        b"OBJ",
        "OBJ",
        b"c",
        "c",
    )
    item = ItemReport(name="ITEM", position=Position())
    assert item.name_str == "ITEM"
    assert ItemReport(position=Position()).name_str == ""


def test_str_properties_fall_back_to_latin1():
    status = APRSFrame.from_bytes(
        bytes(APRSFrame.ui("APRS", "N0CALL", info=b">caf\xe9"))
    ).info
    assert isinstance(status, StatusReport) and status.status_str == "café"


def test_symbol_fields_accept_str():
    pos = Position(sym_table_id="\\", symbol_code="k")
    assert (pos.sym_table_id, pos.symbol_code) == (b"\\", b"k")


# --- #51: public position, HasPosition, lon -------------------------------


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


# --- #52: Symbol, TCP signature, decoder names ----------------------------


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


def test_decoder_names():
    assert aprs.aprsis.APRSDecode is aprs.APRSTNC2Decode
    assert aprs.kiss.APRSDecode is aprs.APRSKISSDecode


def test_tcp_positional_args_and_filter():
    with threaded_server(logresp_script("verified")) as server:
        with aprs.TCP("127.0.0.1", server.port, "N0CALL", filter="r/46/-122/50"):
            pass
        server.wait_done()
    login = server.received.split(b"\r\n")[0]
    assert login.startswith(b"user N0CALL pass -1 vers aprs3 ")
    assert login.endswith(b" filter r/46/-122/50")


def test_login_command_and_filter():
    from aprs.aprsis import _login_command

    assert _login_command("", None) == ""
    assert _login_command("cmd", None) == "cmd"
    assert _login_command("", "b/N0CALL") == "filter b/N0CALL"
    assert _login_command("cmd", "b/N0CALL") == "cmd filter b/N0CALL"
