"""Timestamps carry no year (and DHM/HMS no month): check how they're placed."""

import datetime

import pytest

from aprs.constants import TimestampFormat
from aprs.timestamp import Timestamp

UTC = datetime.UTC


@pytest.fixture
def now(monkeypatch):
    """Set the reference "now" used to complete timestamps."""

    def set_now(*args):
        def fake_now(tz):
            return datetime.datetime(*args, tzinfo=tz)

        monkeypatch.setattr("aprs.timestamp._now", fake_now)

    return set_now


@pytest.mark.parametrize(
    "now_args, raw, expected",
    [
        pytest.param(
            (2024, 6, 15, 12, 0), b"151130z", (2024, 6, 15, 11, 30), id="dhm-today"
        ),
        pytest.param(
            (2024, 6, 15, 12, 0),
            b"151259z",
            (2024, 6, 15, 12, 59),
            id="dhm-within-threshold",
        ),
        pytest.param(
            (2024, 6, 15, 12, 0),
            b"151301z",
            (2024, 5, 15, 13, 1),
            id="dhm-future-is-last-month",
        ),
        pytest.param(
            (2024, 6, 15, 12, 0),
            b"200000z",
            (2024, 5, 20, 0, 0),
            id="dhm-later-day-is-last-month",
        ),
        pytest.param(
            (2024, 1, 2, 0, 0),
            b"311200z",
            (2023, 12, 31, 12, 0),
            id="dhm-january-rolls-to-december",
        ),
        pytest.param(
            (2024, 5, 1, 0, 0),
            b"311200z",
            (2024, 3, 31, 12, 0),
            id="dhm-skips-30-day-month",
        ),
        pytest.param(
            (2024, 3, 1, 0, 0), b"300000z", (2024, 1, 30, 0, 0), id="dhm-skips-february"
        ),
        pytest.param(
            (2024, 3, 1, 0, 0), b"290000z", (2024, 2, 29, 0, 0), id="dhm-leap-day"
        ),
        pytest.param(
            (2024, 6, 15, 12, 0), b"113045h", (2024, 6, 15, 11, 30, 45), id="hms-today"
        ),
        pytest.param(
            (2024, 6, 15, 12, 0),
            b"235959h",
            (2024, 6, 14, 23, 59, 59),
            id="hms-future-is-yesterday",
        ),
        pytest.param(
            (2024, 1, 1, 0, 30), b"235900h", (2023, 12, 31, 23, 59), id="hms-new-year"
        ),
        pytest.param(
            (2024, 6, 15, 12, 0), b"06151130", (2024, 6, 15, 11, 30), id="mdhm-this-year"
        ),
        pytest.param(
            (2024, 6, 15, 12, 0),
            b"12251800",
            (2023, 12, 25, 18, 0),
            id="mdhm-future-is-last-year",
        ),
        pytest.param(
            (2023, 6, 15, 12, 0),
            b"02291200",
            (2020, 2, 29, 12, 0),
            id="mdhm-leap-day-last-leap-year",
        ),
    ],
)
def test_decode(now, now_args, raw, expected):
    now(*now_args)
    ts = Timestamp.from_bytes(raw)
    assert ts.timestamp == datetime.datetime(*expected, tzinfo=UTC)
    assert bytes(ts) == raw


def test_decode_local_is_naive(now):
    now(2024, 6, 15, 12, 0)
    ts = Timestamp.from_bytes(b"151130/")
    assert ts.timestamp_format is TimestampFormat.DayHoursMinutesLocal
    assert ts.timestamp == datetime.datetime(2024, 6, 15, 11, 30)
    assert ts.timestamp.tzinfo is None
    assert bytes(ts) == b"151130/"


def test_format_detection(now):
    now(2024, 6, 15, 12, 0)
    assert (
        Timestamp.from_bytes(b"151130z").timestamp_format
        is TimestampFormat.DayHoursMinutesZulu
    )
    assert (
        Timestamp.from_bytes(b"113045h").timestamp_format
        is TimestampFormat.HoursMinutesSecondsZulu
    )
    assert (
        Timestamp.from_bytes(b"06151130").timestamp_format
        is TimestampFormat.MonthDayHoursMinutesZulu
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"1511",
        b"151130",  # no indicator
        b"151130x",  # unknown indicator
        b"hello w",
        b"hello wo",
        b" 51130z",
        b"+51130z",
        b"001130z",  # day 0
        b"321130z",  # day 32
        b"152430z",  # hour 24
        b"151160z",  # minute 60
        b"246060h",
        b"13151130",  # month 13
        b"02301200",  # Feb 30
    ],
)
def test_invalid(now, raw):
    now(2024, 6, 15, 12, 0)
    with pytest.raises(ValueError):
        Timestamp.from_bytes(raw)


def test_default_is_now_zulu():
    ts = Timestamp()
    assert ts.timestamp_format is TimestampFormat.DayHoursMinutesZulu
    assert ts.timestamp.tzinfo is UTC
    assert (datetime.datetime.now(UTC) - ts.timestamp) < datetime.timedelta(seconds=5)
