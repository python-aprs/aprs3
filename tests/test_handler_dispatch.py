"""Decoder dispatch picks dataclass subclasses of InformationField and DataExt."""

import dataclasses
import gc

from aprs.classes import DataType, InformationField
from aprs.data_ext import DataExt


def test_find_handler_uses_dataclass_subclass():
    @dataclasses.dataclass(frozen=True)
    class _UserDefined(InformationField):
        __data_type__ = [DataType.USER_DEFINED]

    class _Undecorated(InformationField):
        __data_type__ = [DataType.USER_DEFINED]

    try:
        InformationField._find_handler.cache_clear()
        assert InformationField._find_handler(DataType.USER_DEFINED) is _UserDefined
        decoded = InformationField.from_bytes(b"{XXhello")
        assert type(decoded) is _UserDefined
    finally:
        del _UserDefined, _Undecorated
        gc.collect()
        InformationField._find_handler.cache_clear()


def test_data_ext_uses_dataclass_subclass():
    @dataclasses.dataclass(frozen=True)
    class _ZZZ(DataExt):
        value: int = 0

        @classmethod
        def try_parse(cls, raw):
            return raw.startswith(b"ZZZ")

        @classmethod
        def from_bytes(cls, raw):
            return cls(value=int(raw[3:7]))

        def __bytes__(self):
            return b"ZZZ%04d" % self.value

    try:
        assert DataExt.from_bytes(b"ZZZ0042rest") == _ZZZ(value=42)
    finally:
        del _ZZZ
        gc.collect()


def test_find_handler_skips_pre_slots_leftover():
    """
    ``@dataclass(slots=True)`` leaves the class it replaced in
    ``__subclasses__()`` until the cyclic GC runs; dispatch must pick the
    slotted class, never the leftover.
    """
    gc.disable()
    try:

        @dataclasses.dataclass(frozen=True, slots=True)
        class _UserDefined(InformationField):
            __data_type__ = [DataType.USER_DEFINED]

        leftovers = [
            c
            for c in InformationField.__subclasses__()
            if c.__name__ == "_UserDefined" and c is not _UserDefined
        ]
        assert leftovers, "expected dataclasses to leave the pre-slots class behind"
        InformationField._find_handler.cache_clear()
        assert InformationField._find_handler(DataType.USER_DEFINED) is _UserDefined
        assert type(InformationField.from_bytes(b"{XXhello")) is _UserDefined
    finally:
        gc.enable()
        del _UserDefined, leftovers
        gc.collect()
        InformationField._find_handler.cache_clear()


def test_data_ext_skips_pre_slots_leftover():
    gc.disable()
    try:

        @dataclasses.dataclass(frozen=True, slots=True)
        class _YYY(DataExt):
            value: int = 0

            @classmethod
            def try_parse(cls, raw):
                return raw.startswith(b"YYY")

            @classmethod
            def from_bytes(cls, raw):
                return cls(value=int(raw[3:7]))

            def __bytes__(self):
                return b"YYY%04d" % self.value

        assert any(
            c.__name__ == "_YYY" and c is not _YYY for c in DataExt.__subclasses__()
        ), "expected dataclasses to leave the pre-slots class behind"
        parsed = DataExt.from_bytes(b"YYY0042rest")
        assert type(parsed) is _YYY and parsed == _YYY(value=42)
    finally:
        gc.enable()
        del _YYY
        gc.collect()
