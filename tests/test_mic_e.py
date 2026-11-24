"""Mic-E position reports (#27)."""

import attrs
import pytest

from aprs import APRSFrame, CourseSpeed, DataType, InformationField, MicEReport
from aprs.mic_e import decode_destination, encode_destination


def frame(tnc2: str) -> APRSFrame:
    return APRSFrame.from_str(tnc2)


def mic_e(tnc2: str) -> MicEReport:
    report = frame(tnc2).info
    assert isinstance(report, MicEReport)
    return report


def test_yaesu_report():
    report = mic_e('N0CALL-7>T2SP0W,N0DIGI*,WIDE2-1,qAR,N0GATE:`c51l!?>/`"4V}_%')
    assert isinstance(report, MicEReport)
    assert float(report.lat or 0) == pytest.approx(42 + 30.07 / 60)
    assert float(report.long or 0) == pytest.approx(-(71 + 25.21 / 60))
    assert report.data_ext == CourseSpeed(course=135, speed=0)
    assert (report.sym_table_id, report.symbol_code) == (b"/", b">")
    assert (report.message, report.message_text) == ("M2", "In Service")
    assert report.altitude_m == 63
    assert report.altitude_ft == pytest.approx(206.7, abs=0.1)
    assert (report.type_code, report.device_suffix, report.device) == (
        b"`",
        b"_%",
        "Yaesu FTM-400DR",
    )
    assert report.comment == b""
    assert report.destination == "T2SP0W"


def test_kenwood_reports():
    d700 = mic_e("N0CALL-7>T2SP0W:'c7sl!?>/]\"4H}")
    assert (d700.data_type, d700.device, d700.altitude_m) == (
        DataType.OLD_MIC_E_DATA_2,
        "Kenwood TM-D700",
        49,
    )
    d72 = mic_e('N0CALL-9>S32U6T,WIDE1-1:`(_fn"Oj/>=')
    assert d72.device == "Kenwood TH-D72"
    assert (d72.message, d72.data_ext) == ("M3", CourseSpeed(course=251, speed=20))
    assert float(d72.lat or 0) == pytest.approx(33 + 25.64 / 60)


def test_comment_and_unknown_suffix():
    report = mic_e('N0CALL-9>S32U6T:`(_fn"Oj/`Hello world_9')
    assert report.type_code == b"`"
    assert report.device_suffix == b"" and report.device is None
    assert report.comment == b"Hello world_9"


def test_destination_ssid_is_ignored():
    with_ssid = mic_e('N0CALL-9>S32U6T-2:`(_fn"Oj/>=')
    assert with_ssid.lat == mic_e('N0CALL-9>S32U6T:`(_fn"Oj/>=').lat


@pytest.mark.parametrize(
    "tnc2",
    [
        'N0CALL-9>APRS:`(_fn"Oj/>=',  # 4-character destination
        'N0CALL-9>S32U6M:`(_fn"Oj/>=',  # M isn't a Mic-E character
        'N0CALL-9>S32UAT:`(_fn"Oj/>=',  # custom bits only in the first 3
        "N0CALL-9>S32U6T:`(_f",  # too short
        'N0CALL-9>S32U6T:`\x1b\x1b\x1bn"Oj/',  # longitude bytes out of range
        "N0CALL-9>S32U6T:`(_fn%Oj/>=",  # course 551
        'N0CALL-9>Y2SP0W:`(_fn"Oj/>=',  # latitude 92 degrees
    ],
)
def test_undecodable_mic_e_stays_raw(tnc2):
    f = frame(tnc2)
    assert type(f.info) is InformationField
    assert str(f) == tnc2


def test_info_alone_cannot_decode_mic_e():
    field = InformationField.from_bytes(b'`(_fn"Oj/>=')
    assert type(field) is InformationField
    with pytest.raises(ValueError):
        MicEReport.from_bytes(b'`(_fn"Oj/>=')


@pytest.mark.parametrize(
    "destination, message",
    [
        ("PPPP0W", "M0"),
        ("PP0P0W", "M1"),
        ("P0PP0W", "M2"),
        ("P00P0W", "M3"),
        ("0PPP0W", "M4"),
        ("0P0P0W", "M5"),
        ("00PP0W", "M6"),
        ("AAAP0W", "C0"),
        ("00AP0W", "C6"),
        ("000P0W", "Emergency"),
        ("AP0P0W", "Unknown"),
    ],
)
def test_message_codes(destination, message):
    assert decode_destination(destination.encode())["message"] == message
    if message != "Unknown":
        assert encode_destination(0, -100, message)[:3] == destination.encode()[:3]


def test_ambiguity():
    decoded = decode_destination(b"T2SPLZ")
    assert decoded["ambiguity"] == 2
    report = mic_e("N0CALL>T2SPLZ:`c51l!?>/")
    assert report._position is not None and report._position.ambiguity == 2
    # the box centre: 42 30.5'N, and the longitude is blurred the same way
    assert float(report.lat or 0) == pytest.approx(42 + 30.5 / 60)
    assert float(report.long or 0) == pytest.approx(-(71 + 25.5 / 60))


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(lat=-33.8688, long=151.2093),
        dict(lat=51.4779, long=-0.0015),
        dict(lat=49.0583, long=-105.5, message="Emergency", speed=120, course=360),
        dict(lat=0.5, long=179.99, message="C2", speed=799, course=1, altitude_m=-50),
        dict(lat=45, long=-9.99, speed=5, course=5, altitude_m=12000),
        dict(lat=89.99, long=100.01, speed=0, course=0),
        dict(lat=10.25, long=-109.75, symbol_code=b"k", sym_table_id=b"\\"),
    ],
)
def test_build_and_decode(kwargs):
    report = MicEReport.new(**kwargs, comment=b"test")
    f = APRSFrame.ui(report.destination, "N0CALL", ["WIDE1-1"], bytes(report))
    decoded = f.info
    assert isinstance(decoded, MicEReport)
    assert float(decoded.lat or 0) == pytest.approx(kwargs["lat"], abs=1 / 6000)
    assert float(decoded.long or 0) == pytest.approx(kwargs["long"], abs=1 / 6000)
    assert decoded.data_ext == CourseSpeed(
        course=kwargs.get("course", 0), speed=kwargs.get("speed", 0)
    )
    assert decoded.message == kwargs.get("message", "M0")
    assert decoded.altitude_m == kwargs.get("altitude_m")
    assert decoded.symbol_code == kwargs.get("symbol_code", b">")
    assert decoded.comment == b"test"
    # an unchanged copy encodes to the same bytes and destination
    assert bytes(attrs.evolve(decoded)) == bytes(report)
    assert decoded.destination == report.destination
    assert str(APRSFrame.from_bytes(bytes(f))) == str(f)


@pytest.mark.parametrize(
    "kwargs", [dict(speed=800), dict(message="Unknown"), dict(message="M7")]
)
def test_build_rejects(kwargs):
    report = MicEReport.new(lat=1, long=1, **kwargs)
    with pytest.raises(ValueError):
        _ = report.destination, bytes(report)


def test_report_without_position():
    report = MicEReport(raw=b"", data_type=DataType.CURRENT_MIC_E_DATA_2, data=b"")
    with pytest.raises(ValueError):
        bytes(report)
    with pytest.raises(ValueError):
        _ = report.destination


def test_is_emergency():
    assert mic_e('N0CALL>000P0W:`(_fn"Oj/').is_emergency
    assert not mic_e('N0CALL>PPPP0W:`(_fn"Oj/').is_emergency
