"""Encoders and decoders for Data extension structures"""

import math
import re
from abc import ABC, abstractmethod
from typing import Union

from attrs import define, field

from .util import attrs_subclasses

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


@define(frozen=True, slots=True)
class DataExt(ABC):
    @classmethod
    @abstractmethod
    def try_parse(cls, raw: bytes) -> bool:
        """Return True if this subclass might be able to parse raw bytes."""

    @classmethod
    def from_bytes(cls, raw: bytes) -> Union["DataExt", bytes]:
        for subcls in attrs_subclasses(cls):
            if subcls.try_parse(raw):
                try:
                    return subcls.from_bytes(raw[:7])
                except ValueError:
                    pass
        return b""

    @classmethod
    def split_parse(cls, raw: bytes) -> tuple[Union["DataExt", bytes], bytes]:
        parsed = cls.from_bytes(raw)
        if parsed:
            return parsed, raw[7:]
        return b"", raw

    @abstractmethod
    def __bytes__(self) -> bytes:
        """Serialize the data extension as bytes."""


def _valid_course(instance, attribute, value):
    # APRS101 p27: 001-360 degrees, 360 is due north and 000 means unknown
    if not 0 <= value <= 360:
        raise ValueError(f"course must be between 0 and 360, got {value!r}")


@define(frozen=True, slots=True)
class CourseSpeed(DataExt):
    course: int = field(default=0, validator=_valid_course)
    speed: float = field(default=0)
    """Knots: whole knots from text, a float from compressed cs bytes."""

    @classmethod
    def try_parse(cls, raw: bytes) -> bool:
        """Return True if this subclass might be able to parse raw bytes."""
        return re.match(rb"[0-9]{3}/", raw[:4]) is not None

    @classmethod
    def from_bytes(cls, raw: bytes) -> "CourseSpeed":
        course, slash, speed = raw[:7].partition(b"/")
        if not slash or len(course) != len(speed):
            raise ValueError(f"{raw!r} is not a Course/Speed extension field")
        return cls(
            course=int(course.decode("ascii")),
            speed=int(speed.decode("ascii")),
        )

    def __bytes__(self) -> bytes:
        return b"%03d/%03d" % (self.course, (self.speed % 1000))


@define(frozen=True, slots=True)
class PHG(DataExt):
    """
    PHGphgd
    """

    power_w: int = field(default=0)
    height_ft: int = field(default=0)
    gain_db: int = field(default=0)
    directivity: int = field(default=0)

    @classmethod
    def try_parse(cls, raw: bytes) -> bool:
        """Return True if this subclass might be able to parse raw bytes."""
        return raw.startswith(b"PHG")

    @classmethod
    def from_bytes(cls, raw: bytes) -> "PHG":
        if not raw.startswith(b"PHG"):
            raise ValueError(f"{raw!r} is not a PHG extension field")
        power_code, height_code, gain_code, directivity_code = raw[3:7]
        zero_byte = ord(b"0")
        return cls(
            power_w=int(power_code - zero_byte) ** 2,
            height_ft=10 * (2 ** int(height_code - zero_byte)),
            gain_db=int(gain_code - zero_byte),
            directivity=int(directivity_code - zero_byte) * 45,
        )

    def __bytes__(self) -> bytes:
        power_code = int(round(math.sqrt(self.power_w))) % 10
        height_code = bytes([ord(b"0") + int(round(math.log2(self.height_ft / 10)))])
        gain_code = self.gain_db % 10
        directivity_code = int(round(self.directivity / 45)) % 10
        return b"PHG%d%b%d%d" % (power_code, height_code, gain_code, directivity_code)


@define(frozen=True, slots=True)
class RNG(DataExt):
    """
    RNGrrrr
    """

    range: int = field(default=0)

    @classmethod
    def try_parse(cls, raw: bytes) -> bool:
        """Return True if this subclass might be able to parse raw bytes."""
        return raw.startswith(b"RNG")

    @classmethod
    def from_bytes(cls, raw: bytes) -> "RNG":
        if not raw.startswith(b"RNG"):
            raise ValueError(f"{raw!r} is not a RNG extension field")
        return cls(range=int(raw[3:7]))

    def __bytes__(self) -> bytes:
        return b"RNG%04d" % (self.range % 10000)


@define(frozen=True, slots=True)
class DFS(DataExt):
    """
    DFSshgd
    """

    strength_s: int = field(default=0)
    height_ft: int = field(default=0)
    gain_db: int = field(default=0)
    directivity: int = field(default=0)

    @classmethod
    def try_parse(cls, raw: bytes) -> bool:
        """Return True if this subclass might be able to parse raw bytes."""
        return raw.startswith(b"DFS")

    @classmethod
    def from_bytes(cls, raw: bytes) -> "DFS":
        if not raw.startswith(b"DFS"):
            raise ValueError(f"{raw!r} is not a DFS extension field")
        strength_code, height_code, gain_code, directivity_code = raw[3:7]
        zero_byte = ord(b"0")
        return cls(
            strength_s=int(strength_code - zero_byte),
            height_ft=10 * (2 ** int(height_code - zero_byte)),
            gain_db=int(gain_code - zero_byte),
            directivity=int(directivity_code - zero_byte) * 45,
        )

    def __bytes__(self) -> bytes:
        strength_code = bytes([ord(b"0") + self.strength_s])
        height_code = bytes([ord(b"0") + int(round(math.log2(self.height_ft / 10)))])
        gain_code = self.gain_db % 10
        directivity_code = int(round(self.directivity / 45)) % 10
        return b"DFS%b%b%d%d" % (
            strength_code,
            height_code,
            gain_code,
            directivity_code,
        )


@define(frozen=True, slots=True)
class AreaObject(DataExt):
    """
    Tyy/Cxx
    """

    t: bytes = field(default=b"")
    c: bytes = field(default=b"")

    @classmethod
    def try_parse(cls, raw: bytes) -> bool:
        """Return True if this subclass might be able to parse raw bytes."""
        return re.match(rb"T../C..", raw[:7]) is not None

    @classmethod
    def from_bytes(cls, raw: bytes) -> "AreaObject":
        if not re.match(rb"T../C..", raw[:7]):
            raise ValueError(f"{raw!r} is not an Area Object extension field")
        return cls(
            t=raw[1:3],
            c=raw[5:7],
        )

    def __bytes__(self) -> bytes:
        return b"T% 2b/C% 2b" % (self.t[:2], self.c[:2])
