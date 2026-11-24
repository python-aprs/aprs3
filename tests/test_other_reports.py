"""Third-party traffic (#30), raw NMEA (#31) and the remaining data types (#33)."""

import datetime
from decimal import Decimal

import attrs
import pytest

from aprs import (
    APRSFrame,
    CapabilitiesReport,
    DirectionFinding,
    MaidenheadReport,
    Message,
    NMEAReport,
    PositionReport,
    QueryReport,
    StatusReport,
    ThirdPartyReport,
    UserDefinedReport,
    grid_to_lat_long,
    nmea_checksum,
)


def info(tnc2: str):
    return APRSFrame.from_str(tnc2).info


# --- third-party ---------------------------------------------------------------


def test_third_party_message():
    report = info(
        "N0GATE>APRS,WIDE2-1:}W1AW>APRS,TCPIP,N0GATE*::N0CALL   :hello from IS{12"
    )
    assert isinstance(report, ThirdPartyReport)
    inner = report.frame
    assert str(inner.source) == "W1AW"
    assert str(inner).partition(":")[0] == "W1AW>APRS,TCPIP,N0GATE*"
    assert isinstance(inner.info, Message)
    assert (inner.info.addressee, inner.info.text, inner.info.number) == (
        b"N0CALL",
        b"hello from IS",
        b"12",
    )


def test_third_party_position():
    report = info(
        "N0GATE>APRS:}N0CALL-9>APDR16,TCPIP,N0GATE*:=4903.50N/07201.75W$ via APRSdroid"
    )
    assert isinstance(report.frame.info, PositionReport)
    assert float(report.frame.info.lat) == pytest.approx(49.058333, abs=1e-6)


def test_build_third_party():
    inner = APRSFrame.from_str("W1AW>APRS,TCPIP,N0GATE*:>status")
    report = ThirdPartyReport(raw=b"", data_type=None, data=b"", frame=inner)
    assert bytes(report) == b"}W1AW>APRS,TCPIP,N0GATE*:>status"
    frame = APRSFrame.ui(
        destination="APRS", source="N0GATE", path=["WIDE2-1"], info=report
    )
    assert isinstance(frame.info, ThirdPartyReport)
    assert isinstance(frame.info.frame.info, StatusReport)


def test_third_party_reencodes_after_change():
    report = info("N0GATE>APRS:}W1AW>APRS,TCPIP,N0GATE*:>status")
    changed = attrs.evolve(report, frame=APRSFrame.from_str("W1AW>APRS:>other"))
    assert bytes(changed) == b"}W1AW>APRS:>other"


# --- NMEA -------------------------------------------------------------------------


def test_nmea_rmc():
    report = info(
        "N0CALL>APRS:$GPRMC,063909,A,3349.4302,N,11700.3721,W,43.022,89.3,291099,13.6,E*52"
    )
    assert isinstance(report, NMEAReport)
    assert report.sentence_type == b"GPRMC"
    assert report.checksum == b"52"
    assert float(report.lat) == pytest.approx(33.823837, abs=1e-6)
    assert float(report.long) == pytest.approx(-117.006202, abs=1e-6)
    assert (report.speed_knots, report.course) == (Decimal("43.022"), Decimal("89.3"))
    assert report.valid is True
    assert report.timestamp == datetime.datetime(
        1999, 10, 29, 6, 39, 9, tzinfo=datetime.UTC
    )


def test_nmea_gga():
    report = info(
        "N0CALL>APRS:$GPGGA,102705,5157.9762,N,00029.3256,W,1,04,2.0,75.7,M,47.6,M,,*62"
    )
    assert report.altitude_m == Decimal("75.7")
    assert report.time == datetime.time(10, 27, 5, tzinfo=datetime.UTC)
    assert report.date is None and report.timestamp is None
    assert float(report.long) == pytest.approx(-0.48876)


def test_nmea_gll_and_vtg():
    gll = info("N0CALL>APRS:$GPGLL,4916.45,N,12311.12,W,225444,A*31")
    assert (round(gll.lat, 4), round(gll.long, 4)) == (
        Decimal("49.2742"),
        Decimal("-123.1853"),
    )
    vtg = info("N0CALL>APRS:$GPVTG,089.3,T,,M,43.022,N,79.7,K")
    assert vtg.checksum is None
    assert (vtg.course, vtg.speed_knots, vtg.lat, vtg.valid) == (
        Decimal("89.3"),
        Decimal("43.022"),
        None,
        None,
    )


def test_nmea_other_sentence_keeps_fields():
    report = NMEAReport.from_bytes(
        b"$GPGSA,A,3,04,05,,09*" + nmea_checksum(b"GPGSA,A,3,04,05,,09")
    )
    assert report.fields[:2] == [b"A", b"3"]
    assert report.lat is None


@pytest.mark.parametrize(
    "text",
    [
        "$GPRMC,063909,A,3349.4302,N,11700.3721,W,43.022,89.3,291099,13.6,E*53",  # checksum
        "$GPRMC,063909,A,3399.4302,N,11700.3721,W,43.022,89.3,291099,13.6,E",  # 99 minutes
        "$GPGLL,4916.45,X,12311.12,W,225444,A",  # hemisphere
        "$GPRMC,063909,A,3349.4302,N,11700.3721,W,43.022,89.3,321399,,",  # date
        "$xx",
    ],
)
def test_bad_nmea_stays_raw(text):
    field = info(f"N0CALL>APRS:{text}")
    assert type(field) is not NMEAReport
    assert bytes(field) == text.encode()


def test_build_nmea():
    report = NMEAReport.from_sentence("GPGLL,4916.45,N,12311.12,W,225444,A")
    assert bytes(report) == b"$GPGLL,4916.45,N,12311.12,W,225444,A*31"
    assert info("N0CALL>APRS:" + bytes(report).decode()) == NMEAReport.from_bytes(
        bytes(report)
    )


def test_nmea_lower_case_checksum():
    report = NMEAReport.from_bytes(b"$GPGLL,4916.45,N,12311.12,W,225444,A*31")
    assert report.checksum == b"31"
    assert (
        NMEAReport.from_bytes(b"$GPGGA,1*" + nmea_checksum(b"GPGGA,1").lower()).time
        is None
    )


# --- queries, capabilities, grid squares, user-defined ------------------------------


@pytest.mark.parametrize(
    "text, query, target",
    [
        ("?APRS?", b"APRS", b""),
        ("?IGATE?", b"IGATE", b""),
        ("?WX?", b"WX", b""),
        ("?APRS? 34.02,-117.15,0200", b"APRS", b" 34.02,-117.15,0200"),
    ],
)
def test_general_query(text, query, target):
    report = info(f"N0CALL>APRS:{text}")
    assert isinstance(report, QueryReport)
    assert (report.query, report.target) == (query, target)
    assert bytes(attrs.evolve(report)) == text.encode()


@pytest.mark.parametrize(
    "text, query",
    [
        ("?APRSP", b"APRSP"),
        ("?PING?", b"PING"),
        ("?APRSD", b"APRSD"),
        ("?WX", b"WX"),
        ("?APRSH N0CALL", b"APRSH"),
        ("hello?", None),
        ("?", None),
    ],
)
def test_directed_query(text, query):
    assert info(f"N0CALL>APRS::N0CALL-1 :{text}").query == query


def test_capabilities():
    report = info("N0CALL>APRS:<IGATE,MSG_CNT=30,LOC_CNT=61")
    assert isinstance(report, CapabilitiesReport)
    assert report.capabilities == {b"IGATE": None, b"MSG_CNT": b"30", b"LOC_CNT": b"61"}
    built = CapabilitiesReport(
        raw=b"", data_type=None, data=b"", entries=[(b"IGATE", None), (b"MSG_CNT", b"1")]
    )
    assert bytes(built) == b"<IGATE,MSG_CNT=1"


def test_maidenhead():
    report = info("N0CALL>APRS:[IO91SX] 35 miles NNW of London")
    assert isinstance(report, MaidenheadReport)
    assert (report.grid, report.comment) == (b"IO91SX", b" 35 miles NNW of London")
    assert float(report.lat) == pytest.approx(51.979167)
    assert float(report.long) == pytest.approx(-0.458333)
    assert bytes(attrs.evolve(report)) == b"[IO91SX] 35 miles NNW of London"


@pytest.mark.parametrize(
    "grid, lat, long",
    [
        ("JJ00", 0.5, 1),
        ("AA00aa", -90 + 1.25 / 60, -180 + 2.5 / 60),
        ("RR99xx", 90 - 1.25 / 60, 180 - 2.5 / 60),
    ],
)
def test_grid_to_lat_long(grid, lat, long):
    got_lat, got_long = grid_to_lat_long(grid)
    assert (float(got_lat), float(got_long)) == pytest.approx((lat, long))


@pytest.mark.parametrize("grid", ["SS00", "IO9", "IO91S", "IO91YY", ""])
def test_bad_grid(grid):
    with pytest.raises(ValueError):
        grid_to_lat_long(grid)


def test_user_defined():
    report = info("N0CALL>APRS:{Q1qwerty")
    assert isinstance(report, UserDefinedReport)
    assert (report.user_id, report.packet_type, report.payload) == (b"Q", b"1", b"qwerty")
    assert bytes(attrs.evolve(report, payload=b"x")) == b"{Q1x"


# --- DF reports ----------------------------------------------------------------------


def test_df_report():
    report = info(r"N0CALL>APRS:@092345z4903.50N/07201.75W\088/036/270/729")
    assert report.df == DirectionFinding(bearing=270, hits=7, range_code=2, quality=9)
    assert (report.df.range_mi, report.df.beamwidth) == (4, 1)
    assert bytes(report.df) == b"/270/729"
    assert DirectionFinding(1, 0, 0, 0).beamwidth is None


@pytest.mark.parametrize(
    "text",
    [
        "!4903.50N/07201.75W>088/036/270/729",  # not the DF symbol
        r"!4903.50N/07201.75W\270/729",  # no course/speed first
        r"!4903.50N/07201.75W\088/036 no bearing",
    ],
)
def test_not_a_df_report(text):
    assert info(f"N0CALL>APRS:{text}").df is None


@pytest.mark.parametrize(
    "inner_info",
    ["café 😀".encode(), b"caf\xe9 (Latin-1)"],
    ids=["utf-8", "not-utf-8"],
)
def test_third_party_keeps_inner_info_bytes(inner_info):
    raw = b"}W1AW>APRS,TCPIP,N0GATE*:>" + inner_info
    report = APRSFrame.ui(destination="APRS", source="N0GATE", info=raw).info
    assert isinstance(report, ThirdPartyReport)
    assert report.frame.info.raw == b">" + inner_info
    # encoded from its fields (not the kept source bytes), it's still the same
    assert bytes(attrs.evolve(report)) == raw
