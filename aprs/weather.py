"""Weather reports (APRS101 ch. 12): positionless ``_`` reports and weather in comments."""

import re
from decimal import Decimal

from attrs import define, field

from .classes import DataType, DataTypeError, InformationField
from .constants import TimestampFormat
from .data_ext import CourseSpeed
from .timestamp import Timestamp, TimestampMixin

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2026 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"

# weather field code -> width of its value
WIDTHS = {
    "c": 3,  # wind direction, degrees
    "s": 3,  # wind speed, mph (snowfall when wind speed is already given)
    "g": 3,  # gust, mph
    "t": 3,  # temperature, deg F
    "r": 3,  # rain in the last hour, 1/100 in
    "p": 3,  # rain in the last 24 hours, 1/100 in
    "P": 3,  # rain since midnight, 1/100 in
    "h": 2,  # humidity, % (00 is 100%)
    "b": 5,  # barometric pressure, 1/10 mbar
    "L": 3,  # luminosity, W/m2 (0-999)
    "l": 3,  # luminosity, W/m2 minus 1000
    "#": 3,  # raw rain counter
}
SNOW = "snow"
"""Key used for the second "s" field (snowfall in the last 24 hours, in)."""
_VALUE = {
    width: re.compile(
        rb"[0-9]{%d}|-[0-9]{%d}|\.{%d}| {%d}" % (width, width - 1, width, width)
    )
    for width in set(WIDTHS.values())
}
_SLASH_WIND = re.compile(rb"([0-9]{3}|\.{3}| {3})/([0-9]{3}|\.{3}| {3})")


def _int(value: bytes | None) -> int | None:
    if value is None or not value.strip(b" .") or not value.lstrip(b"-").isdigit():
        return None
    return int(value)


@define(frozen=True, slots=True)
class Weather:
    """
    Weather values, kept as sent so they re-encode unchanged.

    ``fields`` are ``(code, value)`` pairs in the order received; a missing
    value is sent as dots or spaces and reads as None. The typed properties
    convert to the units in their names.

    >>> wx, rest = Weather.from_bytes(b"c220s004g005t077r000p000P000h50b09900wRSW")
    >>> wx.wind_direction, wx.wind_speed_mph, wx.temperature_f, wx.humidity
    (220, 4, 77, 50)
    >>> wx.pressure_mbar, rest
    (Decimal('990.0'), b'wRSW')
    """

    fields: tuple[tuple[str, bytes], ...] = field(
        default=(), converter=lambda v: tuple((k, val) for k, val in v)
    )
    slash_wind: bool = field(default=False)
    """Wind is sent first as ``ddd/sss`` (weather after a position), not ``c..s..``."""

    @classmethod
    def from_bytes(cls, data: bytes, slash_wind: bool = False) -> tuple["Weather", bytes]:
        """
        Parse weather fields from the start of ``data``.

        :param slash_wind: accept a leading ``ddd/sss`` wind direction/speed
            (weather after a position)
        :return: the weather and the rest of ``data`` (software and station
            type, comment)
        """
        fields: list[tuple[str, bytes]] = []
        pos = 0
        found_slash = False
        if slash_wind:
            match = _SLASH_WIND.match(data)
            if match is not None:
                fields += [("c", match.group(1)), ("s", match.group(2))]
                pos, found_slash = match.end(), True
        while pos < len(data):
            code = chr(data[pos])
            width = WIDTHS.get(code)
            if width is None:
                break
            match = _VALUE[width].match(data, pos + 1)
            if match is None:
                break
            key = SNOW if code == "s" and any(k == "s" for k, _ in fields) else code
            fields.append((key, match.group()))
            pos = match.end()
        return cls(fields, slash_wind=found_slash), data[pos:]

    @classmethod
    def new(  # pylint: disable=too-many-arguments
        cls,
        *,
        wind_direction: int | None = None,
        wind_speed_mph: float | None = None,
        wind_gust_mph: float | None = None,
        temperature_f: float | None = None,
        rain_1h_in: float | None = None,
        rain_24h_in: float | None = None,
        rain_since_midnight_in: float | None = None,
        humidity: int | None = None,
        pressure_mbar: float | None = None,
        luminosity_wm2: int | None = None,
        snow_24h_in: float | None = None,
        slash_wind: bool = False,
    ) -> "Weather":
        """
        Build weather to send. Wind direction, speed, gust and temperature are
        always sent (as dots when unknown); other values only when given.

        Use ``slash_wind=True`` for weather after a position with the ``_``
        symbol: the comment then starts with ``ddd/sss``.

        >>> bytes(Weather.new(temperature_f=-5, humidity=100, pressure_mbar=1013.2))
        b'c...s...g...t-05h00b10132'
        """

        def num(value: float | None, width: int, scale: float = 1) -> bytes:
            if value is None:
                return b"." * width
            scaled = int(round(value * scale))
            if scaled < 0:
                return b"-%0*d" % (width - 1, -scaled)
            return b"%0*d" % (width, scaled)

        fields = [
            ("c", num(wind_direction, 3)),
            ("s", num(wind_speed_mph, 3)),
            ("g", num(wind_gust_mph, 3)),
            ("t", num(temperature_f, 3)),
        ]
        optional = [
            ("r", rain_1h_in, 3, 100),
            ("p", rain_24h_in, 3, 100),
            ("P", rain_since_midnight_in, 3, 100),
            ("h", None if humidity is None else humidity % 100, 2, 1),
            ("b", pressure_mbar, 5, 10),
        ]
        fields += [(code, num(v, w, k)) for code, v, w, k in optional if v is not None]
        if luminosity_wm2 is not None:
            if luminosity_wm2 >= 1000:
                fields.append(("l", num(luminosity_wm2 - 1000, 3)))
            else:
                fields.append(("L", num(luminosity_wm2, 3)))
        if snow_24h_in is not None:
            fields.append((SNOW, num(snow_24h_in, 3)))
        return cls(fields, slash_wind=slash_wind)

    def __bytes__(self) -> bytes:
        fields = list(self.fields)
        head = b""
        if self.slash_wind:
            values = dict(fields)
            head = values.get("c", b"...") + b"/" + values.get("s", b"...")
            fields = [(k, v) for k, v in fields if k not in ("c", "s")]
        return head + b"".join(
            (b"s" if k == SNOW else k.encode("ascii")) + v for k, v in fields
        )

    def __bool__(self) -> bool:
        return bool(self.fields)

    def _get(self, code: str) -> bytes | None:
        for key, value in self.fields:
            if key == code:
                return value
        return None

    @property
    def wind_direction(self) -> int | None:
        """Degrees the wind blows from."""
        return _int(self._get("c"))

    @property
    def wind_speed_mph(self) -> int | None:
        """Sustained one-minute wind speed."""
        return _int(self._get("s"))

    @property
    def wind_gust_mph(self) -> int | None:
        """Peak wind speed in the last 5 minutes."""
        return _int(self._get("g"))

    @property
    def temperature_f(self) -> int | None:
        return _int(self._get("t"))

    @property
    def temperature_c(self) -> float | None:
        fahrenheit = self.temperature_f
        return None if fahrenheit is None else (fahrenheit - 32) * 5 / 9

    def _hundredths(self, code: str) -> Decimal | None:
        value = _int(self._get(code))
        return None if value is None else Decimal(value).scaleb(-2)

    @property
    def rain_1h_in(self) -> Decimal | None:
        """Rain in the last hour, inches."""
        return self._hundredths("r")

    @property
    def rain_24h_in(self) -> Decimal | None:
        """Rain in the last 24 hours, inches."""
        return self._hundredths("p")

    @property
    def rain_since_midnight_in(self) -> Decimal | None:
        """Rain since local midnight, inches."""
        return self._hundredths("P")

    @property
    def humidity(self) -> int | None:
        """Relative humidity, percent ("00" is 100%)."""
        value = _int(self._get("h"))
        return 100 if value == 0 else value

    @property
    def pressure_mbar(self) -> Decimal | None:
        """Barometric pressure, millibars (hPa)."""
        value = _int(self._get("b"))
        return None if value is None else Decimal(value).scaleb(-1)

    @property
    def luminosity_wm2(self) -> int | None:
        """Solar radiation, W/m2."""
        low, high = _int(self._get("L")), _int(self._get("l"))
        if high is not None:
            return high + 1000
        return low

    @property
    def snow_24h_in(self) -> int | None:
        """Snowfall in the last 24 hours, inches."""
        return _int(self._get(SNOW))

    @property
    def rain_counter(self) -> int | None:
        """The raw rain counter (#)."""
        return _int(self._get("#"))


def weather_from_comment(comment: bytes, wind: object = None) -> Weather | None:
    """
    The weather after a position with the ``_`` (weather station) symbol.

    :param wind: the position's data extension; a ``CourseSpeed`` there is
        the wind direction and speed (for a compressed position, the speed
        decoded from its cs bytes, rounded)
    """
    if isinstance(wind, CourseSpeed):
        weather, _ = Weather.from_bytes(comment)
        fields = [
            ("c", b"%03d" % wind.course),
            ("s", b"%03d" % round(wind.speed)),
            *weather.fields,
        ]
        return Weather(fields, slash_wind=True)
    weather, _ = Weather.from_bytes(comment, slash_wind=True)
    return weather or None


@define(frozen=True, slots=True)
class WeatherReport(InformationField, TimestampMixin):
    """
    A positionless weather report: ``_`` + MDHM timestamp + weather
    (APRS101 p. 63). The text after the weather fields (software and unit
    type, e.g. ``wRSW``) is the comment.
    """

    _timestamp: Timestamp | None = field(default=None, alias="timestamp")
    weather: Weather = field(factory=Weather)

    __data_type__ = [DataType.WEATHER_REPORT_W_O_POSITION]
    __raw_fallback__ = True

    @classmethod
    def from_bytes(cls, raw: bytes) -> "WeatherReport":
        data_type = DataType(raw[0:1])
        if data_type not in cls.__data_type__:
            raise DataTypeError(
                f"{data_type!r} cannot be handled by {cls!r} (expecting {cls.__data_type__!r})",
            )
        if not raw[1:9].isdigit():
            raise ValueError(f"{raw!r}: weather report without an MDHM timestamp")
        timestamp = Timestamp.from_bytes(raw[1:9])
        weather, comment = Weather.from_bytes(raw[9:])
        if not weather:
            raise ValueError(f"{raw!r}: no weather fields")
        return cls(
            raw=raw,
            data_type=data_type,
            data=raw[: len(raw) - len(comment)],
            timestamp=timestamp,
            weather=weather,
            comment=comment,
        )._keep_source(raw)

    def __bytes__(self) -> bytes:
        if self._source is not None:
            return self._source
        timestamp = self._timestamp or Timestamp(
            timestamp_format=TimestampFormat.MonthDayHoursMinutesZulu
        )
        return b"_" + bytes(timestamp) + bytes(self.weather) + self.comment
