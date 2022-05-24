"""
Decode regression consists of real frames scraped from APRS-IS that
stumped us at one point.

Adding regression tests is an excellent tool for implementing decoders for
new information data types.
"""
import datetime
from decimal import Decimal
from unittest import mock

import pytest

from kiss3.ax25 import Frame

from aprs3 import parser
from aprs3.classes import (
    CourseSpeed,
    DataType,
    DFS,
    InformationField,
    ItemReport,
    Message,
    ObjectReport,
    PHG,
    PositionReport,
    RNG,
    StatusReport,
)
from aprs3.constants import PositionFormat, TimestampFormat


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch):
    """Return a static datetime.datetime.now so the test returns consistent results."""

    def new_now(*args, **kwargs):
        return datetime.datetime(2022, 5, 23, 23, 59, tzinfo=datetime.timezone.utc)

    with mock.patch("aprs3.parser.datetime") as mock_datetime:
        mock_datetime.now.side_effect = new_now
        mock_datetime.strptime.side_effect = (
            lambda *args, **kw: datetime.datetime.strptime(*args, **kw)
        )
        yield


@pytest.mark.parametrize(
    "packet_text, exp_decoded_iframe",
    (
        pytest.param(
            "KB8BMY-10>APDR16,TCPIP*,QAC,T2FINLAND:=4704.13N/12242.73W[241/055/A=-00053 Mike ",
            PositionReport(
                raw=b"=4704.13N/12242.73W[241/055/A=-00053 Mike ",
                data_type=DataType.POSITION_W_O_TIMESTAMP_MSG,
                data=b"4704.13N/12242.73W[",
                data_ext=CourseSpeed(course=241, speed=55),
                comment=b"/A=-00053 Mike ",
                timestamp=None,
                lat=Decimal("47.06883333333333333333333333"),
                sym_table_id=b"/",
                long=Decimal("-122.7121666666666666666666667"),
                symbol_code=b"[",
                altitude_ft=-53,
            ),
            id="position, uncompressed, without timestamp, course/speed, altitude, comment",
        ),
        pytest.param(
            "NICOLI>APRS,QAO,K0INK-5:!4605.21N/12327.31W#PHG2830W2, ORn-N, Fill-in / NA7Q 14.3V 44.2F",
            PositionReport(
                raw=b"!4605.21N/12327.31W#PHG2830W2, ORn-N, Fill-in / NA7Q 14.3V 44.2F",
                data_type=DataType.POSITION_W_O_TIMESTAMP,
                data=b"4605.21N/12327.31W#",
                data_ext=PHG(power_w=4, height_ft=2560, gain_db=3, directivity=0),
                comment=b"W2, ORn-N, Fill-in / NA7Q 14.3V 44.2F",
                timestamp=None,
                lat=Decimal("46.08683333333333333333333333"),
                sym_table_id=b"/",
                long=Decimal("-123.4551666666666666666666667"),
                symbol_code=b"#",
            ),
            id="position, uncompressed, without timestamp, phg, comment",
        ),
        pytest.param(
            "MEISNR>APN382,QAR,W7DG-5:;EL-1369*111111z!4558.13NF12259.58W MEISSNER LOOKOUT N7QXO-7",
            PositionReport(
                raw=b"!4558.13NF12259.58W MEISSNER LOOKOUT N7QXO-7",
                data_type=DataType.POSITION_W_O_TIMESTAMP,
                data=b"4558.13NF12259.58W ",
                data_ext=b"",
                comment=b"MEISSNER LOOKOUT N7QXO-7",
                timestamp=None,
                lat=Decimal("45.96883333333333333333333333"),
                sym_table_id=b"F",
                long=Decimal("-122.993"),
                symbol_code=b" ",
            ),
            id="position, uncompressed, without timestamp, offset data type, comment",
        ),
        pytest.param(
            "UCAPK>APMI06,TCPIP*,QAS,K7CPR:@202350z4658.39N/12308.29W-WX3in1Plus2.0 U=13.9V",
            PositionReport(
                raw=b"@202350z4658.39N/12308.29W-WX3in1Plus2.0 U=13.9V",
                data_type=DataType.POSITION_W_TIMESTAMP_MSG,
                data=b"4658.39N/12308.29W-",
                data_ext=b"",
                comment=b"WX3in1Plus2.0 U=13.9V",
                timestamp=datetime.datetime(
                    2022, 5, 20, 23, 50, tzinfo=datetime.timezone.utc
                ),
                timestamp_format=TimestampFormat.DayHoursMinutesZulu,
                lat=Decimal("46.97316666666666666666666667"),
                sym_table_id=b"/",
                long=Decimal("-123.1381666666666666666666667"),
                symbol_code=b"-",
            ),
            id="position, uncompressed, with timestamp, comment",
        ),
        pytest.param(
            "FOO>APRS:!4605.21N/12327.31W#RNG0125Foo comment",
            PositionReport(
                raw=b"!4605.21N/12327.31W#RNG0125Foo comment",
                data_type=DataType.POSITION_W_O_TIMESTAMP,
                data=b"4605.21N/12327.31W#",
                data_ext=RNG(range=125),
                comment=b"Foo comment",
                timestamp=None,
                lat=Decimal("46.08683333333333333333333333"),
                sym_table_id=b"/",
                long=Decimal("-123.4551666666666666666666667"),
                symbol_code=b"#",
            ),
            id="position, uncompressed, without timestamp, rng, comment",
        ),
        pytest.param(
            "FOO>APRS:!4605.21N/12327.31W#DFS8745Foo comment",
            PositionReport(
                raw=b"!4605.21N/12327.31W#DFS8745Foo comment",
                data_type=DataType.POSITION_W_O_TIMESTAMP,
                data=b"4605.21N/12327.31W#",
                data_ext=DFS(strength_s=8, height_ft=1280, gain_db=4, directivity=225),
                comment=b"Foo comment",
                timestamp=None,
                lat=Decimal("46.08683333333333333333333333"),
                sym_table_id=b"/",
                long=Decimal("-123.4551666666666666666666667"),
                symbol_code=b"#",
            ),
            id="position, uncompressed, without timestamp, dfs, comment",
        ),
        pytest.param(
            "KF7HVM>APJYC1,qAR,W7DG-5:=/7.oh/FIK-  # Masen in Longview",
            PositionReport(
                raw=b"=/7.oh/FIK-  # Masen in Longview",
                data_type=DataType.POSITION_W_O_TIMESTAMP_MSG,
                data=b"/7.oh/FIK-  #",
                comment=b" Masen in Longview",
                position_format=PositionFormat.Compressed,
                sym_table_id=b"/",
                lat=Decimal("46.17683224563301"),
                long=Decimal("-122.98066816127016"),
                symbol_code=b"-",
            ),
            id="position, compressed, without timestamp",
        ),
        pytest.param(
            "KF7HVM>APJYC1,qAR,W7DG-5:=/7.oh/FIK-7P# Masen in Longview",
            PositionReport(
                raw=b"=/7.oh/FIK-7P# Masen in Longview",
                data_type=DataType.POSITION_W_O_TIMESTAMP_MSG,
                data=b"/7.oh/FIK-7P#",
                data_ext=CourseSpeed(course=88, speed=36.23201216883807),
                comment=b" Masen in Longview",
                position_format=PositionFormat.Compressed,
                sym_table_id=b"/",
                lat=Decimal("46.17683224563301"),
                long=Decimal("-122.98066816127016"),
                symbol_code=b"-",
            ),
            id="position, compressed, with cs",
        ),
        pytest.param(
            "SMSGTE>APSMS1,TCPIP,QAS,VE3OTB-12::KF0JGS-7 :@3037755154 I love you 2!{M1383",
            Message(
                raw=b":KF0JGS-7 :@3037755154 I love you 2!{M1383",
                data_type=DataType.MESSAGE,
                data=b"KF0JGS-7 :@3037755154 I love you 2!{M1383",
                data_ext=b"",
                comment=b"",
                addressee=b"KF0JGS-7",
                text=b"@3037755154 I love you 2!",
                number=b"M1383",
            ),
            id="message, needs ack",
        ),
        pytest.param(
            "KF0JGS-7>APSMS1,TCPIP,QAS,VE3OTB-12::SMSGTE   :ackM1383",
            Message(
                raw=b":SMSGTE   :ackM1383",
                data_type=DataType.MESSAGE,
                data=b"SMSGTE   :ackM1383",
                data_ext=b"",
                comment=b"",
                addressee=b"SMSGTE",
                text=b"ackM1383",
                number=None,
            ),
            id="message ack",
        ),
        pytest.param(
            "VE7VIC-15>APMI04,QAR,AF7DX-1::BLN1     :Net Mondays 19:00 146.840- T100.0",
            Message(
                raw=b":BLN1     :Net Mondays 19:00 146.840- T100.0",
                data_type=DataType.MESSAGE,
                data=b"BLN1     :Net Mondays 19:00 146.840- T100.0",
                data_ext=b"",
                comment=b"",
                addressee=b"BLN1",
                text=b"Net Mondays 19:00 146.840- T100.0",
                number=None,
            ),
            id="bulletin, no ack",
        ),
        pytest.param(
            "ROSLDG>BEACON,LINCON*,OR2-1,QAO,W7KKE:>Oregon Coast Repeater Group: WX: Rose Lodge, OR: www.ocrg.org:W7GC-5",
            StatusReport(
                raw=b">Oregon Coast Repeater Group: WX: Rose Lodge, OR: www.ocrg.org:W7GC-5",
                data_type=DataType.STATUS,
                data=b"Oregon Coast Repeater Group: WX: Rose Lodge, OR: www.ocrg.org:W7GC-5",
                data_ext=b"",
                comment=b"",
                status=b"Oregon Coast Repeater Group: WX: Rose Lodge, OR: www.ocrg.org:W7GC-5",
            ),
            id="status, no timestamp",
        ),
        pytest.param(
            "ROSLDG>BEACON,LINCON*,OR2-1,QAO,W7KKE:>232114zOregon Coast Repeater Group: WX: Rose Lodge, OR: www.ocrg.org:W7GC-5",
            StatusReport(
                raw=b">232114zOregon Coast Repeater Group: WX: Rose Lodge, OR: www.ocrg.org:W7GC-5",
                data_type=DataType.STATUS,
                data=b"Oregon Coast Repeater Group: WX: Rose Lodge, OR: www.ocrg.org:W7GC-5",
                data_ext=b"",
                comment=b"",
                timestamp=datetime.datetime(
                    2022, 5, 23, 21, 14, tzinfo=datetime.timezone.utc
                ),
                status=b"Oregon Coast Repeater Group: WX: Rose Lodge, OR: www.ocrg.org:W7GC-5",
            ),
            id="status, timestamp",
        ),
        pytest.param(
            "N7LOL-14>APX219,TCPIP*,QAC,SECOND:;W7ZA     *232209z4657.26N/12348.18WrPmin1,Pmax11,147.160+ T88.5 W7ZA.ORG",
            ObjectReport(
                raw=b";W7ZA     *232209z4657.26N/12348.18WrPmin1,Pmax11,147.160+ T88.5 W7ZA.ORG",
                data_type=DataType.OBJECT,
                data=b"4657.26N/12348.18Wr",
                data_ext=b"",
                comment=b"Pmin1,Pmax11,147.160+ T88.5 W7ZA.ORG",
                name=b"W7ZA",
                killed=False,
                timestamp=datetime.datetime(
                    2022,
                    5,
                    23,
                    22,
                    9,
                    tzinfo=datetime.timezone.utc,
                ),
                timestamp_format=TimestampFormat.DayHoursMinutesZulu,
                lat=Decimal("46.95433333333333333333333333"),
                sym_table_id=b"/",
                long=Decimal("-123.803"),
                symbol_code=b"r",
            ),
            id="object1",
        ),
        pytest.param(
            "FOO>APZ069,TCPIP*,QAC,KF7HVM:)AID #2!4903.50N/07201.75WAfirst aid",
            ItemReport(
                raw=b")AID #2!4903.50N/07201.75WAfirst aid",
                data_type=DataType.ITEM,
                data=b"4903.50N/07201.75WA",
                data_ext=b"",
                comment=b"first aid",
                name=b"AID #2",
                killed=False,
                lat=Decimal("49.05833333333333333333333333"),
                sym_table_id=b"/",
                long=Decimal("-72.02916666666666666666666667"),
                symbol_code=b"A",
            ),
            id="item, live, comment",
        ),
        pytest.param(
            "FOO>APZ069,TCPIP*,QAC,KF7HVM:)AID #2_4903.50N/07201.75WA042/000first aid",
            ItemReport(
                raw=b")AID #2_4903.50N/07201.75WA042/000first aid",
                data_type=DataType.ITEM,
                data=b"4903.50N/07201.75WA",
                data_ext=CourseSpeed(course=42, speed=0),
                comment=b"first aid",
                name=b"AID #2",
                killed=True,
                lat=Decimal("49.05833333333333333333333333"),
                sym_table_id=b"/",
                long=Decimal("-72.02916666666666666666666667"),
                symbol_code=b"A",
            ),
            id="item, killed, course/speed, comment",
        ),
    ),
)
def test_decode(packet_text, exp_decoded_iframe):
    f = Frame.from_str(packet_text)
    iframe = InformationField.from_frame(f)
    assert iframe == exp_decoded_iframe
    if (
        iframe.data_type == DataType.POSITION_W_O_TIMESTAMP
        and iframe.data_type.value != f.info[0:1]
    ):
        # special case for node prefix before '!' data
        assert bytes(iframe) == bytes(exp_decoded_iframe)
    else:
        # otherwise the re-encoded packet should match the input exactly
        assert bytes(iframe) == f.info
