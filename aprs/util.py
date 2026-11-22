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

    ``@dataclass(slots=True)`` builds a new class and discards the one it
    decorated, but the discarded class stays in ``cls.__subclasses__()``
    (still marked as a dataclass) until the cyclic garbage collector runs.
    Dispatching to it builds an instance with a ``__dict__`` and none of the
    slotted class's identity, so when two subclasses share a module and
    qualified name, only the slotted one is yielded.
    """
    candidates = [c for c in cls.__subclasses__() if "__dataclass_fields__" in c.__dict__]
    slotted = {
        (c.__module__, c.__qualname__) for c in candidates if "__slots__" in c.__dict__
    }
    for subcls in candidates:
        key = (subcls.__module__, subcls.__qualname__)
        if key in slotted and "__slots__" not in subcls.__dict__:
            continue  # pre-slots leftover of a slots=True dataclass
        yield subcls
