"""Building reports in code: str input, default data types, str properties (#47, #49, #50)."""

import pytest

import aprs
from aprs import (
    APRSFrame,
    DataType,
    InformationField,
    ItemReport,
    Message,
    ObjectReport,
    Position,
    PositionReport,
    StatusReport,
    Timestamp,
)

# --- str info (#47) ----------------------------------------------------------


def test_ui_accepts_str_info():
    frame = APRSFrame.ui("APRS", "N0CALL", info=">café")
    assert isinstance(frame.info, StatusReport)
    assert frame.info.status_str == "café"


def test_from_any_accepts_bytearray_and_str():
    assert bytes(InformationField.from_any(bytearray(b">hi"))) == b">hi"
    status = InformationField.from_any(">hi")
    assert isinstance(status, StatusReport) and status.status == b"hi"


# --- reports without raw, data and data_type (#49) ---------------------------


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


# --- str in, str out (#50) ---------------------------------------------------


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
