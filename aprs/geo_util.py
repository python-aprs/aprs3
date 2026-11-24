"""Python APRS Module Geo Utility Function Definitions."""

import decimal
import math

from . import decimaldegrees

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"
__copyright__ = "Copyright 2017 Greg Albrecht and Contributors"
__license__ = "Apache License, Version 2.0"


def _is_negative(dec) -> bool:
    """True for negative values, including -0 (e.g. a decoded "0000.00W")."""
    if isinstance(dec, decimal.Decimal):
        return dec.is_signed()
    return math.copysign(1.0, float(dec)) < 0


def _dm(dec) -> tuple[int, decimal.Decimal]:
    """Absolute degrees and minutes rounded to 0.01, carrying 60 minutes."""
    degrees, minutes = decimaldegrees.decimal2dm(abs(decimal.Decimal(str(dec))))
    minutes = minutes.quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP)
    if minutes >= 60:
        degrees, minutes = degrees + 1, minutes - 60
    return int(degrees), minutes


def dec2dm_lat(dec: float | decimal.Decimal) -> bytes:
    """
    Converts decimal degrees to APRS latitude format (DDMM.mmN).

    Example:
        >>> dec2dm_lat(37.7418096)
        b'3744.51N'
        >>> dec2dm_lat(-8.01)
        b'0800.60S'
        >>> dec2dm_lat(-0.5)
        b'0030.00S'
    """
    degrees, minutes = _dm(dec)
    suffix = b"S" if _is_negative(dec) else b"N"
    return b"%02d%05.2f%s" % (degrees, minutes, suffix)


def dec2dm_lng(dec: float | decimal.Decimal) -> bytes:
    """
    Converts decimal degrees to APRS longitude format (DDDMM.mmE).

    Example:
        >>> dec2dm_lng(122.38833)
        b'12223.30E'
        >>> dec2dm_lng(-99.01)
        b'09900.60W'
        >>> dec2dm_lng(-0.0)
        b'00000.00W'
        >>> dec2dm_lng(-72.99999999)
        b'07300.00W'
    """
    degrees, minutes = _dm(dec)
    suffix = b"W" if _is_negative(dec) else b"E"
    return b"%03d%05.2f%s" % (degrees, minutes, suffix)


def ambiguate(pos: bytes, ambiguity: int | None) -> bytes:
    """
    Adjust ambiguity of position.

    Derived from @asdil12's `process_ambiguity()`.

    >>> pos = b'12345.67N'
    >>> ambiguate(pos, 0)
    b'12345.67N'
    >>> ambiguate(pos, 1)
    b'12345.6 N'
    >>> ambiguate(pos, 2)
    b'12345.  N'
    >>> ambiguate(pos, 3)
    b'1234 .  N'
    """
    if not isinstance(pos, bytes):
        pos = str(pos).encode("ascii")
    if not ambiguity:
        return pos
    amb = bytearray(pos)
    for ix in range(len(amb) - 1, -1, -1):
        if not ambiguity:
            break
        if 0x30 <= amb[ix] <= 0x39:  # a digit
            amb[ix] = 0x20  # space
            ambiguity -= 1
    return bytes(amb)


def deambiguate(pos: bytes) -> int:
    """
    Return the ambiguity of the position

    >>> deambiguate(b'12345.67N')
    0
    >>> deambiguate(b'12345.6 N')
    1
    >>> deambiguate(b'12345.  N')
    2
    >>> deambiguate(b'1234 .  N')
    3
    """
    return pos.count(b" ")


def run_doctest():  # pragma: no cover
    """Runs doctests for this module."""
    import doctest  # pylint: disable=import-outside-toplevel

    return doctest.testmod()


if __name__ == "__main__":
    run_doctest()  # pragma: no cover
