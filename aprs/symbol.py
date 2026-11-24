"""APRS symbols: a table identifier and a symbol code (APRS101 ch. 20)."""

from typing import ClassVar

from attrs import define, field

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


def _one_byte(value: str | bytes) -> bytes:
    data = value.encode("latin-1") if isinstance(value, str) else bytes(value)
    if len(data) != 1:
        raise ValueError(f"a symbol table or code is one character, got {value!r}")
    return data


@define(frozen=True, slots=True)
class Symbol:
    """
    A symbol: the table ("/" primary, "\\" alternate, or an overlay
    character) and the code within it.

    >>> Symbol.from_str("/>")
    Symbol(table=b'/', code=b'>')
    >>> str(Symbol.HOUSE)
    '/-'
    """

    table: bytes = field(default=b"/", converter=_one_byte)
    code: bytes = field(default=b"-", converter=_one_byte)

    # a few common symbols from the primary table (APRS101 appendix 2)
    HOUSE: ClassVar["Symbol"]
    CAR: ClassVar["Symbol"]
    TRUCK: ClassVar["Symbol"]
    PERSON: ClassVar["Symbol"]
    BICYCLE: ClassVar["Symbol"]
    BOAT: ClassVar["Symbol"]
    AIRCRAFT: ClassVar["Symbol"]
    BALLOON: ClassVar["Symbol"]
    WEATHER_STATION: ClassVar["Symbol"]
    DIGIPEATER: ClassVar["Symbol"]

    @classmethod
    def from_str(cls, text: "str | bytes | Symbol") -> "Symbol":
        """Parse two characters, table then code: ``"/>"`` is a car."""
        if isinstance(text, Symbol):
            return text
        data = text.encode("latin-1") if isinstance(text, str) else bytes(text)
        if len(data) != 2:
            raise ValueError(f"a symbol is two characters (table, code), got {text!r}")
        return cls(table=data[:1], code=data[1:])

    def __str__(self) -> str:
        return (self.table + self.code).decode("latin-1")

    def __bytes__(self) -> bytes:
        return self.table + self.code


Symbol.HOUSE = Symbol(b"/", b"-")
Symbol.CAR = Symbol(b"/", b">")
Symbol.TRUCK = Symbol(b"/", b"k")
Symbol.PERSON = Symbol(b"/", b"[")
Symbol.BICYCLE = Symbol(b"/", b"b")
Symbol.BOAT = Symbol(b"/", b"s")
Symbol.AIRCRAFT = Symbol(b"/", b"'")
Symbol.BALLOON = Symbol(b"/", b"O")
Symbol.WEATHER_STATION = Symbol(b"/", b"_")
Symbol.DIGIPEATER = Symbol(b"/", b"#")
