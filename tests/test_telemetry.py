"""Telemetry reports, metadata messages and base91 comment telemetry (#29)."""

from decimal import Decimal

import attrs
import pytest

from aprs import (
    APRSFrame,
    CommentTelemetry,
    Message,
    TelemetryBits,
    TelemetryEquations,
    TelemetryNames,
    TelemetryReport,
    TelemetryUnits,
)


def info(tnc2: str):
    return APRSFrame.from_str(tnc2).info


BITS = (False, True, True, False, True, False, False, True)


@pytest.mark.parametrize(
    "text, sequence, analog, digital, comment",
    [
        ("T#005,199,000,255,073,123,01101001", b"005", [199, 0, 255, 73, 123], BITS, b""),
        ("T#MIC199,000,255,073,123,01101001", b"MIC", [199, 0, 255, 73, 123], BITS, b""),
        ("T#MIC,199,000,255,073,123,01101001", b"MIC", [199, 0, 255, 73, 123], BITS, b""),
        (
            "T#123,1.5,-2,3000,4,5,00000000 Balloon payload",
            b"123",
            [Decimal("1.5"), -2, 3000, 4, 5],
            (False,) * 8,
            b" Balloon payload",
        ),
        ("T#7,199,000", b"7", [199, 0], None, b""),
    ],
)
def test_telemetry_report(text, sequence, analog, digital, comment):
    report = info(f"N0CALL>APRS:{text}")
    assert isinstance(report, TelemetryReport)
    assert report.sequence == sequence
    assert list(report.analog) == analog
    assert report.digital == digital
    assert report.comment == comment
    assert bytes(report) == text.encode()


@pytest.mark.parametrize(
    "text",
    [
        "T#005,199,000,255,073,123,0110",  # short bits
        "T#ABC,1,2,3,4,5,00000000",  # sequence
        "T#001,1,x,3",  # value
        "T#001,1,NaN,3",
        "Test packet",  # T without "#"
    ],
)
def test_bad_telemetry_stays_raw(text):
    field = info(f"N0CALL>APRS:{text}")
    assert type(field) is not TelemetryReport
    assert bytes(field) == text.encode()


def test_build_telemetry():
    report = TelemetryReport.new(7, [1, 2.5, 300])
    assert bytes(report) == b"T#007,001,2.5,300"
    assert info("N0CALL>APRS:" + bytes(report).decode()).analog == report.analog
    with pytest.raises(ValueError):
        TelemetryReport.new(7, [1, 2.5, 300], [1, 0, 0, 0, 0, 0, 0, 1])
    report = TelemetryReport.new("MIC", [1, 2, 3, 4, 5], [True] * 8, comment=b" hi")
    assert bytes(report) == b"T#MIC,001,002,003,004,005,11111111 hi"
    assert info("N0CALL>APRS:" + bytes(report).decode()).analog == report.analog
    assert bytes(TelemetryReport.new(1234, [1000, -1])) == b"T#234,1000,-1"
    with pytest.raises(ValueError):
        TelemetryReport.new(1, range(6))


def test_evolved_report_is_reencoded():
    report = info("N0CALL>APRS:T#MIC199,000,255,073,123,01101001")
    assert (
        bytes(attrs.evolve(report, sequence=b"006"))
        == b"T#006,199,000,255,073,123,01101001"
    )
    with pytest.raises(ValueError):
        bytes(attrs.evolve(report, digital=(True,)))


def test_metadata_messages():
    parm = info(
        "N0CALL>APRS::N0CALL-1 :PARM.Battery,Btemp,ATemp,Pres,Alt,Camra,Chute,Sun,10m,ATV"
    )
    assert parm.telemetry_metadata == TelemetryNames(
        [
            b"Battery",
            b"Btemp",
            b"ATemp",
            b"Pres",
            b"Alt",
            b"Camra",
            b"Chute",
            b"Sun",
            b"10m",
            b"ATV",
        ]
    )
    unit = info(
        "N0CALL>APRS::N0CALL-1 :UNIT.v/100,deg.F,deg.F,Mbar,Kft,Click,OPEN,on,on,hi"
    )
    assert unit.telemetry_metadata.units[:2] == (b"v/100", b"deg.F")
    eqns = info("N0CALL>APRS::N0CALL-1 :EQNS.0,5.2,0,0,.53,-32,3,4.39,49,-32,3,18,1,2,3")
    equations = eqns.telemetry_metadata
    assert isinstance(equations, TelemetryEquations)
    assert equations.coefficients[1] == (0, Decimal(".53"), -32)
    bits = info("N0CALL>APRS::N0CALL-1 :BITS.10110000,N0CALL Balloon").telemetry_metadata
    assert bits == TelemetryBits((1, 0, 1, 1, 0, 0, 0, 0), b"N0CALL Balloon")
    assert info("N0CALL>APRS::N0CALL-1 :hello").telemetry_metadata is None
    assert info("N0CALL>APRS::N0CALL-1 :BITS.12,x").telemetry_metadata is None
    assert info("N0CALL>APRS::N0CALL-1 :EQNS.1,2").telemetry_metadata is None


def test_scaled_values():
    report = info("N0CALL>APRS:T#005,199,000,255,073,123,01101001")
    equations = TelemetryEquations([(0, 5.2, 0), (0, ".53", -32), (3, 4.39, 49)])
    assert report.scaled(equations) == (
        Decimal("1034.8"),
        Decimal(-32),
        Decimal(3 * 255 * 255) + Decimal("4.39") * 255 + 49,
        Decimal(73),
        Decimal(123),
    )


@pytest.mark.parametrize(
    "metadata, text",
    [
        (TelemetryNames([b"Vbat", b"Temp"]), b"PARM.Vbat,Temp"),
        (TelemetryUnits([b"V", b"C"]), b"UNIT.V,C"),
        (TelemetryEquations([(0, 0.01, 0), (0, 1, -40)]), b"EQNS.0,0.01,0,0,1,-40"),
        (TelemetryBits([1] * 8, b"WX station"), b"BITS.11111111,WX station"),
    ],
)
def test_build_metadata(metadata, text):
    message = metadata.to_message("N0CALL-1")
    assert isinstance(message, Message)
    assert message.addressee == b"N0CALL-1" and message.text == text
    assert Message.from_bytes(bytes(message)).telemetry_metadata == metadata


def test_comment_telemetry():
    report = info("N0CALL>APRS:!/5L!!<*e7>  T|!!!!!+|")
    assert report.comment_telemetry == CommentTelemetry(0, (0, 10))
    assert info("N0CALL>APRS:!4903.50N/07201.75W-no telemetry").comment_telemetry is None
    full = CommentTelemetry(8280, [1, 2, 3, 4, 8280], [1, 0, 0, 0, 0, 0, 0, 1])
    assert CommentTelemetry.from_comment(b"x" + bytes(full) + b"y") == full
    assert bytes(CommentTelemetry(91, [0])) == b'|"!!!|'
    with pytest.raises(ValueError):
        bytes(CommentTelemetry(1, []))
    with pytest.raises(ValueError):
        bytes(CommentTelemetry(1, [1, 2], [True] * 8))
