# aprslib - Python library for working with APRS
# Copyright (C) 2013-2014 Rossen Georgiev
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""
Provides facilities for conversion from/to base91

Original source:
https://github.com/rossengeorgiev/aprs-python/blob/2b139d18578e62818adb6fac217a96b622c490f7/aprslib/base91.py
"""

__all__ = ["to_decimal", "from_decimal"]
from math import log, ceil
from re import findall


def to_decimal(text):
    """
    Takes a base91 char string and returns decimal
    """

    if not isinstance(text, str):
        raise TypeError("expected str or unicode, %s given" % type(text))

    if findall(r"[\x00-\x20\x7c-\xff]", text):
        raise ValueError("invalid character in sequence")

    text = text.lstrip("!")
    decimal = 0
    length = len(text) - 1
    for i, char in enumerate(text):
        decimal += (ord(char) - 33) * (91 ** (length - i))

    return decimal if text != "" else 0


def from_decimal(number, width=1):
    """
    Takes a decimal and returns base91 char string.
    With optional parameter for fix with output
    """
    text = []

    if not isinstance(number, int):
        raise TypeError("Expected number to be int, got %s" % type(number))
    if not isinstance(width, int):
        raise TypeError("Expected width to be int, got %s" % type(number))
    if number < 0:
        raise ValueError("Expected number to be positive integer")
    if number > 0:
        max_n = ceil(log(number) / log(91))

        for n in range(int(max_n), -1, -1):
            quotient, number = divmod(number, 91**n)
            text.append(chr(33 + quotient))

    return "".join(text).lstrip("!").rjust(max(1, width), "!")
