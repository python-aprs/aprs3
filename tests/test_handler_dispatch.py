"""InformationField dispatch must survive attrs ``slots=True`` class replacement."""

import gc

from attrs import define

from aprs.classes import DataType, InformationField


def test_find_handler_skips_pre_slots_class():
    """
    ``@define(slots=True)`` builds a new class and leaves the original in
    ``InformationField.__subclasses__()`` until the cyclic GC runs. Dispatch
    must pick the real (slotted) class, never the leftover.

    Before the fix this was order- and GC-timing-dependent: in some processes
    every status report failed to decode with
    ``TypeError: __init__() got an unexpected keyword argument 'timestamp'``.
    """
    gc.disable()
    try:

        @define(frozen=True, slots=True)
        class _UserDefined(InformationField):
            __data_type__ = [DataType.AGRELO_DFJR]

        leftovers = [
            c
            for c in InformationField.__subclasses__()
            if c.__name__ == "_UserDefined" and c is not _UserDefined
        ]
        assert leftovers, "expected attrs to leave the pre-slots class behind"

        InformationField._find_handler.cache_clear()
        assert InformationField._find_handler(DataType.AGRELO_DFJR) is _UserDefined
        decoded = InformationField.from_bytes(b"%XXhello")
        assert type(decoded) is _UserDefined
    finally:
        gc.enable()
        del _UserDefined, leftovers
        gc.collect()
        InformationField._find_handler.cache_clear()


def test_data_ext_skips_pre_slots_class():
    """Same leftover-class hazard for DataExt dispatch (RNG/PHG/DFS/...)."""
    from aprs.data_ext import DataExt

    gc.disable()
    try:

        @define(frozen=True, slots=True)
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

        assert any(
            c.__name__ == "_ZZZ" and c is not _ZZZ for c in DataExt.__subclasses__()
        ), "expected attrs to leave the pre-slots class behind"
        assert DataExt.from_bytes(b"ZZZ0042rest") == _ZZZ(value=42)
    finally:
        gc.enable()
        del _ZZZ
        gc.collect()
