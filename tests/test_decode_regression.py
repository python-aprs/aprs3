"""
Decode regression consists of real frames scraped from APRS-IS that
stumped us at one point.

Adding regression tests is an excellent tool for implementing decoders for
new information data types.
"""
import datetime
from decimal import Decimal

import pytest

from kiss3.ax25 import Frame

from aprs3.classes import (
    CourseSpeed,
    DataType,
    DFS,
    InformationField,
    PHG,
    PositionReport,
    RNG,
)


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
    ),
)
def test_decode(packet_text, exp_decoded_iframe):
    f = Frame.from_str(packet_text)
    iframe = InformationField.from_bytes(f.info)
    assert iframe == exp_decoded_iframe
