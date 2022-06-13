"""Python APRS Module Geo Utility Function Definitions."""
from . import decimaldegrees

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"
__copyright__ = "Copyright 2017 Greg Albrecht and Contributors"
__license__ = "Apache License, Version 2.0"


def dec2dm_lat(dec: float) -> bytes:
    """
    Converts DecDeg to APRS Coord format.

    See: http://ember2ash.com/lat.htm

    Source: http://stackoverflow.com/questions/2056750

    Example:
        >>> test_lat = 37.7418096
        >>> aprs_lat = dec2dm_lat(test_lat)
        >>> aprs_lat
        '3744.51N'
        >>> test_lat = -8.01
        >>> aprs_lat = dec2dm_lat(test_lat)
        >>> aprs_lat
        '0800.60S'
    """
    dec_min = decimaldegrees.decimal2dm(dec)

    deg = dec_min[0]
    abs_deg = abs(deg)

    if not deg == abs_deg:
        suffix = b"S"
    else:
        suffix = b"N"

    return b"%02d%05.2f%s" % (abs_deg, dec_min[1], suffix)


def dec2dm_lng(dec: float) -> bytes:
    """
    Converts DecDeg to APRS Coord format.

    See: http://ember2ash.com/lat.htm

    Example:
        >>> test_lng = 122.38833
        >>> aprs_lng = dec2dm_lng(test_lng)
        >>> aprs_lng
        '12223.30E'
        >>> test_lng = -99.01
        >>> aprs_lng = dec2dm_lng(test_lng)
        >>> aprs_lng
        '09900.60W'
    """
    dec_min = decimaldegrees.decimal2dm(dec)

    deg = dec_min[0]
    abs_deg = abs(deg)

    if not deg == abs_deg:
        suffix = b"W"
    else:
        suffix = b"E"

    return b"%03d%05.2f%s" % (abs_deg, dec_min[1], suffix)


def ambiguate(pos: bytes, ambiguity: int) -> bytes:
    """
    Adjust ambiguity of position.

    Derived from @asdil12's `process_ambiguity()`.

    >>> pos = '12345.67N'
    >>> ambiguate(pos, 0)
    '12345.67N'
    >>> ambiguate(pos, 1)
    '12345.6 N'
    >>> ambiguate(pos, 2)
    '12345.  N'
    >>> ambiguate(pos, 3)
    '1234 .  N'
    """
    if not isinstance(pos, bytes):
        pos = str(pos).encode("ascii")
    amb = []
    for b in reversed(pos):
        if ord(b"0") <= b <= ord(b"9") and ambiguity:
            amb.append(ord(b" "))
            ambiguity -= 1
            continue
        amb.append(b)
    return bytes(reversed(amb))


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
