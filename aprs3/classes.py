#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Python APRS Module Class Definitions."""

from abc import ABC, abstractmethod
from datetime import datetime
import enum
from functools import lru_cache
import re
from typing import Optional, Tuple, Type, Union

from attrs import define, field

from .parser import decode_position_uncompressed, decode_timestamp

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2017 Greg Albrecht and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801


class DataType(enum.Enum):
    """APRS101.PDF p. 27"""

    CURRENT_MIC_E_DATA = b"\x1c"
    OLD_MIC_E_DATA = b"\x1c"
    POSITION_W_O_TIMESTAMP = b"!"
    PEET_BROS_U_II = b"#"
    RAW_GPS_DATA = b"$"
    AGRELO_DFJR = b"%"
    OLD_MIC_E_DATA_2 = b"'"
    ITEM = b")"
    PEET_BROS_U_II_2 = b"*"
    INVALID_DATA = b","
    POSITION_W_TIMESTAMP_NO_MSG = b"/"
    MESSAGE = b":"
    OBJECT = b";"
    STATION_CAPABILITIES = b"<"
    POSITION_W_O_TIMESTAMP_MSG = b"="
    STATUS = b">"
    QUERY = b"?"
    POSITION_W_TIMESTAMP_MSG = b"@"
    TELEMETRY_DATA = b"T"
    MAIDENHEAD_GRID_LOCATOR_BEACON = b"["
    WEATHER_REPORT_W_O_POSITION = b"_"
    CURRENT_MIC_E_DATA_2 = b"`"
    USER_DEFINED = b"{"
    THIRD_PARTY_TRAFFIC = b"}"


class DataTypeError(ValueError):
    pass


class DataExt(ABC):
    @classmethod
    @abstractmethod
    def try_parse(cls, raw: bytes) -> bool:
        """Return True if this subclass might be able to parse raw bytes."""

    @classmethod
    def from_bytes(cls, raw: bytes) -> Union["DataExt", bytes]:
        for subcls in cls.__subclasses__():
            if subcls.try_parse(raw):
                try:
                    return subcls.from_bytes(raw[:7])
                except ValueError:
                    pass
        return b""

    @classmethod
    def split_parse(cls, raw: bytes) -> Tuple[Union["DataExt", bytes], bytes]:
        parsed = cls.from_bytes(raw)
        if parsed:
            return parsed, raw[7:]
        return b"", raw


@define
class CourseSpeed(DataExt):
    course: int = field(default=0)
    speed: int = field(default=0)

    @classmethod
    def try_parse(cls, raw: bytes) -> bool:
        """Return True if this subclass might be able to parse raw bytes."""
        return re.match(rb"[0-9]{3}/", raw[:4])

    @classmethod
    def from_bytes(cls, raw: bytes) -> "CourseSpeed":
        course, slash, speed = raw[:7].partition(b"/")
        if not slash or len(course) != len(speed):
            raise ValueError("{!r} is not a Course/Speed extension field".format(raw))
        return cls(
            course=int(course.decode("ascii")),
            speed=int(speed.decode("ascii")),
        )


@define
class PHG(DataExt):
    """
    PHGphgd
    """

    power_w: int = field(default=0)
    height_ft: int = field(default=0)
    gain_db: int = field(default=0)
    directivity: int = field(default=0)

    @classmethod
    def try_parse(cls, raw: bytes) -> bool:
        """Return True if this subclass might be able to parse raw bytes."""
        return raw.startswith(b"PHG")

    @classmethod
    def from_bytes(cls, raw: bytes) -> "PHG":
        if not raw.startswith(b"PHG"):
            raise ValueError("{!r} is not a PHG extension field".format(raw))
        power_code, height_code, gain_code, directivity_code = raw[3:7]
        zero_byte = ord(b"0")
        return cls(
            power_w=int(power_code - zero_byte) ** 2,
            height_ft=10 * (2 ** int(height_code - zero_byte)),
            gain_db=int(gain_code - zero_byte),
            directivity=int(directivity_code - zero_byte) * 45,
        )


@define
class RNG(DataExt):
    """
    RNGrrrr
    """

    range: int = field(default=0)

    @classmethod
    def try_parse(cls, raw: bytes) -> bool:
        """Return True if this subclass might be able to parse raw bytes."""
        return raw.startswith(b"RNG")

    @classmethod
    def from_bytes(cls, raw: bytes) -> "RNG":
        if not raw.startswith(b"RNG"):
            raise ValueError("{!r} is not a RNG extension field".format(raw))
        return cls(range=int(raw[3:7]))


@define
class DFS(DataExt):
    """
    DFSshgd
    """

    strength_s: int = field(default=0)
    height_ft: int = field(default=0)
    gain_db: int = field(default=0)
    directivity: int = field(default=0)

    @classmethod
    def try_parse(cls, raw: bytes) -> bool:
        """Return True if this subclass might be able to parse raw bytes."""
        return raw.startswith(b"DFS")

    @classmethod
    def from_bytes(cls, raw: bytes) -> "DFS":
        if not raw.startswith(b"DFS"):
            raise ValueError("{!r} is not a DFS extension field".format(raw))
        strength_code, height_code, gain_code, directivity_code = raw[3:7]
        zero_byte = ord(b"0")
        return cls(
            strength_s=int(strength_code - zero_byte),
            height_ft=10 * (2 ** int(height_code - zero_byte)),
            gain_db=int(gain_code - zero_byte),
            directivity=int(directivity_code - zero_byte) * 45,
        )


@define
class AreaObject(DataExt):
    """
    Tyy/Cxx
    """

    t: bytes = field(default=b"")
    c: bytes = field(default=b"")

    @classmethod
    def try_parse(cls, raw: bytes) -> bool:
        """Return True if this subclass might be able to parse raw bytes."""
        return re.match(rb"T../C..", raw[:7])

    @classmethod
    def from_bytes(cls, raw: bytes) -> "AreaObject":
        if not re.match(rb"T../C..", raw[:7]):
            raise ValueError("{!r} is not an Area Object extension field".format(raw))
        return cls(
            t=raw[1:3],
            c=raw[5:7],
        )


@define(frozen=True, slots=True)
class InformationField:
    """
    Class for APRS 'Information' Field.
    """

    raw: bytes
    data_type: DataType
    data: bytes
    data_ext: Union[bytes, DataExt] = field(default=b"")
    comment: bytes = field(default=b"")

    @classmethod
    @lru_cache(len(DataType.__members__))
    def _find_handler(cls, data_type: DataType) -> Type["InformationField"]:
        for subcls in cls.__subclasses__():
            if data_type in subcls.__data_type__:
                return subcls

    @classmethod
    def from_bytes(cls, raw: bytes) -> "InformationField":
        data_type = DataType(raw[0:1])
        handler = cls._find_handler(data_type)
        if handler is None:
            x1j_header, found_data_type, data = raw.partition(b"!")
            if len(x1j_header) <= 40:
                # special case in APRS101
                return PositionReport.from_bytes(found_data_type + data)
            return cls(
                raw=raw, data_type=data_type, data=b"", data_ext=b"", comment=raw[1:]
            )
        return handler.from_bytes(raw)

    def __bytes__(self) -> bytes:
        return self.raw


ALTITUDE_REX = re.compile(rb"/A=(-[0-9]+)")


@define(frozen=True, slots=True)
class PositionReport(InformationField):
    timestamp: Optional[datetime] = field(default=None)
    lat: float = field(default=0.0)
    sym_table_id: bytes = field(default=b"/")
    long: float = field(default=0.0)
    symbol_code: bytes = field(default=b"-")
    altitude_ft: Optional[int] = field(default=None)

    __data_type__ = [
        DataType.POSITION_W_O_TIMESTAMP,
        DataType.POSITION_W_O_TIMESTAMP_MSG,
        DataType.POSITION_W_TIMESTAMP_MSG,
        DataType.POSITION_W_TIMESTAMP_NO_MSG,
    ]

    @classmethod
    def from_bytes(cls, raw: bytes) -> "PositionReport":
        data_type = DataType(raw[0:1])
        if data_type not in cls.__data_type__:
            raise DataTypeError(
                "{!r} cannot be handled by {!r} (expecting {!r})".format(
                    data_type, cls, cls.__data_type__
                )
            )
        timestamp = None
        if data_type in [
            DataType.POSITION_W_TIMESTAMP_MSG,
            DataType.POSITION_W_TIMESTAMP_NO_MSG,
        ]:
            timestamp = decode_timestamp(raw[1:8])
            data = raw[8:]
        else:
            data = raw[1:]
        comment = b""
        try:
            position = decode_position_uncompressed(data[:19])
            data, comment = data[:19], data[19:]
        except ValueError:
            # eventually we may try to decode other position types here
            raise
        # try to decode extended data
        data_ext, comment = DataExt.split_parse(comment)
        # try to find the altitude comment
        alt_match = ALTITUDE_REX.search(comment)
        return cls(
            raw=raw,
            data_type=data_type,
            data=data,
            data_ext=data_ext,
            comment=comment,
            timestamp=timestamp,
            altitude_ft=int(alt_match.group(1).decode("ascii")) if alt_match else None,
            **position,
        )


@define(frozen=True, slots=True)
class Message(InformationField):
    addressee: bytes = field(default=b"")
    text: bytes = field(default=b"")
    number: Optional[bytes] = field(default=None)

    __data_type__ = [DataType.MESSAGE]

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Message":
        data_type = DataType(raw[0:1])
        if data_type not in cls.__data_type__:
            raise DataTypeError(
                "{!r} cannot be handled by {!r} (expecting {!r})".format(
                    data_type, cls, cls.__data_type__
                )
            )
        data = raw[1:]
        end_of_addressee = data[9:10]
        if end_of_addressee != DataType.MESSAGE.value:
            raise ValueError(
                "Expecting {!r} at index 9 of {!r}".format(DataType.MESSAGE.value, data)
            )
        init_kwargs = dict(addressee=data[:9].strip())
        text = data[10:]
        if b"{" in text[-6:]:
            text, mid, number = text.rpartition(b"{")
            init_kwargs["number"] = number
        return cls(
            raw=raw,
            data_type=data_type,
            data=data,
            text=text,
            **init_kwargs,
        )

    def __bytes__(self):
        return b"".join(
            [
                DataType.MESSAGE.value,
                self.addressee.ljust(9),
                DataType.MESSAGE.value,
                self.text[:67],
                b"{%s" % self.number if self.number else b"",
            ]
        )
