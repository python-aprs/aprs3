"""APRS value types are frozen stdlib dataclasses."""

import dataclasses
import datetime

import pytest

from aprs import APRSFrame, Position, PositionReport, StatusReport, Timestamp
from aprs.classes import DataType, InformationField, Message
from aprs.constants import TimestampFormat
from aprs.kiss import APRSDecode

TS = Timestamp(
    TimestampFormat.DayHoursMinutesZulu,
    datetime.datetime(2022, 5, 20, 23, 50, tzinfo=datetime.UTC),
)


def test_report_constructor_keywords():
    pos = Position(lat=46.1, long=-122.9, symbol_code=b">")
    report = PositionReport(
        raw=b"",
        data_type=DataType.POSITION_W_TIMESTAMP_MSG,
        data=b"",
        timestamp=TS,
        position=pos,
        comment=b"hi",
    )
    assert report.timestamp is TS
    assert report.position is pos
    assert (report.lat, report.long, report.symbol_code) == (46.1, -122.9, b">")
    assert bytes(report).startswith(b"@202350z4606.00N/12254.00W>")


def test_mixin_properties_without_position():
    status = StatusReport(raw=b"", data_type=DataType.STATUS, data=b"", status=b"ok")
    assert status.timestamp is None
    assert bytes(status) == b">ok"


def test_frozen_and_hashable():
    msg = InformationField.from_bytes(b":N0CALL   :hello{1")
    assert isinstance(msg, Message)
    with pytest.raises(dataclasses.FrozenInstanceError):
        msg.text = b"x"  # type: ignore[misc]
    assert hash(msg) == hash(InformationField.from_bytes(b":N0CALL   :hello{1"))


def test_aprsframe_decodes_info_on_init_and_replace():
    frame = APRSFrame.from_str("N0CALL>APZ069::N0CALL-2 :ping{1")
    assert isinstance(frame.info, Message)
    replaced = dataclasses.replace(frame, info=b">status")
    assert isinstance(replaced.info, StatusReport)
    assert dataclasses.asdict(frame)["info"]["text"] == b"ping"


def test_aprs_kiss_decoder_always_strips_command_byte():
    assert APRSDecode(strip_df_start=False).strip_df_start is True
