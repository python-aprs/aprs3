"""Internal helpers."""

from collections.abc import Iterator
from typing import TypeVar

_T = TypeVar("_T")


def dataclass_subclasses(cls: type[_T]) -> Iterator[type[_T]]:
    """
    Yield the direct subclasses of ``cls`` that are themselves dataclasses.

    Decoder dispatch only considers subclasses that declare their own
    fields with ``@dataclass``; an undecorated subclass would construct
    with its parent's ``__init__`` and is skipped.
    """
    for subcls in cls.__subclasses__():
        if "__dataclass_fields__" in subcls.__dict__:
            yield subcls
