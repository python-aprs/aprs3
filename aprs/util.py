"""Internal helpers."""

from collections.abc import Iterator
from typing import TypeVar

_T = TypeVar("_T")


def attrs_subclasses(cls: type[_T]) -> Iterator[type[_T]]:
    """
    Yield the direct subclasses of ``cls`` that are live attrs classes.

    ``@attrs.define(slots=True)`` builds a new class and discards the one it
    decorated, but the discarded class stays in ``cls.__subclasses__()`` until
    the cyclic garbage collector runs. Its ``__init__`` is the base class's,
    so dispatching to it fails ("unexpected keyword argument") or builds the
    wrong type. Whether a leftover is present depends on GC timing, which made
    decoding fail in some processes and not others.
    """
    for subcls in cls.__subclasses__():
        if "__attrs_attrs__" in subcls.__dict__:
            yield subcls
