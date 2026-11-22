"""Python APRS Module Class Definitions."""

import enum
from functools import lru_cache
from typing import Any

import attr
from attrs import define, field
from ax253 import Frame

from .constants import TimestampFormat
from .position import Position, PositionMixin
from .timestamp import Timestamp, TimestampMixin
from .util import attrs_subclasses

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


# Mic-E encodes the position in the destination address; its info field can
# contain a "!" that is not a position
MIC_E_DATA_TYPES = frozenset(
    {
        DataType.CURRENT_MIC_E_DATA,
        DataType.OLD_MIC_E_DATA_2,
        DataType.CURRENT_MIC_E_DATA_2,
    }
)


class DataTypeError(ValueError):
    pass


@define(frozen=True, slots=True)
class InformationField:
    """
    Class for APRS 'Information' Field.
    """

    raw: bytes
    data_type: DataType
    data: bytes
    comment: bytes = field(default=b"")

    @classmethod
    @lru_cache(len(DataType.__members__))
    def _find_handler(cls, data_type: DataType) -> type["InformationField"] | None:
        for subcls in attrs_subclasses(cls):
            if data_type in subcls.__data_type__:
                return subcls
        return None

    @classmethod
    def from_bytes(cls, raw: bytes) -> "InformationField":
        data_type = DataType(raw[0:1])
        handler = cls._find_handler(data_type)
        if (handler is None or data_type == DataType.OBJECT) and (
            data_type not in MIC_E_DATA_TYPES
        ):
            x1j_header, found_data_type, data = raw.partition(b"!")
            if found_data_type and len(x1j_header) <= 40:
                # special case in APRS101 p32: a position after up to 40
                # characters of other text (e.g. a TNC beacon header)
                try:
                    report = PositionReport.from_bytes(found_data_type + data)
                    return attr.evolve(report, raw=raw, prefix=x1j_header)
                except ValueError:
                    pass  # just a "!" in some other kind of packet
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


@define(frozen=True, slots=True)
class PositionReport(InformationField, TimestampMixin, PositionMixin):
    _timestamp: Timestamp | None = field(default=None)
    _position: Position | None = field(default=None)
    prefix: bytes = field(default=b"")
    """Text before the "!" of a position that doesn't start the info field."""

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
                self.prefix,
                self.data_type.value,
                bytes(self._timestamp)
                if self.data_type
                in [
                    DataType.POSITION_W_TIMESTAMP_MSG,
                    DataType.POSITION_W_TIMESTAMP_NO_MSG,
                ]
                else b"",
                bytes(self._position),
                self.format_altitude(),
                self.comment,
            ],
        )


@define(frozen=True, slots=True)
class Message(InformationField):
    addressee: bytes = field(default=b"")
    text: bytes = field(default=b"")
    number: bytes | None = field(default=None)

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
                b"" if self.number is None else b"{%s" % self.number,
            ],
        )


@define(frozen=True, slots=True)
class StatusReport(InformationField, TimestampMixin):
    status: bytes = field(default=b"")
    _timestamp: Timestamp | None = field(default=None)

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
                timestamp = attr.evolve(
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
                bytes(self._timestamp) if self._timestamp else b"",
                self.status,
            ],
        )


@define(frozen=True, slots=True)
class ObjectReport(InformationField, TimestampMixin, PositionMixin):
    name: bytes = field(default=None)
    killed: bool = field(default=False)
    _timestamp: Timestamp | None = field(default=None)
    _position: Position | None = field(default=None)

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
                bytes(self._timestamp) if self._timestamp else b"",
                bytes(self._position) if self._position else b"",
                self.format_altitude(),
                self.comment,
            ],
        )


@define(frozen=True, slots=True)
class ItemReport(InformationField, PositionMixin):
    name: bytes = field(default=None)
    killed: bool = field(default=False)
    _position: Position | None = field(default=None)

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
                bytes(self._position),
                self.format_altitude(),
                self.comment,
            ],
        )


@define(frozen=True, slots=True)
class APRSFrame(Frame):
    info: InformationField = field(default=b"", converter=InformationField.from_any)
