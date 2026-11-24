"""Raw NMEA position sentences ($GPRMC, $GPGGA ...): APRS101 ch. 7."""

import datetime
import functools
import re
from decimal import Decimal

from attrs import define, field

from .classes import DataType, DataTypeError, InformationField

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2026 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"

SENTENCE = re.compile(rb"\$([A-Z]{2}[A-Z]{3}(?:,[^*\r\n]*)?)(?:\*([0-9A-Fa-f]{2}))?")
"""``$`` + talker and type (GPRMC) + fields, and an optional ``*hh`` checksum."""


def nmea_checksum(body: bytes) -> bytes:
    """
    The two hex digits of an NMEA checksum: the XOR of the bytes between
    ``$`` and ``*``.

    >>> nmea_checksum(b"GPGLL,4916.45,N,12311.12,W,225444,A")
    b'31'
    """
    return b"%02X" % functools.reduce(lambda a, b: a ^ b, body, 0)


def _coordinate(value: bytes, hemisphere: bytes, degree_digits: int) -> Decimal | None:
    if not value or not hemisphere:
        return None
    degrees = int(value[:degree_digits])
    minutes = Decimal(value[degree_digits:].decode("ascii"))
    if minutes >= 60:
        raise ValueError(f"{value!r}: minutes out of range")
    coordinate = degrees + minutes / 60
    if hemisphere in (b"S", b"W"):
        return -coordinate
    if hemisphere not in (b"N", b"E"):
        raise ValueError(f"{hemisphere!r} is not a hemisphere")
    return coordinate


def _time(value: bytes) -> datetime.time | None:
    if len(value) < 6:
        return None
    hour, minute, second = int(value[0:2]), int(value[2:4]), Decimal(value[4:].decode())
    return datetime.time(
        hour,
        minute,
        int(second),
        int((second % 1) * 1_000_000),
        tzinfo=datetime.UTC,
    )


def _decimal(value: bytes) -> Decimal | None:
    return Decimal(value.decode("ascii")) if value else None


@define(frozen=True, slots=True)
class NMEAReport(InformationField):
    """
    A raw NMEA sentence from a GPS (APRS101 ch. 7).

    The sentence is kept as sent; ``lat``, ``long``, ``course``,
    ``speed_knots``, ``altitude_m``, ``time`` and ``date`` are decoded from
    GGA, RMC, GLL and VTG sentences where present (None otherwise). A
    sentence with a wrong ``*hh`` checksum is not decoded.

    >>> report = NMEAReport.from_bytes(
    ...     b"$GPGLL,4916.45,N,12311.12,W,225444,A*31"
    ... )
    >>> report.sentence_type, round(report.lat, 4), round(report.long, 4)
    (b'GPGLL', Decimal('49.2742'), Decimal('-123.1853'))
    """

    sentence: bytes = field(default=b"")
    """The sentence between ``$`` and ``*``, e.g. b"GPRMC,063909,A,...".
    """
    checksum: bytes | None = field(default=None)
    """The ``*hh`` checksum digits as sent, or None if there were none."""

    __data_type__ = [DataType.RAW_GPS_DATA]
    __raw_fallback__ = True

    @classmethod
    def from_sentence(cls, sentence: bytes | str, comment: bytes = b"") -> "NMEAReport":
        """Build a report for ``sentence`` (without ``$`` and ``*hh``), adding the checksum."""
        body = sentence.encode("ascii") if isinstance(sentence, str) else sentence
        return cls(
            raw=b"",
            data_type=DataType.RAW_GPS_DATA,
            data=b"",
            sentence=body,
            checksum=nmea_checksum(body),
            comment=comment,
        )

    @classmethod
    def from_bytes(cls, raw: bytes) -> "NMEAReport":
        data_type = DataType(raw[0:1])
        if data_type not in cls.__data_type__:
            raise DataTypeError(
                f"{data_type!r} cannot be handled by {cls!r} (expecting {cls.__data_type__!r})",
            )
        match = SENTENCE.match(raw)
        if match is None:
            raise ValueError(f"{raw!r} is not an NMEA sentence")
        sentence, checksum = match.groups()
        if checksum is not None and nmea_checksum(sentence) != checksum.upper():
            raise ValueError(f"{raw!r}: NMEA checksum mismatch")
        report = cls(
            raw=raw,
            data_type=data_type,
            data=raw[: match.end()],
            sentence=sentence,
            checksum=checksum,
            comment=raw[match.end() :],
        )
        report._decoded()  # reject sentences whose fields don't parse
        return report

    def __bytes__(self) -> bytes:
        return b"".join(
            [
                b"$",
                self.sentence,
                b"" if self.checksum is None else b"*" + self.checksum,
                self.comment,
            ]
        )

    @property
    def sentence_type(self) -> bytes:
        """Talker and sentence type, e.g. b"GPRMC"."""
        return self.sentence.partition(b",")[0]

    @property
    def fields(self) -> list[bytes]:
        """The comma-separated fields after the sentence type."""
        return self.sentence.split(b",")[1:]

    def _decoded(self) -> dict:
        kind, f = self.sentence_type[2:], self.fields + [b""] * 12
        try:
            if kind == b"GGA":
                return dict(
                    time=_time(f[0]),
                    lat=_coordinate(f[1], f[2], 2),
                    long=_coordinate(f[3], f[4], 3),
                    fix_quality=int(f[5]) if f[5] else None,
                    satellites=int(f[6]) if f[6] else None,
                    altitude_m=_decimal(f[8]),
                    valid=f[5] not in (b"", b"0"),
                )
            if kind == b"RMC":
                date = None
                if len(f[8]) == 6:
                    day, month, year = int(f[8][:2]), int(f[8][2:4]), int(f[8][4:])
                    # two-digit years: 1980-2079, like most GPS receivers
                    date = datetime.date(
                        year + (1900 if year >= 80 else 2000), month, day
                    )
                return dict(
                    time=_time(f[0]),
                    valid=f[1] == b"A",
                    lat=_coordinate(f[2], f[3], 2),
                    long=_coordinate(f[4], f[5], 3),
                    speed_knots=_decimal(f[6]),
                    course=_decimal(f[7]),
                    date=date,
                )
            if kind == b"GLL":
                return dict(
                    lat=_coordinate(f[0], f[1], 2),
                    long=_coordinate(f[2], f[3], 3),
                    time=_time(f[4]),
                    valid=f[5] != b"V",
                )
            if kind == b"VTG":
                return dict(course=_decimal(f[0]), speed_knots=_decimal(f[4]))
        except (ArithmeticError, ValueError, IndexError) as exc:
            raise ValueError(f"{self.sentence!r}: {exc}") from exc
        return {}

    @property
    def lat(self) -> Decimal | None:
        """Latitude in decimal degrees (GGA, RMC, GLL)."""
        return self._decoded().get("lat")

    @property
    def long(self) -> Decimal | None:
        """Longitude in decimal degrees (GGA, RMC, GLL)."""
        return self._decoded().get("long")

    @property
    def course(self) -> Decimal | None:
        """Course over ground, degrees true (RMC, VTG)."""
        return self._decoded().get("course")

    @property
    def speed_knots(self) -> Decimal | None:
        """Speed over ground in knots (RMC, VTG)."""
        return self._decoded().get("speed_knots")

    @property
    def altitude_m(self) -> Decimal | None:
        """Altitude above mean sea level in metres (GGA)."""
        return self._decoded().get("altitude_m")

    @property
    def time(self) -> datetime.time | None:
        """UTC time of the fix (GGA, RMC, GLL)."""
        return self._decoded().get("time")

    @property
    def date(self) -> datetime.date | None:
        """UTC date of the fix (RMC)."""
        return self._decoded().get("date")

    @property
    def timestamp(self) -> datetime.datetime | None:
        """UTC date and time of an RMC fix."""
        date, time = self.date, self.time
        if date is None or time is None:
            return None
        return datetime.datetime.combine(date, time)

    @property
    def valid(self) -> bool | None:
        """Whether the receiver reports a valid fix; None for VTG and others."""
        return self._decoded().get("valid")
