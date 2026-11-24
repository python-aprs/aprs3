"""Decoders for the smaller APRS data types (APRS101 ch. 15, 17, 18, 19)."""

import re
from decimal import Decimal

from attrs import define, field

from .classes import APRSFrame, DataType, DataTypeError, InformationField

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2026 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


def _check_data_type(cls: type[InformationField], raw: bytes) -> DataType:
    data_type = DataType(raw[0:1])
    if data_type not in cls.__data_type__:
        raise DataTypeError(
            f"{data_type!r} cannot be handled by {cls!r} (expecting {cls.__data_type__!r})",
        )
    return data_type


QUERY = re.compile(rb"([A-Za-z0-9]+)\?(.*)", re.DOTALL)


@define(frozen=True, slots=True, kw_only=True)
class QueryReport(InformationField):
    """
    A general query (APRS101 ch. 15): ``?APRS?``, ``?IGATE?``, ``?WX?``.

    Directed queries are messages; see ``Message.query``.

    >>> q = QueryReport.from_bytes(b"?APRS? 34.02,-117.15,0200")
    >>> q.query, q.target
    (b'APRS', b' 34.02,-117.15,0200')
    """

    query: bytes = field(default=b"")
    """The query name between the question marks, e.g. b"IGATE"."""
    target: bytes = field(default=b"")
    """Anything after the query: an optional target footprint."""

    __data_type__ = [DataType.QUERY]
    __raw_fallback__ = True

    @classmethod
    def from_bytes(cls, raw: bytes) -> "QueryReport":
        data_type = _check_data_type(cls, raw)
        match = QUERY.fullmatch(raw[1:])
        if match is None:
            raise ValueError(f"{raw!r} is not a general query")
        return cls(
            raw=raw,
            data_type=data_type,
            data=raw[1:],
            query=match.group(1),
            target=match.group(2),
        )

    def __bytes__(self) -> bytes:
        return b"?%s?%s" % (self.query, self.target)


@define(frozen=True, slots=True, kw_only=True)
class CapabilitiesReport(InformationField):
    """
    Station capabilities (APRS101 p. 85), usually an igate's reply to ``?IGATE?``.

    >>> report = CapabilitiesReport.from_bytes(b"<IGATE,MSG_CNT=30,LOC_CNT=61")
    >>> report.capabilities
    {b'IGATE': None, b'MSG_CNT': b'30', b'LOC_CNT': b'61'}
    """

    entries: tuple[tuple[bytes, bytes | None], ...] = field(
        default=(), converter=lambda v: tuple((k, val) for k, val in v)
    )
    """Each comma-separated ``TOKEN`` or ``TOKEN=value``, in order."""

    __data_type__ = [DataType.STATION_CAPABILITIES]
    __raw_fallback__ = True

    @classmethod
    def from_bytes(cls, raw: bytes) -> "CapabilitiesReport":
        data_type = _check_data_type(cls, raw)
        entries = []
        for token in raw[1:].split(b","):
            key, eq, value = token.partition(b"=")
            entries.append((key, value if eq else None))
        return cls(raw=raw, data_type=data_type, data=raw[1:], entries=entries)

    @property
    def capabilities(self) -> dict[bytes, bytes | None]:
        """The entries as a dict; a token without a value maps to None."""
        return dict(self.entries)

    def __bytes__(self) -> bytes:
        return b"<" + b",".join(
            key if value is None else key + b"=" + value for key, value in self.entries
        )


GRID = re.compile(rb"\[([A-Ra-r]{2}[0-9]{2}(?:[A-Xa-x]{2})?)\]")


def grid_to_lat_long(grid: bytes | str) -> tuple[Decimal, Decimal]:
    """
    The centre of a 4 or 6 character Maidenhead grid square.

    >>> [round(v, 4) for v in grid_to_lat_long("IO91SX")]
    [Decimal('51.9792'), Decimal('-0.4583')]
    """
    text = grid.decode("ascii") if isinstance(grid, bytes) else grid
    text = text.upper()
    if not re.fullmatch(r"[A-R]{2}[0-9]{2}(?:[A-X]{2})?", text):
        raise ValueError(f"{grid!r} is not a Maidenhead grid square")
    long = Decimal((ord(text[0]) - 65) * 20 - 180 + int(text[2]) * 2)
    lat = Decimal((ord(text[1]) - 65) * 10 - 90 + int(text[3]))
    if len(text) == 6:
        long += (ord(text[4]) - 65) * Decimal(5) / 60 + Decimal(5) / 120
        lat += (ord(text[5]) - 65) * Decimal("2.5") / 60 + Decimal("2.5") / 120
    else:
        long += 1
        lat += Decimal("0.5")
    return lat, long


@define(frozen=True, slots=True, kw_only=True)
class MaidenheadReport(InformationField):
    """
    A Maidenhead grid locator beacon (APRS101 p. 43): ``[IO91SX] comment``.

    >>> report = MaidenheadReport.from_bytes(b"[IO91SX] 35 miles NNW of London")
    >>> report.grid, report.comment
    (b'IO91SX', b' 35 miles NNW of London')
    """

    grid: bytes = field(default=b"")

    __data_type__ = [DataType.MAIDENHEAD_GRID_LOCATOR_BEACON]
    __raw_fallback__ = True

    @classmethod
    def from_bytes(cls, raw: bytes) -> "MaidenheadReport":
        data_type = _check_data_type(cls, raw)
        match = GRID.match(raw)
        if match is None:
            raise ValueError(f"{raw!r} is not a grid locator beacon")
        return cls(
            raw=raw,
            data_type=data_type,
            data=raw[: match.end()],
            grid=match.group(1),
            comment=raw[match.end() :],
        )

    @property
    def lat(self) -> Decimal:
        """Latitude of the centre of the grid square."""
        return grid_to_lat_long(self.grid)[0]

    @property
    def long(self) -> Decimal:
        """Longitude of the centre of the grid square."""
        return grid_to_lat_long(self.grid)[1]

    def __bytes__(self) -> bytes:
        return b"[%s]%s" % (self.grid, self.comment)


@define(frozen=True, slots=True, kw_only=True)
class UserDefinedReport(InformationField):
    """
    User-defined data (APRS101 p. 87): ``{`` + user ID + packet type + data.

    >>> report = UserDefinedReport.from_bytes(b"{Q1qwerty")
    >>> report.user_id, report.packet_type, report.payload
    (b'Q', b'1', b'qwerty')
    """

    user_id: bytes = field(default=b"")
    """One character naming the program, e.g. b"Q" for Q-type."""
    packet_type: bytes = field(default=b"")
    """One character: the program's own packet type."""
    payload: bytes = field(default=b"")

    __data_type__ = [DataType.USER_DEFINED]
    __raw_fallback__ = True

    @classmethod
    def from_bytes(cls, raw: bytes) -> "UserDefinedReport":
        data_type = _check_data_type(cls, raw)
        if len(raw) < 3:
            raise ValueError(f"{raw!r} has no user ID and packet type")
        return cls(
            raw=raw,
            data_type=data_type,
            data=raw[1:3],
            user_id=raw[1:2],
            packet_type=raw[2:3],
            payload=raw[3:],
        )

    def __bytes__(self) -> bytes:
        return b"{%s%s%s" % (self.user_id[:1], self.packet_type[:1], self.payload)


@define(frozen=True, slots=True, kw_only=True)
class ThirdPartyReport(InformationField):
    """
    Third-party traffic (APRS101 ch. 17): another station's packet, wrapped.

    Igates gating APRS-IS to RF send these. ``frame`` is the inner packet,
    an ``APRSFrame`` with its own source, path and decoded info.

    >>> report = ThirdPartyReport.from_bytes(b"}W1AW>APRS,TCPIP,N0CALL*::N0CALL   :hi{1")
    >>> str(report.frame.source), report.frame.info.text
    ('W1AW', b'hi')
    """

    frame: APRSFrame = field(kw_only=True)

    __data_type__ = [DataType.THIRD_PARTY_TRAFFIC]
    __raw_fallback__ = True

    @classmethod
    def from_bytes(cls, raw: bytes) -> "ThirdPartyReport":
        data_type = _check_data_type(cls, raw)
        header, colon, _ = raw[1:].partition(b":")
        if not colon or b">" not in header:
            raise ValueError(f"{raw!r} has no inner TNC2 header")
        frame = APRSFrame.from_str(raw[1:].decode("latin1"))
        return cls(raw=raw, data_type=data_type, data=raw[1:], frame=frame)._keep_source(
            raw
        )

    def __bytes__(self) -> bytes:
        if self._source is not None:
            return self._source
        return b"}" + str(self.frame).encode("latin1")
