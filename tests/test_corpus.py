"""
Decode and re-encode every packet in tests/corpus/packets.txt.

A receive-only station may get away with a lossy decoder, but a client that
logs, digipeats or gates frames must not change them. So each packet has to
decode to the expected class and serialize back to the identical frame, both as
TNC2 text and through AX.25 binary (the KISS path).
"""

import datetime
import re
from pathlib import Path

import pytest

from aprs import (
    APRSFrame,
    CourseSpeed,
    DataType,
    InformationField,
    ItemReport,
    Message,
    ObjectReport,
    Position,
    PositionReport,
    StatusReport,
)

CORPUS = Path(__file__).parent / "corpus" / "packets.txt"

# packet text -> reason; these are expected to fail until the bug is fixed
KNOWN_BUGS: dict[str, str] = {}


def _unescape(line: str) -> str:
    return re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), line)


def load_corpus():
    for lineno, line in enumerate(CORPUS.read_text("ascii").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        expected_class, _, tnc2 = line.partition(" ")
        tnc2 = _unescape(tnc2)
        marks = []
        if tnc2 in KNOWN_BUGS:
            marks.append(pytest.mark.xfail(reason=KNOWN_BUGS[tnc2], strict=True))
        yield pytest.param(expected_class, tnc2, id=f"L{lineno}", marks=marks)


CORPUS_PARAMS = list(load_corpus())


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch):
    """Timestamps in the corpus are placed relative to this "now"."""
    monkeypatch.setattr(
        "aprs.timestamp._now",
        lambda tz: datetime.datetime(2024, 6, 15, 12, 0, tzinfo=tz),
    )


def test_known_bugs_are_in_corpus():
    tnc2s = {p.values[1] for p in CORPUS_PARAMS}
    assert set(KNOWN_BUGS) <= tnc2s


@pytest.mark.parametrize("expected_class, tnc2", CORPUS_PARAMS)
def test_decode_and_round_trip(expected_class, tnc2):
    frame = APRSFrame.from_str(tnc2)
    assert type(frame.info).__name__ == expected_class
    assert isinstance(frame.info, InformationField)
    assert str(frame) == tnc2
    header = tnc2.partition(":")[0]
    if header == header.upper():
        # APRS-IS q-constructs (qAR, qAC...) can't be AX.25 addresses
        assert str(APRSFrame.from_bytes(bytes(frame))) == tnc2


def info(tnc2: str):
    return APRSFrame.from_str(tnc2).info


@pytest.mark.parametrize(
    "tnc2, addressee, text, number",
    [
        ("N0CALL>APRS::WU2Z     :Testing", b"WU2Z", b"Testing", None),
        ("N0CALL>APRS::WU2Z     :Testing{003", b"WU2Z", b"Testing", b"003"),
        ("N0CALL>APRS::N0CALL-12:Hi there{12345", b"N0CALL-12", b"Hi there", b"12345"),
        ("N0CALL>APRS::WU2Z     :brace { in text", b"WU2Z", b"brace { in text", None),
        # acks and rejects carry the number in the text; no number of their own
        ("N0CALL>APRS::WU2Z     :ack003", b"WU2Z", b"ack003", None),
        ("N0CALL>APRS::WU2Z     :rej003", b"WU2Z", b"rej003", None),
        # reply-ack: "{MM}AA" is the message number MM plus an ack for AA
        ("N0CALL>APRS::WU2Z     :Testing{AB}", b"WU2Z", b"Testing", b"AB}"),
        ("N0CALL>APRS::WU2Z     :Testing{AB}CD", b"WU2Z", b"Testing", b"AB}CD"),
        ("N0CALL>APRS::WU2Z     :ackAB}CD", b"WU2Z", b"ackAB}CD", None),
        (
            "N0CALL>APRS::BLN1     :Snow expected in Tampa RSN",
            b"BLN1",
            b"Snow expected in Tampa RSN",
            None,
        ),
    ],
)
def test_message_fields(tnc2, addressee, text, number):
    message = info(tnc2)
    assert isinstance(message, Message)
    assert (message.addressee, message.text, message.number) == (addressee, text, number)


def test_message_requires_addressee_terminator():
    with pytest.raises(ValueError):
        info("N0CALL>APRS::WU2Z:short addressee")


def test_status_fields():
    status = info("N0CALL>APRS:>092345zNet Control Center")
    assert isinstance(status, StatusReport)
    assert status.status == b"Net Control Center"
    assert status.timestamp == datetime.datetime(2024, 6, 9, 23, 45, tzinfo=datetime.UTC)
    plain = info("N0CALL>APRS:>Net Control Center")
    assert plain.status == b"Net Control Center" and plain.timestamp is None


@pytest.mark.parametrize(
    "tnc2, name, killed",
    [
        ("N0CALL>APRS:;LEADER   *092345z4903.50N/07201.75W>088/036", b"LEADER", False),
        ("N0CALL>APRS:;LEADER   _092345z4903.50N/07201.75W>088/036", b"LEADER", True),
        (
            "N0CALL>APRS:;145.290-R*111111z4903.50N/07201.75Wr145.290MHz T100 -060 R40m",
            b"145.290-R",
            False,
        ),
    ],
)
def test_object_fields(tnc2, name, killed):
    obj = info(tnc2)
    assert isinstance(obj, ObjectReport)
    assert (obj.name, obj.killed) == (name, killed)
    assert float(obj.lat) == pytest.approx(49.058333, abs=1e-6)
    assert float(obj.long) == pytest.approx(-72.029167, abs=1e-6)
    assert obj.timestamp is not None and obj.timestamp.tzinfo is datetime.UTC


def test_object_without_timestamp_is_rejected():
    # APRS101 p58: the timestamp is mandatory
    with pytest.raises(ValueError):
        info("N0CALL>APRS:;LEADER   *4903.50N/07201.75W>no timestamp")


@pytest.mark.parametrize(
    "tnc2, name, killed, comment",
    [
        ("N0CALL>APRS:)AID #2!4903.50N/07201.75WA", b"AID #2", False, b""),
        ("N0CALL>APRS:)AID #2_4903.50N/07201.75WA", b"AID #2", True, b""),
        (
            "N0CALL>APRS:)FD!4903.50N/07201.75W;Field Day site",
            b"FD",
            False,
            b"Field Day site",
        ),
    ],
)
def test_item_fields(tnc2, name, killed, comment):
    item = info(tnc2)
    assert isinstance(item, ItemReport)
    assert (item.name, item.killed, item.comment) == (name, killed, comment)
    assert item.symbol_code is not None


def test_position_fields():
    report = info("N0CALL>APRS:=4903.50N/07201.75W>088/036/A=001234 mobile")
    assert isinstance(report, PositionReport)
    assert (report.sym_table_id, report.symbol_code) == (b"/", b">")
    assert report.data_ext == CourseSpeed(course=88, speed=36)
    assert report.comment == b"/A=001234 mobile"


@pytest.mark.parametrize(
    "tnc2, data_type",
    [
        ("N0CALL>APRS:,test invalid", DataType.INVALID_DATA),
        ("N0CALL>APRS:%DF data", DataType.AGRELO_DFJR),
        ("N0CALL>APRS:#W1AW weather", DataType.PEET_BROS_U_II),
        # a data type with a decoder, but not in a form it decodes
        ("N0CALL>APRS:}garbage", DataType.THIRD_PARTY_TRAFFIC),
        ("N0CALL>APRS:?", DataType.QUERY),
    ],
)
def test_unsupported_formats_kept_raw(tnc2, data_type):
    """No decoder: the data type is identified and the rest kept verbatim."""
    field = info(tnc2)
    assert type(field) is InformationField
    assert field.data_type is data_type
    assert field.data == b""
    assert field.comment == field.raw[1:]


def test_unknown_data_type_is_kept():
    # e.g. a Kenwood "]" prefix: issue #20, the frame decodes with the raw bytes
    tnc2 = "N0CALL-7>APK102:]=4903.50N/07201.75W>Kenwood"
    field = info(tnc2)
    assert type(field) is InformationField
    assert field.data_type is None
    assert field.comment == field.raw == b"]=4903.50N/07201.75W>Kenwood"
    assert str(APRSFrame.from_str(tnc2)) == tnc2


def test_positive_altitude_comment():
    report = info("N0CALL>APRS:=4903.50N/07201.75W>088/036/A=001234 mobile")
    assert report.altitude_ft == 1234


def test_negative_altitude_comment():
    assert info("N0CALL>APRS:=4903.50N/07201.75Wl/A=-00012").altitude_ft == -12


def test_compressed_course_speed():
    # APRS101 p40: course 88, speed 36.2 knots
    report = info("N0CALL>APRS:=/5L!!<*e7>7P[")
    assert float(report.lat) == pytest.approx(49.5, abs=1e-4)
    assert float(report.long) == pytest.approx(-72.75, abs=1e-4)
    assert report.data_ext.course == 88
    assert report.data_ext.speed == pytest.approx(36.2, abs=0.1)


def test_compressed_altitude():
    # APRS101 p40: altitude 10004 ft
    report = info("N0CALL>APRS:=/5L!!<*e7OS]S")
    assert report.altitude_ft == pytest.approx(10004, abs=1)
    assert report.data_ext == b""


@pytest.mark.parametrize(
    "tnc2, ambiguity, lat, long",
    [
        # an ambiguous position is placed in the middle of its box
        ("N0CALL>APRS:!4903.50N/07201.75W-", 0, 49 + 3.5 / 60, -(72 + 1.75 / 60)),
        ("N0CALL>APRS:!4903.5 N/07201.7 W-", 1, 49 + 3.55 / 60, -(72 + 1.75 / 60)),
        ("N0CALL>APRS:!4903.  N/07201.  W-", 2, 49 + 3.5 / 60, -(72 + 1.5 / 60)),
        ("N0CALL>APRS:!490 .  N/0720 .  W-", 3, 49 + 5 / 60, -(72 + 5 / 60)),
        ("N0CALL>APRS:!49  .  N/072  .  W-", 4, 49.5, -72.5),
        ("N0CALL>APRS:!49  .  S/072  .  E-", 4, -49.5, 72.5),
    ],
)
def test_position_ambiguity(tnc2, ambiguity, lat, long):
    report = info(tnc2)
    assert report._position.ambiguity == ambiguity
    assert float(report.lat) == pytest.approx(lat)
    assert float(report.long) == pytest.approx(long)


@pytest.mark.parametrize(
    "info_text",
    [
        "!49 3.50N/07201.75W-",  # space inside the digits
        "!4903.50X/07201.75W-",  # bad hemisphere
        "!4903.50N/07201.75Q-",
        "!4903.50N/0720",  # truncated
        "!     .  N/     .  W-",  # more than 4 digits blanked
    ],
)
def test_malformed_position_is_rejected(info_text):
    with pytest.raises(ValueError):
        info(f"N0CALL>APRS:{info_text}")


def test_bang_in_unsupported_format_stays_raw():
    """A "!" that doesn't start a position leaves the packet undecoded, not dropped."""
    field = info("N0CALL>APRS:,MSG_CNT=30!,LOC_CNT=61")
    assert type(field) is InformationField
    assert field.data_type is DataType.INVALID_DATA


def test_compressed_object():
    obj = info("N0CALL>APRS:;LEADER   *092345z/5L!!<*e7>7P[")
    assert isinstance(obj, ObjectReport)
    assert obj.name == b"LEADER"
    assert float(obj.lat) == pytest.approx(49.5, abs=1e-4)
    assert obj.data_ext.course == 88


def test_offset_position_keeps_prefix():
    report = info("N0CALL>APRS:TNC2 BTEXT !4903.50N/07201.75W-header")
    assert isinstance(report, PositionReport)
    assert report.prefix == b"TNC2 BTEXT "
    assert report.comment == b"header"


# --- pre-release bug fixes ---------------------------------------------------


def test_compressed_position_keeps_following_text_as_comment():
    """Issue #19: was TypeError (data_ext passed twice)."""
    report = info("N0CALL>APRS:!/5L!!<*e7>  TPHG5132 igate")
    assert report.data_ext == b""
    assert report.comment == b"PHG5132 igate"
    report = info("N0CALL>APRS:=/5L!!<*e7>7P[RNG0050")
    assert isinstance(report.data_ext, CourseSpeed)
    assert report.comment == b"RNG0050"


@pytest.mark.parametrize("text", ["hello world", "", "&foo", "]Kenwood"])
def test_unknown_data_type_decodes(text):
    """Issue #20."""
    field = info(f"N0CALL>APRS:{text}")
    assert type(field) is InformationField
    assert field.data_type is None
    assert field.raw == field.comment == text.encode()


def test_unknown_data_type_with_position_after_text():
    """Issue #20: APRS101 p32 allows a position after up to 40 characters."""
    report = info("N0CALL>APRS:TNC beacon !4903.50N/07201.75W-")
    assert isinstance(report, PositionReport)
    assert report.prefix == b"TNC beacon "


def test_old_mic_e_data_type():
    """Issue #21."""
    assert DataType.OLD_MIC_E_DATA.value == b"\x1d"
    assert DataType.OLD_MIC_E_DATA is not DataType.CURRENT_MIC_E_DATA
    assert info("N0CALL>APRS:\x1d'abc").data_type is DataType.OLD_MIC_E_DATA


def test_killed_item_with_bang_in_comment():
    """Issue #22."""
    item = info("N0CALL>APRS:)AID #2_4903.50N/07201.75WA comment!")
    assert isinstance(item, ItemReport)
    assert (item.name, item.killed, item.comment) == (b"AID #2", True, b" comment!")
    live = info("N0CALL>APRS:)AID #2!4903.50N/07201.75WA under_score")
    assert (live.name, live.killed, live.comment) == (b"AID #2", False, b" under_score")


def test_item_without_terminator_is_rejected():
    with pytest.raises(ValueError):
        info("N0CALL>APRS:)NO TERMINATOR")


def test_course_360_is_kept():
    """Issue #23."""
    report = info("N0CALL>APRS:!4903.50N/07201.75W>360/010")
    assert report.data_ext == CourseSpeed(course=360, speed=10)
    assert bytes(CourseSpeed(course=0, speed=10)) == b"000/010"


@pytest.mark.parametrize("course", [-1, 361, 999])
def test_course_out_of_range(course):
    """Issue #23: no silent wrap."""
    with pytest.raises(ValueError):
        CourseSpeed(course=course, speed=0)
    # as text it isn't a course/speed extension, so it stays in the comment
    report = info(f"N0CALL>APRS:!4903.50N/07201.75W>{course:03d}/010")
    assert report.data_ext == b""


@pytest.mark.parametrize(
    "info_text",
    [
        "!9903.50N/07201.75W-",  # 99 degrees north
        "!9000.01N/07201.75W-",  # just past the pole
        "!4903.50N/18201.75W-",  # 182 degrees west
        "!4903.50N/18000.01E-",
        "!4963.50N/07201.75W-",  # 63 minutes
        "!4903.50N/07260.00W-",
    ],
)
def test_out_of_range_position_is_rejected(info_text):
    """Issue #24: rejected like other malformed positions."""
    with pytest.raises(ValueError):
        info(f"N0CALL>APRS:{info_text}")


def test_position_limits_decode():
    assert float(info("N0CALL>APRS:!9000.00N/18000.00W-").lat) == 90
    assert float(info("N0CALL>APRS:!9000.00S/18000.00E-").long) == 180


@pytest.mark.parametrize("kwargs", [{"lat": 90.5}, {"lat": -91}, {"long": 180.1}])
def test_out_of_range_position_cannot_be_built(kwargs):
    """Issue #24."""
    with pytest.raises(ValueError):
        Position(**kwargs)


def test_ambiguity_only_centres_blanked_digits():
    """Issue #25."""
    report = info("N0CALL>APRS:!4903.5 N/07201.75W-")
    assert report.lat == pytest.approx(49.059167, abs=1e-6)
    assert report.long == pytest.approx(-72.029167, abs=1e-6)
    assert report._position.ambiguity == 1
    assert report._position.long_ambiguity == 0

    report = info("N0CALL>APRS:!4903.50N/0720 .  W-")
    assert report.lat == pytest.approx(49.058333, abs=1e-6)
    # 072 degrees 0x minutes: centred at 072 05'
    assert report.long == pytest.approx(-72.083333, abs=1e-6)
    assert report._position.long_ambiguity == 3


def test_matching_ambiguity_leaves_long_ambiguity_unset():
    report = info("N0CALL>APRS:!4903.  N/07201.  W-")
    assert report._position.ambiguity == 2
    assert report._position.long_ambiguity is None
