"""Represent various position formats"""
from decimal import Decimal
import math
import re
from typing import Optional, Tuple, Union

from attrs import define, field

from .base91 import from_decimal, to_decimal
from .constants import PositionFormat
from .data_ext import CourseSpeed, DataExt, RNG
from .decimaldegrees import dm2decimal
from .geo_util import ambiguate, dec2dm_lat, dec2dm_lng


__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


POSITION_UNCOMPRESSED_SIGNATURE = tuple(chr(c) for c in range(ord(b"0"), ord(b"9")))
ALTITUDE_REX = re.compile(rb"/A=(-[0-9]+)")


def decode_position_uncompressed(data: bytes):
    """
    :return: dict with keys lat, long, sym_table_id, symbol_code
    """
    text = data.decode("ascii")
    if not text.startswith(POSITION_UNCOMPRESSED_SIGNATURE):
        raise ValueError("{!r} is not an uncompressed position".format(data[:19]))
    lat_degrees = int(text[:2])
    lat_minutes = Decimal(text[2:7])
    lat_sign = -1 if text[7:8] == "S" else 1
    lat = dm2decimal(lat_degrees, lat_minutes) * lat_sign
    sym_table_id = data[8:9]
    long_degrees = int(text[9:12])
    long_minutes = Decimal(text[12:17])
    long_sign = -1 if text[17:18] == "W" else 1
    long = dm2decimal(long_degrees, long_minutes) * long_sign
    symbol_code = data[18:19]
    return dict(
        lat=lat,
        sym_table_id=sym_table_id,
        long=long,
        symbol_code=symbol_code,
    )


def encode_position_uncompressed(
    lat,
    long,
    sym_table_id,
    symbol_code,
    ambiguity=None,
) -> bytes:
    return b"".join(
        [
            ambiguate(dec2dm_lat(lat), ambiguity),
            sym_table_id,
            ambiguate(dec2dm_lng(long), ambiguity),
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
    :return: dict with keys lat, long, sym_table_id, symbol_code, data_ext
    """
    text = data.decode("latin1")
    if chr(data[0]) in POSITION_UNCOMPRESSED_SIGNATURE:
        raise ValueError("{!r} is not a compressed position".format(data[:13]))
    sym_table_id = data[0:1]
    lat = Decimal(str(decompress_lat(text[1:5])))
    long = Decimal(str(decompress_long(text[5:9])))
    symbol_code = data[9:10]
    c_ext = text[10:12]
    comp_type = data[12]
    init_kwargs = {}

    if c_ext[0] == " ":
        data_ext = b""
    else:
        if c_ext[0] == "{":
            data_ext = RNG(range=2 * 1.08 ** to_decimal(c_ext[1]))
        elif ord("!") <= ord(c_ext[0]) <= ord("z"):
            data_ext = CourseSpeed(
                course=to_decimal(c_ext[0]) * 4, speed=1.08 ** to_decimal(c_ext[1]) - 1
            )

        if comp_type % 0b11000 == 0b10000:
            # extract altitude
            init_kwargs["altitude_ft"] = 1.002 ** to_decimal(c_ext)

    return dict(
        sym_table_id=sym_table_id,
        lat=lat,
        long=long,
        symbol_code=symbol_code,
        data_ext=data_ext,
        **init_kwargs,
    )


def encode_position_compressed(
    lat,
    long,
    sym_table_id,
    symbol_code,
    ambiguity=None,
    data_ext=None,
    altitude_ft=None,
) -> bytes:
    data = [
        sym_table_id,
        compress_lat(lat),
        compress_long(long),
        symbol_code,
    ]
    if data_ext:
        if isinstance(data_ext, CourseSpeed):
            data.append(from_decimal(data_ext.course // 4, 1).encode("ascii"))
            data.append(
                from_decimal(int(round(math.log(data_ext.speed + 1, 1.08))), 1).encode(
                    "ascii"
                )
            )
            data.append(b"#")
        elif isinstance(data_ext, RNG):
            data.append(b"{")
            data.append(
                from_decimal(int(round(math.log(data_ext.range / 2, 1.08))), 1).encode(
                    "ascii"
                )
            )
            data.append(b"#")
    elif altitude_ft:
        data.append(
            from_decimal(int(round(math.log(altitude_ft, 1.002))), 1).encode("ascii")
        )
        data.append(b"#")
    else:
        data.append(b"  #")
    return b"".join(data)


@define(frozen=True, slots=True)
class Position:
    """Represents a position including any data extension."""

    position_format: PositionFormat = field(default=PositionFormat.Uncompressed)
    lat: float = field(default=0.0)
    sym_table_id: bytes = field(default=b"/")
    long: float = field(default=0.0)
    symbol_code: bytes = field(default=b"-")
    altitude_ft: Optional[int] = field(default=None)
    data_ext: Union[bytes, DataExt] = field(default=b"")

    @classmethod
    def from_bytes_with_data_and_remainder(
        cls, raw: bytes
    ) -> Tuple["Position", bytes, bytes]:
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
            except ValueError:
                # eventually we may try to decode other position types here
                raise
        # try to decode extended data
        data_ext, remainder = DataExt.split_parse(remainder)
        # try to find the altitude comment
        alt_match = ALTITUDE_REX.search(remainder)
        if alt_match:
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
            )
        raise ValueError("Unknown position format: {!r}".format(self.position_format))


class PositionMixin:
    _position: Optional[Position] = field(default=None)

    @property
    def lat(self) -> Optional[float]:
        if self._position:
            return self._position.lat

    @property
    def long(self) -> Optional[float]:
        if self._position:
            return self._position.long

    @property
    def sym_table_id(self) -> Optional[bytes]:
        if self._position:
            return self._position.sym_table_id

    @property
    def symbol_code(self) -> Optional[bytes]:
        if self._position:
            return self._position.symbol_code

    @property
    def altitude_ft(self) -> Optional[int]:
        if self._position:
            return self._position.altitude_ft

    @property
    def data_ext(self) -> Union[DataExt, bytes]:
        if self._position:
            return self._position.data_ext
        return b""

    def format_altitude(self) -> bytes:
        if self.altitude_ft and not ALTITUDE_REX.search(getattr(self, "comment", b"")):
            return b"/A=%06d" % self.altitude_ft
        return b""
