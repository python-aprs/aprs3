"""Python APRS Module Class Definitions."""

import enum
import logging
import re
from functools import lru_cache
from typing import Any, ClassVar, Self, TypeVar

import attr
from attrs import define, field
from ax253 import Frame

from .constants import TimestampFormat
from .position import HasPosition, Position, PositionMixin
from .timestamp import Timestamp, TimestampMixin
from .util import attrs_subclasses

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"

log = logging.getLogger(__name__)


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


def _as_bytes(value: str | bytes) -> bytes:
    """Text fields are stored as bytes; ``str`` is encoded as UTF-8."""
    return value.encode("utf-8") if isinstance(value, str) else bytes(value)


def _as_bytes_or_none(value: str | bytes | None) -> bytes | None:
    return None if value is None else _as_bytes(value)


def _as_name(value: str | bytes) -> bytes:
    """An object or item name; None (not yet named) is kept."""
    return value if value is None else _as_bytes(value)


def _as_str(value: bytes) -> str:
    """Decode wire text: UTF-8, or Latin-1 (which never fails) when invalid."""
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode("latin-1")


def _required(value: _V | None, name: str) -> _V:
    if value is None:
        raise ValueError(f"cannot encode this report without a {name}")
    return value


@define(frozen=True, slots=True, kw_only=True)
class InformationField:
    """
    Class for APRS 'Information' Field.

    Fields are keyword-only. ``raw`` and ``data`` are what was heard; they
    don't take part in equality, so a report built to send equals the same
    report decoded off the air.
    """

    __match_args__ = ("data_type", "comment")

    raw: bytes = field(default=b"", converter=_as_bytes, eq=False, repr=False)
    """The bytes this report was decoded from; b"" for one built to send."""
    data_type: DataType | None = field(default=None)
    """
    None when the first byte isn't a known APRS data type identifier. A
    report built without one gets its class's usual data type (see
    ``default_data_type``).
    """
    data: bytes = field(default=b"", converter=_as_bytes, eq=False, repr=False)
    comment: bytes = field(default=b"", converter=_as_bytes)
    _source: bytes | None = field(default=None, init=False, eq=False, repr=False)
    """
    The bytes this report was decoded from, re-sent unchanged by subclasses
    whose format has several spellings of the same values. Not carried over
    by ``attrs.evolve``, so a changed copy is encoded from its fields.
    """

    __data_type__: ClassVar[list[DataType]] = []
    """The data types a subclass decodes."""
    __raw_fallback__: ClassVar[bool] = False
    """
    Keep a packet this subclass can't decode as a raw InformationField
    instead of failing, for formats that used to be kept raw.
    """

    def __attrs_post_init__(self) -> None:
        if self.data_type is None:
            object.__setattr__(self, "data_type", self.default_data_type())

    def default_data_type(self) -> DataType | None:
        """The data type of a report built without one: the first one decoded."""
        return self.__data_type__[0] if self.__data_type__ else None

    @property
    def comment_str(self) -> str:
        """``comment`` as text: UTF-8, or Latin-1 when it isn't valid UTF-8."""
        return _as_str(self.comment)

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
        if handler is not None and handler.__raw_fallback__:
            try:
                return handler.from_bytes(raw)
            except ValueError:
                log.debug("Keep undecodable %s raw: %r", handler.__name__, raw)
                handler = None  # e.g. "Test !4903.50N...": try the position
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
            return cls._raw(raw, data_type)
        return handler.from_bytes(raw)

    @classmethod
    def _raw(cls, raw: bytes, data_type: DataType | None) -> "InformationField":
        return cls(
            raw=raw,
            data_type=data_type,
            data=b"",
            comment=raw if data_type is None else raw[1:],
        )

    def _keep_source(self, raw: bytes) -> Self:
        """Remember the decoded bytes, so ``bytes(self)`` reproduces them."""
        object.__setattr__(self, "_source", raw)
        return self

    @classmethod
    def from_frame(cls, f: Frame) -> "InformationField":
        return cls.from_bytes(f.info)

    @classmethod
    def from_any(cls, obj: Any) -> "InformationField":
        if isinstance(obj, cls):
            return obj
        if isinstance(obj, Frame):
            return cls.from_frame(obj)
        if isinstance(obj, str):
            obj = obj.encode("utf-8")  # as ax253.Frame encodes str info
        return cls.from_bytes(bytes(obj))

    def __bytes__(self) -> bytes:
        """
        Encode the report from its fields.

        A report decoded from bytes encodes back to exactly those bytes,
        even where the decoder was lenient (an addressee not left-aligned,
        a malformed PHG, an unusual object status byte); each such case
        logs a warning on the ``aprs.classes`` logger. A report built from
        fields, or changed with ``attr.evolve``, is encoded from its fields.
        """
        encoded = self._encode()
        if self.raw and encoded != self.raw and self._decodes_from_raw():
            # the decoder accepted something its fields can't express: keep
            # the bytes heard, but say so, so the gap can be found and fixed
            log.warning(
                "%s doesn't encode back to the bytes it was decoded from; "
                "using those bytes. Heard %r, fields encode as %r",
                type(self).__name__,
                self.raw,
                encoded,
            )
            return self.raw
        return encoded

    def _encode(self) -> bytes:
        """
        Encode the fields as an info field; subclasses override this. Here:
        the data type identifier, ``data`` and ``comment``.
        """
        if self.data_type is None:
            return self.data + self.comment
        return self.data_type.value + self.data + self.comment

    def _decodes_from_raw(self) -> bool:
        """True if decoding ``raw`` gives this report, unchanged."""
        try:
            return InformationField.from_bytes(self.raw) == self
        except ValueError:
            return False

    def _data_type_id(self) -> bytes:
        """The data type identifier byte, for encoding."""
        if self.data_type is None:
            raise ValueError(f"{type(self).__name__} has no data type to encode")
        return self.data_type.value


@define(frozen=True, slots=True, kw_only=True)
class PositionReport(InformationField, TimestampMixin, PositionMixin):
    __match_args__ = ("lat", "long")

    _timestamp: Timestamp | None = field(default=None, alias="timestamp")
    _position: Position | None = field(default=None, alias="position")
    prefix: bytes = field(default=b"", converter=_as_bytes)
    """Text before the "!" of a position that doesn't start the info field."""

    __data_type__ = [
        DataType.POSITION_W_O_TIMESTAMP,
        DataType.POSITION_W_O_TIMESTAMP_MSG,
        DataType.POSITION_W_TIMESTAMP_MSG,
        DataType.POSITION_W_TIMESTAMP_NO_MSG,
    ]

    def default_data_type(self) -> DataType:
        """``=`` (messaging capable), or ``@`` with a timestamp."""
        if self._timestamp is not None:
            return DataType.POSITION_W_TIMESTAMP_MSG
        return DataType.POSITION_W_O_TIMESTAMP_MSG

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

    def _encode(self) -> bytes:
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
                self.altitude_and_comment(),
            ],
        )


MESSAGE_NUMBER = re.compile(rb"\{([A-Za-z0-9]{0,5}(?:\}[A-Za-z0-9]{0,5})?)$")
"""A trailing message number: {N} with 1-5 characters, or {MM}AA with a reply-ack.

The number keeps a reply-ack's "}" and acked number (aprs11/replyacks.txt).
"""
ACK_REJ = re.compile(rb"(ack|rej)([A-Za-z0-9]{1,5})(\}[A-Za-z0-9]{0,5})?")
"""An ack or reject's whole text: ackNNNNN, or ackMM}AA with a reply-ack."""
BULLETIN = re.compile(rb"BLN([0-9A-Z])(.{0,5})")
"""Bulletin (BLN0-BLN9, group: BLN0WX) and announcement (BLNA-BLNZ) addressees."""
DIRECTED_QUERY = re.compile(rb"\?([A-Za-z0-9]+)\??(?:\s.*)?", re.DOTALL)
"""A directed query: ?APRSP, ?PING? ..., optionally followed by arguments."""
NWS_PREFIXES = (b"NWS-", b"NWS_", b"SKY", b"CWA", b"BOM")
"""Addressee prefixes of weather service bulletins (APRS101 p76, wx.txt)."""


@define(frozen=True, slots=True, kw_only=True)
class Message(InformationField):
    """
    A message, ack, reject, bulletin or announcement (APRS101 ch. 14).

    ``number`` is everything after the ``{``, including a reply-ack's
    ``}AA``; ``message_number`` and ``reply_ack`` split it. Acks and rejects
    carry the number they answer in the text: see ``is_ack``, ``is_rej`` and
    ``acked_number``.
    """

    __match_args__ = ("addressee", "text")

    addressee: bytes = field(default=b"", converter=_as_bytes)
    text: bytes = field(default=b"", converter=_as_bytes)
    number: bytes | None = field(default=None, converter=_as_bytes_or_none)

    __data_type__ = [DataType.MESSAGE]

    @property
    def addressee_str(self) -> str:
        """``addressee`` as text (see ``comment_str``)."""
        return _as_str(self.addressee)

    @property
    def text_str(self) -> str:
        """``text`` as text: UTF-8, or Latin-1 when it isn't valid UTF-8."""
        return _as_str(self.text)

    @classmethod
    def new(
        cls,
        addressee: str | bytes,
        text: str | bytes,
        number: str | bytes | None = None,
        reply_ack: str | bytes | None = None,
    ) -> "Message":
        """
        Build a message to send.

        :param number: the message number, to ask for an ack
        :param reply_ack: with ``number``, send ``{number}reply_ack``: an
            empty value advertises reply-ack support, a number also acks the
            addressee's message with that number

        >>> bytes(Message.new("N0CALL-2", "hello", number="12", reply_ack=""))
        b':N0CALL-2 :hello{12}'
        """
        if reply_ack is not None:
            if number is None:
                raise ValueError("a reply-ack needs a message number")
            number = _as_bytes(number) + b"}" + _as_bytes(reply_ack)
        return cls(
            raw=b"",
            data_type=DataType.MESSAGE,
            data=b"",
            addressee=_as_bytes(addressee),
            text=_as_bytes(text),
            number=None if number is None else _as_bytes(number),
        )

    @classmethod
    def ack_for(
        cls,
        addressee: str | bytes,
        number: str | bytes,
        reply_ack: str | bytes | None = None,
        reject: bool = False,
    ) -> "Message":
        """
        Build the ack (or with ``reject``, the reject) of message ``number``.

        >>> bytes(Message.ack_for("N0CALL", "12"))
        b':N0CALL   :ack12'
        >>> bytes(Message.ack_for("N0CALL", "12", reply_ack="", reject=True))
        b':N0CALL   :rej12}'
        """
        text = (b"rej" if reject else b"ack") + _as_bytes(number)
        if reply_ack is not None:
            text += b"}" + _as_bytes(reply_ack)
        return cls.new(addressee, text)

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

    def _encode(self) -> bytes:
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

    # --- message numbers and reply-acks ----------------------------------

    @property
    def message_number(self) -> bytes | None:
        """This message's number, without a reply-ack ("12" of "{12}AB")."""
        if self.number is None:
            return None
        return self.number.partition(b"}")[0]

    @property
    def reply_ack(self) -> bytes | None:
        """
        The reply-ack (aprs11/replyacks.txt) of a message or ack.

        None without one; b"" when the sender only advertises reply-ack
        support ("{12}", "ack12}"); otherwise the number of our message it
        acks ("{12}AB" and "ack12}AB" both ack our message AB).
        """
        if self.number is not None:
            number, brace, reply_ack = self.number.partition(b"}")
            return reply_ack if brace else None
        match = self._ack_rej()
        if match is None or match.group(3) is None:
            return None
        return match.group(3)[1:]

    # --- acks and rejects ------------------------------------------------

    def _ack_rej(self) -> "re.Match[bytes] | None":
        if self.number is not None:
            return None
        return ACK_REJ.fullmatch(self.text)

    @property
    def is_ack(self) -> bool:
        """True for an ack ("ack12"); its number is ``acked_number``."""
        match = self._ack_rej()
        return match is not None and match.group(1) == b"ack"

    @property
    def is_rej(self) -> bool:
        """True for a reject ("rej12"); its number is ``acked_number``."""
        match = self._ack_rej()
        return match is not None and match.group(1) == b"rej"

    @property
    def acked_number(self) -> bytes | None:
        """The message number an ack or reject answers, else None."""
        match = self._ack_rej()
        return None if match is None else match.group(2)

    # --- bulletins, announcements and weather service --------------------

    def _bulletin(self) -> "re.Match[bytes] | None":
        return BULLETIN.fullmatch(self.addressee)

    @property
    def is_bulletin(self) -> bool:
        """Addressed BLN0-BLN9, optionally with a group (BLN0WX)."""
        match = self._bulletin()
        return match is not None and match.group(1).isdigit()

    @property
    def is_announcement(self) -> bool:
        """Addressed BLNA-BLNZ."""
        match = self._bulletin()
        return match is not None and match.group(1).isalpha()

    @property
    def bulletin_id(self) -> bytes | None:
        """The bulletin or announcement identifier: b"1" of BLN1, b"A" of BLNA."""
        match = self._bulletin()
        return None if match is None else match.group(1)

    @property
    def bulletin_group(self) -> bytes | None:
        """A group bulletin's group name (b"WX" of BLN3WX); b"" for none."""
        match = self._bulletin()
        return None if match is None else match.group(2).rstrip()

    @property
    def query(self) -> bytes | None:
        """
        A directed query's name (APRS101 ch. 15): b"APRSP" for "?APRSP",
        b"PING" for "?PING?"; None for other messages.
        """
        match = DIRECTED_QUERY.fullmatch(self.text)
        return None if match is None else match.group(1)

    @property
    def telemetry_metadata(self):  # -> aprs.telemetry.TelemetryMetadata | None
        """
        The parsed ``PARM.``, ``UNIT.``, ``EQNS.`` or ``BITS.`` telemetry
        metadata this message carries, else None.
        """
        from .telemetry import telemetry_metadata  # pylint: disable=import-outside-toplevel

        return telemetry_metadata(self)

    @property
    def is_nws(self) -> bool:
        """A weather service bulletin (NWS-WARN, SKYCWA ...)."""
        return self.addressee.upper().startswith(NWS_PREFIXES)


@define(frozen=True, slots=True, kw_only=True)
class StatusReport(InformationField, TimestampMixin):
    __match_args__ = ("status",)

    status: bytes = field(default=b"", converter=_as_bytes)
    _timestamp: Timestamp | None = field(default=None, alias="timestamp")

    __data_type__ = [DataType.STATUS]

    @property
    def status_str(self) -> str:
        """``status`` as text: UTF-8, or Latin-1 when it isn't valid UTF-8."""
        return _as_str(self.status)

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

    def _encode(self) -> bytes:
        return b"".join(
            [
                DataType.STATUS.value,
                bytes(self._timestamp) if self._timestamp else b"",
                self.status,
            ],
        )


@define(frozen=True, slots=True, kw_only=True)
class ObjectReport(InformationField, TimestampMixin, PositionMixin):
    __match_args__ = ("name", "lat", "long")

    name: bytes = field(default=None, converter=_as_name)
    killed: bool = field(default=False)
    _timestamp: Timestamp | None = field(default=None, alias="timestamp")
    _position: Position | None = field(default=None, alias="position")

    __data_type__ = [DataType.OBJECT]

    @property
    def name_str(self) -> str:
        """``name`` as text: UTF-8, or Latin-1 when it isn't valid UTF-8."""
        return _as_str(self.name or b"")

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

    def _encode(self) -> bytes:
        return b"".join(
            [
                self._data_type_id(),
                self.name.ljust(9),  # pylint: disable=no-member
                b"_" if self.killed else b"*",
                bytes(self._timestamp) if self._timestamp else b"",
                bytes(self._position) if self._position else b"",
                self.altitude_and_comment(),
            ],
        )


@define(frozen=True, slots=True, kw_only=True)
class ItemReport(InformationField, PositionMixin):
    __match_args__ = ("name", "lat", "long")

    name: bytes = field(default=None, converter=_as_name)
    killed: bool = field(default=False)
    _position: Position | None = field(default=None, alias="position")

    __data_type__ = [DataType.ITEM]

    @property
    def name_str(self) -> str:
        """``name`` as text: UTF-8, or Latin-1 when it isn't valid UTF-8."""
        return _as_str(self.name or b"")

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

    def _encode(self) -> bytes:
        return b"".join(
            [
                self._data_type_id(),
                self.name,
                b"_" if self.killed else b"!",
                bytes(_required(self._position, "position")),
                self.altitude_and_comment(),
            ],
        )


@define(frozen=True, slots=True)
class APRSFrame(Frame):
    # Narrower than Frame.info (bytes); bytes(info) is still the AX.25 info.
    # ty doesn't yet apply attrs converters (it sees the default, b"").
    info: InformationField = field(  # ty: ignore[incompatible-attribute-override, invalid-assignment]
        default=b"", converter=InformationField.from_any
    )

    @property
    def position(self) -> Position | None:
        """The info field's position, or None when it has none."""
        if isinstance(self.info, HasPosition):
            return self.info.position
        return None

    def __attrs_post_init__(self) -> None:
        # Mic-E carries half its data in the destination address, which the
        # info converter can't see: decode it here, once the frame is built
        info = self.info
        if type(info) is not InformationField or info.data_type not in MIC_E_DATA_TYPES:
            return
        handler = InformationField._find_handler(info.data_type)
        decode = getattr(handler, "from_bytes_and_destination", None)
        if decode is None:
            return
        try:
            report = decode(info.raw, self.destination.callsign)
        except ValueError:
            log.debug("Keep undecodable Mic-E raw: %r", info.raw, exc_info=True)
            return
        object.__setattr__(self, "info", report)
