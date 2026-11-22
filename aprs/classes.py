"""Python APRS Module Class Definitions."""

import dataclasses
import enum
from functools import lru_cache
from typing import Any

from ax253 import Frame

from .constants import TimestampFormat
from .position import Position, PositionMixin
from .timestamp import Timestamp, TimestampMixin
from .util import dataclass_subclasses

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


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


@dataclasses.dataclass(frozen=True, slots=True)
class InformationField:
    """
    Class for APRS 'Information' Field.
    """

    raw: bytes
    data_type: DataType
    data: bytes
    comment: bytes = b""

    @classmethod
    @lru_cache(len(DataType.__members__))
    def _find_handler(cls, data_type: DataType) -> type["InformationField"] | None:
        for subcls in dataclass_subclasses(cls):
            if data_type in subcls.__data_type__:
                return subcls
        return None

    @classmethod
    def from_bytes(cls, raw: bytes) -> "InformationField":
        data_type = DataType(raw[0:1])
        handler = cls._find_handler(data_type)
        if handler is None or data_type == DataType.OBJECT:
            x1j_header, found_data_type, data = raw.partition(b"!")
            if found_data_type and len(x1j_header) <= 40:
                # special case in APRS101
                return PositionReport.from_bytes(found_data_type + data)
        if handler is None:
            return cls(
                raw=raw,
                data_type=data_type,
                data=b"",
                comment=raw[1:],
            )
        return handler.from_bytes(raw)

    @classmethod
    def from_frame(cls, f: Frame) -> "InformationField":
        return cls.from_bytes(f.info)

    @classmethod
    def from_any(cls, obj: Any) -> "InformationField":
        if isinstance(obj, cls):
            return obj
        if isinstance(obj, Frame):
            return cls.from_frame(obj)
        return cls.from_bytes(obj)

    def __bytes__(self) -> bytes:
        return self.raw


@dataclasses.dataclass(frozen=True, slots=True)
class PositionReport(InformationField, TimestampMixin, PositionMixin):
    timestamp: Timestamp | None = None
    position: Position | None = None

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
                f"{data_type!r} cannot be handled by {cls!r} (expecting {cls.__data_type__!r})",
            )
        timestamp, remainder = None, raw[1:]
        if data_type in [
            DataType.POSITION_W_TIMESTAMP_MSG,
            DataType.POSITION_W_TIMESTAMP_NO_MSG,
        ]:
            timestamp, remainder = Timestamp.from_bytes(remainder[:7]), remainder[7:]
        position, data, comment = Position.from_bytes_with_data_and_remainder(remainder)
        return cls(
            raw=raw,
            data_type=data_type,
            data=data,
            timestamp=timestamp,
            position=position,
            comment=comment,
        )

    def __bytes__(self) -> bytes:
        return b"".join(
            [
                self.data_type.value,
                bytes(self.timestamp)
                if self.data_type
                in [
                    DataType.POSITION_W_TIMESTAMP_MSG,
                    DataType.POSITION_W_TIMESTAMP_NO_MSG,
                ]
                else b"",
                bytes(self.position),
                self.format_altitude(),
                self.comment,
            ],
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Message(InformationField):
    addressee: bytes = b""
    text: bytes = b""
    number: bytes | None = None

    __data_type__ = [DataType.MESSAGE]

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Message":
        data_type = DataType(raw[0:1])
        if data_type not in cls.__data_type__:
            raise DataTypeError(
                f"{data_type!r} cannot be handled by {cls!r} (expecting {cls.__data_type__!r})",
            )
        data = raw[1:]
        end_of_addressee = data[9:10]
        if end_of_addressee != DataType.MESSAGE.value:
            raise ValueError(
                f"Expecting {DataType.MESSAGE.value!r} at index 9 of {data!r}",
            )
        init_kwargs = dict(addressee=data[:9].strip())
        text = data[10:]
        if b"{" in text[-6:]:
            text, _, number = text.rpartition(b"{")
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
                self.addressee.ljust(9),  # pylint: disable=no-member
                DataType.MESSAGE.value,
                self.text[:67],  # pylint: disable=unsubscriptable-object
                b"{%s" % self.number if self.number else b"",
            ],
        )


@dataclasses.dataclass(frozen=True, slots=True)
class StatusReport(InformationField, TimestampMixin):
    status: bytes = b""
    timestamp: Timestamp | None = None

    __data_type__ = [DataType.STATUS]

    @classmethod
    def from_bytes(cls, raw: bytes) -> "StatusReport":
        data_type = DataType(raw[0:1])
        if data_type not in cls.__data_type__:
            raise DataTypeError(
                f"{data_type!r} cannot be handled by {cls!r} (expecting {cls.__data_type__!r})",
            )
        timestamp, data = None, raw[1:]
        try:
            timestamp, data = Timestamp.from_bytes(data[:7]), data[7:]
            if timestamp.timestamp_format != TimestampFormat.DayHoursMinutesZulu:
                # APRS101 p. 80: Note: The timestamp can only be in DHM zulu format.
                timestamp = dataclasses.replace(
                    timestamp, timestamp_format=TimestampFormat.DayHoursMinutesZulu
                )
        except ValueError:
            pass
        return cls(
            raw=raw,
            data_type=data_type,
            data=data,
            timestamp=timestamp,
            status=data,
        )

    def __bytes__(self):
        return b"".join(
            [
                DataType.STATUS.value,
                bytes(self.timestamp) if self.timestamp else b"",
                self.status,
            ],
        )


@dataclasses.dataclass(frozen=True, slots=True)
class ObjectReport(InformationField, TimestampMixin, PositionMixin):
    name: bytes | None = None
    killed: bool = False
    timestamp: Timestamp | None = None
    position: Position | None = None

    __data_type__ = [DataType.OBJECT]

    @classmethod
    def from_bytes(cls, raw: bytes) -> "ObjectReport":
        data_type = DataType(raw[0:1])
        if data_type not in cls.__data_type__:
            raise DataTypeError(
                f"{data_type!r} cannot be handled by {cls!r} (expecting {cls.__data_type__!r})",
            )
        name = raw[1:10].strip()
        killed = raw[10:11] == b"_"
        timestamp, remainder = Timestamp.from_bytes(raw[11:18]), raw[18:]
        position, data, comment = Position.from_bytes_with_data_and_remainder(remainder)
        return cls(
            raw=raw,
            data_type=data_type,
            data=data,
            comment=comment,
            name=name,
            killed=killed,
            timestamp=timestamp,
            position=position,
        )

    def __bytes__(self) -> bytes:
        return b"".join(
            [
                self.data_type.value,
                self.name.ljust(9),  # pylint: disable=no-member
                b"_" if self.killed else b"*",
                bytes(self.timestamp) if self.timestamp else b"",
                bytes(self.position) if self.position else b"",
                self.format_altitude(),
                self.comment,
            ],
        )


@dataclasses.dataclass(frozen=True, slots=True)
class ItemReport(InformationField, PositionMixin):
    name: bytes | None = None
    killed: bool = False
    position: Position | None = None

    __data_type__ = [DataType.ITEM]

    @classmethod
    def from_bytes(cls, raw: bytes) -> "ItemReport":
        data_type = DataType(raw[0:1])
        if data_type not in cls.__data_type__:
            raise DataTypeError(
                f"{data_type!r} cannot be handled by {cls!r} (expecting {cls.__data_type__!r})",
            )
        for split in (b"!", b"_"):
            name, status, remainder = raw[1:].partition(split)
            if status:
                break
        name = name.strip()
        killed = status == b"_"
        position, data, comment = Position.from_bytes_with_data_and_remainder(remainder)
        return cls(
            raw=raw,
            data_type=data_type,
            data=data,
            comment=comment,
            name=name,
            killed=killed,
            position=position,
        )

    def __bytes__(self) -> bytes:
        return b"".join(
            [
                self.data_type.value,
                self.name,
                b"_" if self.killed else b"!",
                bytes(self.position),
                self.format_altitude(),
                self.comment,
            ],
        )


@dataclasses.dataclass(frozen=True, slots=True)
class APRSFrame(Frame):
    """An AX.25 frame whose information field is decoded as APRS."""

    @staticmethod
    def _convert_info(info: Any) -> "InformationField":
        return InformationField.from_any(info)
