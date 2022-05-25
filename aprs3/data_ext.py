"""Encoders and decoders for Data extension structures"""
from abc import ABC, abstractmethod
import math
import re
from typing import Tuple, Union

from attrs import define, field


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
        for subcls in cls.__subclasses__():
            if subcls.try_parse(raw):
                try:
                    return subcls.from_bytes(raw[:7])
                except ValueError:
                    pass
        return b""

    @classmethod
    def split_parse(cls, raw: bytes) -> Tuple[Union["DataExt", bytes], bytes]:
        parsed = cls.from_bytes(raw)
        if parsed:
            return parsed, raw[7:]
        return b"", raw

    @abstractmethod
    def __bytes__(self) -> bytes:
        """Serialize the data extension as bytes."""


@define(frozen=True, slots=True)
class CourseSpeed(DataExt):
    course: int = field(default=0)
    speed: int = field(default=0)

    @classmethod
    def try_parse(cls, raw: bytes) -> bool:
        """Return True if this subclass might be able to parse raw bytes."""
        return re.match(rb"[0-9]{3}/", raw[:4])

    @classmethod
    def from_bytes(cls, raw: bytes) -> "CourseSpeed":
        course, slash, speed = raw[:7].partition(b"/")
        if not slash or len(course) != len(speed):
            raise ValueError("{!r} is not a Course/Speed extension field".format(raw))
        return cls(
            course=int(course.decode("ascii")),
            speed=int(speed.decode("ascii")),
        )

    def __bytes__(self) -> bytes:
        return b"%03d/%03d" % ((self.course % 360), (self.speed % 1000))


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
            raise ValueError("{!r} is not a PHG extension field".format(raw))
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
            raise ValueError("{!r} is not a RNG extension field".format(raw))
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
            raise ValueError("{!r} is not a DFS extension field".format(raw))
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
        return re.match(rb"T../C..", raw[:7])

    @classmethod
    def from_bytes(cls, raw: bytes) -> "AreaObject":
        if not re.match(rb"T../C..", raw[:7]):
            raise ValueError("{!r} is not an Area Object extension field".format(raw))
        return cls(
            t=raw[1:3],
            c=raw[5:7],
        )

    def __bytes__(self) -> bytes:
        return b"T% 2b/C% 2b" % (self.t[:2], self.c[:2])
