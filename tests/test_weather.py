"""Weather reports (#28)."""

import datetime
from decimal import Decimal

import attrs
import pytest

from aprs import APRSFrame, DataType, Position, PositionReport, Weather, WeatherReport


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch):
    monkeypatch.setattr(
        "aprs.timestamp._now",
        lambda tz: datetime.datetime(2024, 11, 15, 12, 0, tzinfo=tz),
    )


def info(tnc2: str):
    return APRSFrame.from_str(tnc2).info


def test_positionless_weather():
    report = info("N0CALL>APRS:_10090556c220s004g005t077r000p000P000h50b09900wRSW")
    assert isinstance(report, WeatherReport)
    assert report.timestamp == datetime.datetime(2024, 10, 9, 5, 56, tzinfo=datetime.UTC)
    wx = report.weather
    assert (wx.wind_direction, wx.wind_speed_mph, wx.wind_gust_mph) == (220, 4, 5)
    assert (wx.temperature_f, round(wx.temperature_c, 1)) == (77, 25.0)
    assert (wx.rain_1h_in, wx.rain_24h_in, wx.rain_since_midnight_in) == (0, 0, 0)
    assert (wx.humidity, wx.pressure_mbar) == (50, Decimal("990.0"))
    assert report.comment == b"wRSW"
    assert bytes(attrs.evolve(report)) == report.raw


def test_missing_and_extra_values():
    wx = info("N0CALL>APRS:_10090556c...s...g...t-05h00b10132L456").weather
    assert (wx.wind_direction, wx.wind_speed_mph, wx.wind_gust_mph) == (None, None, None)
    assert (wx.temperature_f, wx.humidity, wx.luminosity_wm2) == (-5, 100, 456)
    assert wx.temperature_c == pytest.approx(-20.56, abs=0.01)
    wx = info("N0CALL>APRS:_10090556c   s   g   t   wRSW").weather
    assert wx.temperature_f is None and wx.temperature_c is None
    assert wx.pressure_mbar is None and wx.rain_1h_in is None and wx.humidity is None
    wx = info(
        "N0CALL>APRS:_10090556c220s004g005t077r000p000P000h50b09900l012s003#123xDvs"
    ).weather
    assert (wx.luminosity_wm2, wx.snow_24h_in, wx.rain_counter) == (1012, 3, 123)


@pytest.mark.parametrize("text", ["_10090556no weather here", "_1009"])
def test_not_weather_stays_raw(text):
    field = info(f"N0CALL>APRS:{text}")
    assert type(field) is not WeatherReport
    assert field.data_type is DataType.WEATHER_REPORT_W_O_POSITION


def test_position_weather():
    report = info(
        "N0CALL>APRS:@092345z4903.50N/07201.75W_220/004g005t077r000p000P000h50b09900wRSW"
    )
    wx = report.weather
    assert (wx.wind_direction, wx.wind_speed_mph, wx.temperature_f) == (220, 4, 77)
    assert bytes(wx) == b"220/004g005t077r000p000P000h50b09900"


def test_position_weather_without_wind():
    report = info("N0CALL>APRS:!4903.50N/07201.75W_.../...g...t-05h00b10132 comment")
    wx = report.weather
    assert (wx.wind_direction, wx.temperature_f, wx.pressure_mbar) == (
        None,
        -5,
        Decimal("1013.2"),
    )


def test_compressed_position_weather():
    wx = info("N0CALL>APRS:=/5L!!<*e7_7P[g005t077r000p000P000h50b09900wRSW").weather
    assert (wx.wind_direction, wx.wind_speed_mph, wx.wind_gust_mph) == (88, 36, 5)


def test_object_weather():
    wx = info("N0CALL>APRS:;WX-SITE  *092345z4903.50N/07201.75W_220/004g005t077").weather
    assert wx.temperature_f == 77


def test_no_weather_for_other_symbols():
    assert info("N0CALL>APRS:!4903.50N/07201.75W-t077").weather is None
    assert info("N0CALL>APRS:!4903.50N/07201.75W_ just a comment").weather is None


def test_build_positionless_weather():
    wx = Weather.new(
        wind_direction=90,
        wind_speed_mph=5,
        wind_gust_mph=12,
        temperature_f=68.4,
        rain_1h_in=0.12,
        rain_24h_in=1.5,
        rain_since_midnight_in=0.5,
        humidity=45,
        pressure_mbar=1013.25,
        luminosity_wm2=1200,
        snow_24h_in=2,
    )
    assert bytes(wx) == b"c090s005g012t068r012p150P050h45b10132l200s002"
    report = WeatherReport(
        raw=b"",
        data_type=DataType.WEATHER_REPORT_W_O_POSITION,
        data=b"",
        timestamp=None,
        weather=wx,
        comment=b"xPYT",
    )
    encoded = bytes(report)
    assert encoded.startswith(b"_") and encoded.endswith(b"l200s002xPYT")
    decoded = info("N0CALL>APRS:" + encoded.decode())
    assert isinstance(decoded, WeatherReport)
    assert decoded.weather == wx
    assert decoded.weather.luminosity_wm2 == 1200
    assert Weather.new(luminosity_wm2=999).luminosity_wm2 == 999


def test_build_position_weather():
    wx = Weather.new(
        wind_direction=270, wind_speed_mph=3, temperature_f=50, slash_wind=True
    )
    report = PositionReport(
        raw=b"",
        data=b"",
        data_type=DataType.POSITION_W_O_TIMESTAMP,
        position=Position(lat=49.0583, long=-72.0292, symbol_code=b"_"),
        comment=bytes(wx) + b"Davis",
    )
    assert bytes(report) == b"!4903.50N/07201.75W_270/003g...t050Davis"
    decoded = info("N0CALL>APRS:" + bytes(report).decode())
    assert decoded.weather == wx
