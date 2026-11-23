"""Python APRS Module Class Definitions."""

import enum
import re
from functools import lru_cache
from typing import Any, ClassVar, TypeVar

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
    OLD_MIC_E_DATA = b"\x1d"
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
        DataType.OLD_MIC_E_DATA,
        DataType.OLD_MIC_E_DATA_2,
        DataType.CURRENT_MIC_E_DATA_2,
    }
)


class DataTypeError(ValueError):
    pass


_V = TypeVar("_V")


def _required(value: _V | None, name: str) -> _V:
    if value is None:
        raise ValueError(f"cannot encode this report without a {name}")
    return value


@define(frozen=True, slots=True)
class InformationField:
    """
    Class for APRS 'Information' Field.
    """

    raw: bytes
    data_type: DataType | None
    """None when the first byte isn't a known APRS data type identifier."""
    data: bytes
    comment: bytes = field(default=b"")

    __data_type__: ClassVar[list[DataType]] = []
    """The data types a subclass decodes."""

    @classmethod
    @lru_cache(len(DataType.__members__))
    def _find_handler(cls, data_type: DataType) -> type["InformationField"] | None:
        for subcls in attrs_subclasses(cls):
            if data_type in subcls.__data_type__:
                return subcls
        return None

    @classmethod
    def from_bytes(cls, raw: bytes) -> "InformationField":
        try:
            data_type = DataType(raw[0:1])
        except ValueError:
            # free text, an empty info field, or an unused identifier
            # (APRS101 p17): keep the raw bytes so the frame still decodes
            data_type = None
        handler = None if data_type is None else cls._find_handler(data_type)
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
                comment=raw if data_type is None else raw[1:],
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

    def _data_type_id(self) -> bytes:
        """The data type identifier byte, for encoding."""
        if self.data_type is None:
            raise ValueError(f"{type(self).__name__} has no data type to encode")
        return self.data_type.value


@define(frozen=True, slots=True)
class PositionReport(InformationField, TimestampMixin, PositionMixin):
    _timestamp: Timestamp | None = field(default=None, alias="timestamp")
    _position: Position | None = field(default=None, alias="position")
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
                self._data_type_id(),
                bytes(_required(self._timestamp, "timestamp"))
                if self.data_type
                in [
                    DataType.POSITION_W_TIMESTAMP_MSG,
                    DataType.POSITION_W_TIMESTAMP_NO_MSG,
                ]
                else b"",
                bytes(_required(self._position, "position")),
                self.format_altitude(),
                self.comment,
            ],
        )


MESSAGE_NUMBER = re.compile(rb"\{([A-Za-z0-9]{0,5}(?:\}[A-Za-z0-9]{0,5})?)$")
"""A trailing message number: {N} with 1-5 characters, or {MM}AA with a reply-ack.

The number keeps a reply-ack's "}" and acked number (aprs11/replyacks.txt).
"""


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
        match = MESSAGE_NUMBER.search(text)
        if match is not None:
            text, init_kwargs["number"] = text[: match.start()], match.group(1)
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
                # no truncation: the spec's 67 character limit applies to
                # chat text, but telemetry PARM/UNIT/EQNS/BITS headers are
                # carried as messages and may be longer
                self.text,
                b"" if self.number is None else b"{%s" % self.number,
            ],
        )


@define(frozen=True, slots=True)
class StatusReport(InformationField, TimestampMixin):
    status: bytes = field(default=b"")
    _timestamp: Timestamp | None = field(default=None, alias="timestamp")

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
    _timestamp: Timestamp | None = field(default=None, alias="timestamp")
    _position: Position | None = field(default=None, alias="position")

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
                self._data_type_id(),
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
    _position: Position | None = field(default=None, alias="position")

    __data_type__ = [DataType.ITEM]

    @classmethod
    def from_bytes(cls, raw: bytes) -> "ItemReport":
        data_type = DataType(raw[0:1])
        if data_type not in cls.__data_type__:
            raise DataTypeError(
                f"{data_type!r} cannot be handled by {cls!r} (expecting {cls.__data_type__!r})",
            )
        # APRS101 p59: the name (3-9 characters) can't contain "!" or "_",
        # so the first of either ends it; the comment may contain both
        match = re.search(rb"[!_]", raw[1:])
        if match is None:
            raise ValueError(f"{raw!r}: item name is not terminated by '!' or '_'")
        name = raw[1 : 1 + match.start()]
        status = match.group()
        remainder = raw[2 + match.start() :]
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
                self._data_type_id(),
                self.name,
                b"_" if self.killed else b"!",
                bytes(_required(self._position, "position")),
                self.format_altitude(),
                self.comment,
            ],
        )


@define(frozen=True, slots=True)
class APRSFrame(Frame):
    # Narrower than Frame.info (bytes); bytes(info) is still the AX.25 info.
    # ty doesn't yet apply attrs converters (it sees the default, b"").
    info: InformationField = field(  # ty: ignore[incompatible-attribute-override, invalid-assignment]
        default=b"", converter=InformationField.from_any
    )
