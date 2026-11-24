"""Mic-E position reports (APRS101 ch. 10), as most Kenwood and Yaesu radios send."""

import re
from decimal import Decimal

from attrs import define, field

from .base91 import from_decimal, to_decimal
from .classes import MIC_E_DATA_TYPES, DataType, DataTypeError, InformationField
from .data_ext import CourseSpeed
from .geo_util import ambiguate
from .position import Position, PositionMixin, _decode_dm

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2026 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"

FEET_PER_METRE = 3.28084

MESSAGES = {
    "M0": "Off Duty",
    "M1": "En Route",
    "M2": "In Service",
    "M3": "Returning",
    "M4": "Committed",
    "M5": "Special",
    "M6": "Priority",
    "C0": "Custom-0",
    "C1": "Custom-1",
    "C2": "Custom-2",
    "C3": "Custom-3",
    "C4": "Custom-4",
    "C5": "Custom-5",
    "C6": "Custom-6",
    "Emergency": "Emergency",
    "Unknown": "Unknown",
}
"""Mic-E message codes and their names (APRS101 p. 45)."""

TYPE_CODES = (b">", b"]", b"`", b"'")
"""Radio type codes that may start the status text (mic-e types)."""

DEVICES = {
    (b">", b""): "Kenwood TH-D7A",
    (b">", b"="): "Kenwood TH-D72",
    (b">", b"^"): "Kenwood TH-D74",
    (b">", b"&"): "Kenwood TH-D75",
    (b"]", b""): "Kenwood TM-D700",
    (b"]", b"="): "Kenwood TM-D710",
    (b"`", b"_ "): "Yaesu VX-8",
    (b"`", b'_"'): "Yaesu FTM-350",
    (b"`", b"_#"): "Yaesu VX-8G",
    (b"`", b"_$"): "Yaesu FT1D",
    (b"`", b"_%"): "Yaesu FTM-400DR",
    (b"`", b"_)"): "Yaesu FTM-100D",
    (b"`", b"_("): "Yaesu FT2D",
    (b"`", b"_0"): "Yaesu FT3D",
    (b"`", b"_1"): "Yaesu FTM-300D",
    (b"`", b"_3"): "Yaesu FT5D",
    (b"`", b"_5"): "Yaesu FTM-500D",
    (b"'", b"|3"): "Byonics TinyTrak3",
    (b"'", b"|4"): "Byonics TinyTrak4",
}
"""Known (type code, suffix) pairs; the suffix ends the status text."""

ALTITUDE = re.compile(rb"([!-{]{3})\}")
DESTINATION = re.compile(rb"[0-9A-LP-Z]{3}[0-9LP-Z]{3}")


def _dest_char(char: int) -> tuple[str, int, str]:
    """A destination byte as (digit or " ", 0 or 1, "std"/"custom"/"")."""
    c = chr(char)
    if "0" <= c <= "9":
        return c, 0, ""
    if "A" <= c <= "J":
        return str(ord(c) - ord("A")), 1, "custom"
    if c == "K":
        return " ", 1, "custom"
    if c == "L":
        return " ", 0, ""
    if "P" <= c <= "Y":
        return str(ord(c) - ord("P")), 1, "std"
    if c == "Z":
        return " ", 1, "std"
    raise ValueError(f"{c!r} is not a Mic-E destination character")


def _message_code(bits: list[tuple[int, str]]) -> str:
    kinds = {kind for bit, kind in bits if bit}
    value = sum(bit << (2 - ix) for ix, (bit, _) in enumerate(bits))
    if value == 0:
        return "Emergency"
    if len(kinds) > 1:
        return "Unknown"
    return ("C" if kinds == {"custom"} else "M") + str(7 - value)


def decode_destination(destination: bytes) -> dict:
    """
    Decode a Mic-E destination address (the callsign, without SSID).

    :return: dict with lat (Decimal), ambiguity, message, long_offset
        (True: add 100 to the longitude degrees) and west (bool)
    """
    callsign = destination.upper()
    if not DESTINATION.fullmatch(callsign):
        raise ValueError(f"{destination!r} is not a Mic-E destination address")
    decoded = [_dest_char(c) for c in callsign]
    lat_text = "".join(d for d, _, _ in decoded)
    lat_text = f"{lat_text[:4]}.{lat_text[4:]}"
    lat = _decode_dm(lat_text, 2)
    flags = [bit for _, bit, _ in decoded[3:]]
    return dict(
        lat=lat if flags[0] else -lat,
        ambiguity=lat_text.count(" "),
        message=_message_code([(bit, kind) for _, bit, kind in decoded[:3]]),
        long_offset=bool(flags[1]),
        west=bool(flags[2]),
    )


def encode_destination(
    lat: float | Decimal, long: float | Decimal, message: str = "M0", ambiguity: int = 0
) -> bytes:
    """
    The destination address carrying a Mic-E latitude, message and
    longitude flags.

    >>> encode_destination(33.4273, -112.1295, "M3")
    b'S32UVT'
    """
    if message not in MESSAGES or message == "Unknown":
        raise ValueError(f"{message!r} is not a Mic-E message code")
    lat_dec = Decimal(str(lat))
    whole = abs(lat_dec)
    degrees = int(whole)
    hundredths = int(round((whole - degrees) * 60 * 100))
    if hundredths == 6000:
        degrees, hundredths = degrees + 1, 0
    digits = ambiguate(b"%02d%04d" % (degrees, hundredths), ambiguity).decode("ascii")
    if message == "Emergency":
        bits, kind = (0, 0, 0), "std"
    else:
        value = 7 - int(message[1])
        bits = (value >> 2 & 1, value >> 1 & 1, value & 1)
        kind = "custom" if message[0] == "C" else "std"
    long_degrees = int(abs(Decimal(str(long))))
    flags = (
        lat_dec >= 0,
        long_degrees < 10 or long_degrees >= 100,
        Decimal(str(long)) < 0,
    )
    out = []
    for ix, digit in enumerate(digits):
        bit = bits[ix] if ix < 3 else int(flags[ix - 3])
        style = kind if ix < 3 else "std"
        if not bit:
            out.append("L" if digit == " " else digit)
        elif style == "custom":
            out.append("K" if digit == " " else chr(ord("A") + int(digit)))
        else:
            out.append("Z" if digit == " " else chr(ord("P") + int(digit)))
    return "".join(out).encode("ascii")


def _decode_longitude(
    info: bytes, long_offset: bool, west: bool, ambiguity: int
) -> Decimal:
    degrees = info[0] - 28 + (100 if long_offset else 0)
    if 180 <= degrees <= 189:
        degrees -= 80
    elif 190 <= degrees <= 199:
        degrees -= 190
    minutes = info[1] - 28
    if minutes >= 60:
        minutes -= 60
    hundredths = info[2] - 28
    if not (0 <= degrees <= 179 and 0 <= minutes <= 59 and 0 <= hundredths <= 99):
        raise ValueError(f"{info[:3]!r} is not a Mic-E longitude")
    text = ambiguate(b"%03d%02d.%02d" % (degrees, minutes, hundredths), ambiguity)
    long = _decode_dm(text.decode("ascii"), 3)
    return -long if west else long


def _encode_longitude(long: float | Decimal) -> bytes:
    whole = abs(Decimal(str(long)))
    degrees = int(whole)
    hundredths = int(round((whole - degrees) * 6000))
    if hundredths == 6000:
        degrees, hundredths = degrees + 1, 0
    minutes, hundredths = divmod(hundredths, 100)
    if degrees < 10:
        d = degrees + 118
    elif degrees < 100:
        d = degrees + 28
    elif degrees < 110:
        d = degrees + 8
    else:
        d = degrees - 72
    m = minutes + 88 if minutes < 10 else minutes + 28
    return bytes([d, m, hundredths + 28])


def _decode_speed_course(info: bytes) -> tuple[int, int]:
    sp, dc, se = (b - 28 for b in info[:3])
    speed = sp * 10 + dc // 10
    course = (dc % 10) * 100 + se
    if speed >= 800:
        speed -= 800
    if course >= 400:
        course -= 400
    if not (0 <= speed < 800 and 0 <= course <= 360):
        raise ValueError(f"{info[:3]!r} is not a Mic-E speed and course")
    return speed, course


def _encode_speed_course(speed: float, course: int) -> bytes:
    speed = int(round(speed))
    if not 0 <= speed < 800:
        raise ValueError(f"Mic-E speed must be 0-799 knots, got {speed!r}")
    sp, units = divmod(speed, 10)
    if sp < 20:
        sp += 80  # printable, like Kenwood radios
    hundreds, rest = divmod(int(course), 100)
    dc = units * 10 + hundreds
    if dc < 4:
        dc += 4  # course + 400: printable
    return bytes([sp + 28, dc + 28, rest + 28])


@define(frozen=True, slots=True, kw_only=True)
class MicEReport(InformationField, PositionMixin):
    """
    A Mic-E position report (APRS101 ch. 10).

    The latitude, message code and longitude flags travel in the frame's
    destination address, so decode the whole frame (``APRSFrame``), not
    just the info field. To send one, use ``destination`` as the frame's
    destination::

        report = MicEReport.new(lat=33.4273, long=-112.1295, symbol_code=b">")
        frame = APRSFrame.ui(
            destination=report.destination, source="N0CALL", path=["WIDE1-1"], info=report
        )
    """

    __match_args__ = ("lat", "long")

    _position: Position | None = field(default=None, alias="position")
    message: str = field(default="M0")
    """Message code: M0-M6, C0-C6, Emergency (or Unknown); see ``message_text``."""
    type_code: bytes = field(default=b"")
    """Radio type code starting the status text (b">", b"]", b"`", b"'") or b""."""
    altitude_m: int | None = field(default=None)
    device_suffix: bytes = field(default=b"")
    """The radio's suffix ending the status text, e.g. b"_%" (FTM-400DR)."""

    __data_type__ = sorted(MIC_E_DATA_TYPES, key=lambda d: d.value)
    __raw_fallback__ = True

    def default_data_type(self) -> DataType:
        """Current Mic-E (`````)."""
        return DataType.CURRENT_MIC_E_DATA_2

    @classmethod
    def new(  # pylint: disable=too-many-arguments
        cls,
        lat: float | Decimal,
        long: float | Decimal,
        symbol_code: bytes = b">",
        sym_table_id: bytes = b"/",
        speed: float = 0,
        course: int = 0,
        message: str = "M0",
        altitude_m: int | None = None,
        comment: bytes = b"",
        ambiguity: int = 0,
    ) -> "MicEReport":
        """Build a Mic-E report to send (current Mic-E, data type ``\\```)."""
        return cls(
            raw=b"",
            data_type=DataType.CURRENT_MIC_E_DATA_2,
            data=b"",
            position=Position(
                lat=lat,
                long=long,
                symbol_code=symbol_code,
                sym_table_id=sym_table_id,
                data_ext=CourseSpeed(course=course, speed=speed),
                ambiguity=ambiguity,
            ),
            message=message,
            altitude_m=altitude_m,
            comment=comment,
        )

    @classmethod
    def from_bytes(cls, raw: bytes) -> "MicEReport":
        raise ValueError("Mic-E needs the destination address: decode the APRSFrame")

    @classmethod
    def from_bytes_and_destination(cls, raw: bytes, destination: bytes) -> "MicEReport":
        """Decode Mic-E info bytes with the frame's destination callsign."""
        data_type = DataType(raw[0:1])
        if data_type not in MIC_E_DATA_TYPES:
            raise DataTypeError(f"{data_type!r} is not a Mic-E data type")
        if len(raw) < 9:
            raise ValueError(f"{raw!r} is too short for Mic-E")
        dest = decode_destination(destination)
        long = _decode_longitude(
            raw[1:4], dest["long_offset"], dest["west"], dest["ambiguity"]
        )
        speed, course = _decode_speed_course(raw[4:7])
        status = raw[9:]
        type_code = status[:1] if status[:1] in TYPE_CODES else b""
        status = status[len(type_code) :]
        altitude_m = None
        match = ALTITUDE.match(status)
        if match is not None:
            altitude_m = to_decimal(match.group(1).decode("ascii")) - 10000
            status = status[match.end() :]
        device_suffix = b""
        for (code, suffix), _ in DEVICES.items():
            if suffix and code == type_code and status.endswith(suffix):
                device_suffix, status = suffix, status[: -len(suffix)]
                break
        position = Position(
            lat=dest["lat"],
            long=long,
            symbol_code=raw[7:8],
            sym_table_id=raw[8:9],
            data_ext=CourseSpeed(course=course, speed=speed),
            ambiguity=dest["ambiguity"],
            altitude_ft=None if altitude_m is None else altitude_m * FEET_PER_METRE,
        )
        return cls(
            raw=raw,
            data_type=data_type,
            data=raw[:9],
            position=position,
            message=dest["message"],
            type_code=type_code,
            altitude_m=altitude_m,
            device_suffix=device_suffix,
            comment=status,
        )._keep_source(raw)

    def _required_position(self) -> Position:
        if self._position is None:
            raise ValueError("cannot encode a Mic-E report without a position")
        return self._position

    @property
    def destination(self) -> str:
        """The destination callsign that carries this report's latitude and flags."""
        position = self._required_position()
        return encode_destination(
            position.lat, position.long, self.message, position.ambiguity
        ).decode("ascii")

    @property
    def message_text(self) -> str:
        """The message code's name, e.g. "En Route"."""
        return MESSAGES.get(self.message, "Unknown")

    @property
    def is_emergency(self) -> bool:
        return self.message == "Emergency"

    @property
    def device(self) -> str | None:
        """The radio model, from the type code and suffix, when known."""
        return DEVICES.get((self.type_code, self.device_suffix))

    def __bytes__(self) -> bytes:
        if self._source is not None:
            return self._source
        position = self._required_position()
        data_ext = position.data_ext
        speed, course = (
            (data_ext.speed, data_ext.course)
            if isinstance(data_ext, CourseSpeed)
            else (0, 0)
        )
        altitude = b""
        if self.altitude_m is not None:
            altitude = (
                from_decimal(int(self.altitude_m) + 10000, 3).encode("ascii") + b"}"
            )
        return b"".join(
            [
                self._data_type_id(),
                _encode_longitude(position.long),
                _encode_speed_course(speed, course),
                position.symbol_code,
                position.sym_table_id,
                self.type_code,
                altitude,
                self.comment,
                self.device_suffix,
            ]
        )
