"""Represent various position formats"""

import math
import re
from decimal import Decimal

from attrs import define, field

from .base91 import from_decimal, to_decimal
from .constants import PositionFormat
from .data_ext import RNG, CourseSpeed, DataExt
from .decimaldegrees import dm2decimal
from .geo_util import ambiguate, deambiguate, dec2dm_lat, dec2dm_lng

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


POSITION_UNCOMPRESSED_SIGNATURE = tuple("0123456789")
# APRS101 p26: "/A=aaaaaa", 6 digits, or "-" and 5 digits when negative
ALTITUDE_REX = re.compile(rb"/A=(-[0-9]{5}|[0-9]{6})")
# Minutes to add to an ambiguous position to place it in the middle of its box,
# by ambiguity level (APRS101 p24: 1 to 4 trailing digits replaced by spaces)
AMBIGUITY_CENTER_MINUTES = (
    Decimal(0),
    Decimal("0.05"),
    Decimal("0.5"),
    Decimal(5),
    Decimal(30),
)


def _decode_dm(text: str, degree_digits: int) -> Decimal:
    """
    Decode "DDMM.mm" or "DDDMM.mm", where trailing digits may be blanked.

    Blanked digits are centred in their range; digits that were sent are kept.
    """
    unblanked = text.replace(" ", "0")
    if not re.fullmatch(r"[0-9]{%d}[0-9]{2}\.[0-9]{2}" % degree_digits, unblanked):
        raise ValueError(f"{text!r} is not a valid coordinate")
    ambiguity = text.count(" ")
    if ambiguity > 4 or ambiguate(unblanked.encode("ascii"), ambiguity) != text.encode(
        "ascii"
    ):
        raise ValueError(f"{text!r}: only up to 4 trailing digits may be blanked")
    degrees = int(unblanked[:degree_digits])
    minutes = Decimal(unblanked[degree_digits:])
    max_degrees = 90 if degree_digits == 2 else 180
    if minutes >= 60 or degrees > max_degrees or (degrees == max_degrees and minutes):
        raise ValueError(f"{text!r} is out of range")
    return dm2decimal(degrees, minutes + AMBIGUITY_CENTER_MINUTES[ambiguity])


def decode_position_uncompressed(data: bytes):
    """
    :return: dict with keys lat, long, sym_table_id, symbol_code, ambiguity,
        and long_ambiguity when the longitude has a different number of
        blanked digits than the latitude

    An ambiguous position (APRS101 p24) is placed in the middle of its box.
    Only blanked digits are centred, so a longitude sent with more precision
    than the latitude keeps it.
    """
    text = data.decode("latin1")
    if len(text) < 19 or not text.startswith(POSITION_UNCOMPRESSED_SIGNATURE):
        raise ValueError(f"{data[:19]!r} is not an uncompressed position")
    lat_text, lat_hemisphere = text[:7], text[7:8]
    long_text, long_hemisphere = text[9:17], text[17:18]
    if lat_hemisphere not in ("N", "S") or long_hemisphere not in ("E", "W"):
        raise ValueError(f"{data[:19]!r} is not an uncompressed position")
    lat = _decode_dm(lat_text, 2) * (-1 if lat_hemisphere == "S" else 1)
    long = _decode_dm(long_text, 3) * (-1 if long_hemisphere == "W" else 1)
    # APRS101 p24: the latitude sets the ambiguity
    ambiguity = deambiguate(lat_text.encode("ascii"))
    long_ambiguity = deambiguate(long_text.encode("ascii"))
    extra = {} if long_ambiguity == ambiguity else {"long_ambiguity": long_ambiguity}
    return dict(
        lat=lat,
        sym_table_id=data[8:9],
        long=long,
        symbol_code=data[18:19],
        ambiguity=ambiguity,
        **extra,
    )


def encode_position_uncompressed(
    lat,
    long,
    sym_table_id,
    symbol_code,
    ambiguity=None,
    long_ambiguity=None,
) -> bytes:
    if long_ambiguity is None:
        long_ambiguity = ambiguity
    return b"".join(
        [
            ambiguate(dec2dm_lat(lat), ambiguity),
            sym_table_id,
            ambiguate(dec2dm_lng(long), long_ambiguity),
            symbol_code,
        ]
    )


def decompress_lat(data: str) -> float:
    return 90 - to_decimal(data) / 380926


def compress_lat(data: float) -> bytes:
    return from_decimal(int(round(380926 * (90 - data))), width=4).encode("ascii")


def decompress_long(data: str) -> float:
    return -180 + to_decimal(data) / 190463


def compress_long(data: float) -> bytes:
    return from_decimal(int(round(190463 * (180 + data))), width=4).encode("ascii")


def decode_position_compressed(data: bytes):
    """
    :return: dict with keys lat, long, sym_table_id, symbol_code, data_ext,
        and altitude_ft when the cs bytes hold an altitude
    """
    if len(data) < 13 or chr(data[0]) in POSITION_UNCOMPRESSED_SIGNATURE:
        raise ValueError(f"{data[:13]!r} is not a compressed position")
    text = data.decode("latin1")
    sym_table_id = data[0:1]
    lat = Decimal(str(decompress_lat(text[1:5])))
    long = Decimal(str(decompress_long(text[5:9])))
    symbol_code = data[9:10]
    c_ext = text[10:12]
    comp_type = data[12] - 33
    init_kwargs = {}
    data_ext = b""

    # APRS101 p38-40: a space in c means no course/speed, range or altitude,
    # and s is ignored (but kept so the position re-encodes unchanged)
    if c_ext[0] == " ":
        if c_ext != "  ":
            init_kwargs["ignored_cs"] = data[10:12]
    else:
        if (comp_type >> 3) & 0b11 == 0b10:
            # GGA source: cs is an altitude
            init_kwargs["altitude_ft"] = 1.002 ** to_decimal(c_ext)
        elif c_ext[0] == "{":
            data_ext = RNG(range=2 * 1.08 ** to_decimal(c_ext[1]))
        else:
            data_ext = CourseSpeed(
                course=to_decimal(c_ext[0]) * 4, speed=1.08 ** to_decimal(c_ext[1]) - 1
            )

    return dict(
        sym_table_id=sym_table_id,
        lat=lat,
        long=long,
        symbol_code=symbol_code,
        data_ext=data_ext,
        compression_type=comp_type,
        **init_kwargs,
    )


# Compression type bytes used when encoding a Position that wasn't decoded:
# current GPS fix, compressed origin; GGA source when cs holds an altitude
COMPRESSION_TYPE_DEFAULT = ord("#") - 33
COMPRESSION_TYPE_ALTITUDE = ord("S") - 33


def _encode_cs(data_ext, altitude_ft, ignored_cs=None) -> bytes:
    if isinstance(data_ext, CourseSpeed):
        return (
            # 360 (due north) is code 0: code 90 ("{") marks a range
            from_decimal(int(data_ext.course) % 360 // 4, 1)
            + from_decimal(int(round(math.log(data_ext.speed + 1, 1.08))), 1)
        ).encode("ascii")
    if isinstance(data_ext, RNG):
        return b"{" + from_decimal(
            int(round(math.log(data_ext.range / 2, 1.08))), 1
        ).encode("ascii")
    if altitude_ft is not None:
        if altitude_ft <= 0:
            # 1.002**c cannot produce 0 (or a negative value); encode the
            # lowest valid code instead of failing on math.log()'s domain error
            return from_decimal(0, 2).encode("ascii")
        return from_decimal(int(round(math.log(altitude_ft, 1.002))), 2).encode("ascii")
    return ignored_cs or b"  "


def encode_position_compressed(  # pylint: disable=too-many-arguments
    lat,
    long,
    sym_table_id,
    symbol_code,
    ambiguity=None,  # pylint: disable=unused-argument
    data_ext=None,
    altitude_ft=None,
    compression_type=None,
    ignored_cs=None,
) -> bytes:
    if compression_type is None:
        compression_type = (
            COMPRESSION_TYPE_ALTITUDE
            if altitude_ft is not None and not data_ext
            else COMPRESSION_TYPE_DEFAULT
        )
    return b"".join(
        [
            sym_table_id,
            compress_lat(lat),
            compress_long(long),
            symbol_code,
            _encode_cs(data_ext, altitude_ft, ignored_cs),
            bytes([compression_type + 33]),
        ]
    )


def _in_range(limit):
    def validator(instance, attribute, value):
        if not -limit <= value <= limit:
            raise ValueError(f"{attribute.name} must be within ±{limit}, got {value!r}")

    return validator


@define(frozen=True, slots=True)
class Position:
    """Represents a position including any data extension."""

    position_format: PositionFormat = field(default=PositionFormat.Uncompressed)
    lat: float = field(default=0.0, validator=_in_range(90))
    sym_table_id: bytes = field(default=b"/")
    long: float = field(default=0.0, validator=_in_range(180))
    symbol_code: bytes = field(default=b"-")
    altitude_ft: int | None = field(default=None)
    data_ext: bytes | DataExt = field(default=b"")
    ambiguity: int = field(default=0)
    """Uncompressed only: how many trailing digits are blanked (0-4)."""
    long_ambiguity: int | None = field(default=None)
    """
    Uncompressed only: blanked longitude digits, when they differ from the
    latitude's; None means the same as ambiguity.
    """
    compression_type: int | None = field(default=None)
    """Compressed only: the type byte (minus 33); None picks a default."""
    ignored_cs: bytes | None = field(default=None)
    """Compressed only: cs bytes starting with a space, which carry no data."""

    @classmethod
    def from_bytes_with_data_and_remainder(
        cls, raw: bytes
    ) -> tuple["Position", bytes, bytes]:
        """
        Create a Position from raw packet bytes.

        :return: a Position and remaining bytes, which may be any unparsed
            extended data or comments.
        """
        try:
            (
                position_format,
                position,
            ) = PositionFormat.Uncompressed, decode_position_uncompressed(raw[:19])
            data, remainder = raw[:19], raw[19:]
        except ValueError:
            try:
                (
                    position_format,
                    position,
                ) = PositionFormat.Compressed, decode_position_compressed(raw[:13])
                data, remainder = raw[:13], raw[13:]
            except ValueError:  # pylint: disable=try-except-raise
                # eventually we may try to decode other position types here
                raise
        # try to decode extended data; a compressed position carries
        # course/speed or range in its cs bytes (APRS101 p36), so text after
        # it (e.g. an igate's PHG) stays in the comment
        data_ext = b""
        if position_format is PositionFormat.Uncompressed:
            data_ext, remainder = DataExt.split_parse(remainder)
        # try to find the altitude comment
        alt_match = ALTITUDE_REX.search(remainder)
        if alt_match and "altitude_ft" not in position:
            # a compressed altitude (in cs) takes precedence
            position["altitude_ft"] = int(alt_match.group(1))
        return (
            cls(
                position_format=position_format,
                data_ext=data_ext or position.pop("data_ext", b""),
                **position,
            ),
            data,
            remainder,
        )

    def __bytes__(self) -> bytes:
        if self.position_format is PositionFormat.Uncompressed:
            return b"".join(
                [
                    encode_position_uncompressed(
                        self.lat,
                        self.long,
                        self.sym_table_id,
                        self.symbol_code,
                        ambiguity=self.ambiguity,
                        long_ambiguity=self.long_ambiguity,
                    ),
                    bytes(self.data_ext),
                ]
            )
        if self.position_format is PositionFormat.Compressed:
            return encode_position_compressed(
                self.lat,
                self.long,
                self.sym_table_id,
                self.symbol_code,
                data_ext=self.data_ext,
                altitude_ft=self.altitude_ft,
                compression_type=self.compression_type,
                ignored_cs=self.ignored_cs,
            )
        raise ValueError(f"Unknown position format: {self.position_format!r}")


# pylint: disable=no-member,inconsistent-return-statements
class PositionMixin:
    _position: Position | None = field(default=None)

    @property
    def lat(self) -> float | None:
        if self._position:
            return self._position.lat

    @property
    def long(self) -> float | None:
        if self._position:
            return self._position.long

    @property
    def sym_table_id(self) -> bytes | None:
        if self._position:
            return self._position.sym_table_id

    @property
    def symbol_code(self) -> bytes | None:
        if self._position:
            return self._position.symbol_code

    @property
    def altitude_ft(self) -> int | None:
        if self._position:
            return self._position.altitude_ft

    @property
    def data_ext(self) -> DataExt | bytes:
        if self._position:
            return self._position.data_ext
        return b""

    def format_altitude(self) -> bytes:
        """The "/A=" comment for altitude_ft, unless it's already encoded."""
        position = self._position
        if (
            position is not None
            and position.position_format is PositionFormat.Compressed
            and not position.data_ext
        ):
            return b""  # carried in the compressed cs bytes
        if self.altitude_ft is not None and not ALTITUDE_REX.search(
            getattr(self, "comment", b"")
        ):
            return b"/A=%06d" % self.altitude_ft
        return b""
