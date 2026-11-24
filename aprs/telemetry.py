"""Telemetry reports, their metadata messages and base91 comment telemetry (APRS101 ch. 13)."""

import re
from collections.abc import Iterable, Sequence
from decimal import Decimal, InvalidOperation

from attrs import define, field

from .base91 import from_decimal, to_decimal
from .classes import DataType, DataTypeError, InformationField, Message

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2026 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"

ANALOG_CHANNELS = 5
DIGITAL_CHANNELS = 8
BITS = re.compile(rb"[01]{8}")


def _number(text: bytes) -> Decimal:
    try:
        value = Decimal(text.strip().decode("ascii"))
    except (InvalidOperation, UnicodeDecodeError) as exc:
        raise ValueError(f"{text!r} is not a number") from exc
    if not value.is_finite():
        raise ValueError(f"{text!r} is not a number")
    return value


def _format_number(value: Decimal | float | int) -> bytes:
    value = Decimal(str(value)) if isinstance(value, float) else Decimal(value)
    if value == value.to_integral_value() and 0 <= value <= 999:
        return b"%03d" % int(value)
    return format(value.normalize(), "f").encode("ascii")


def _bits(text: bytes) -> tuple[bool, ...]:
    if not BITS.fullmatch(text):
        raise ValueError(f"{text!r} is not 8 binary digits")
    return tuple(c == ord("1") for c in text)


def _format_bits(bits: Sequence[bool]) -> bytes:
    if len(bits) != DIGITAL_CHANNELS:
        raise ValueError(f"expected {DIGITAL_CHANNELS} bits, got {len(bits)}")
    return bytes(b"1"[0] if b else b"0"[0] for b in bits)


@define(frozen=True, slots=True, kw_only=True)
class TelemetryReport(InformationField):
    """
    A telemetry report: ``T#sss,a1,a2,a3,a4,a5,bbbbbbbb`` (APRS101 p. 68).

    ``analog`` holds up to five raw values (scale them with the station's
    ``EQNS.`` message: ``TelemetryEquations.apply``) and ``digital`` the
    eight bits, or None if the report has none.

    >>> report = TelemetryReport.from_bytes(b"T#005,199,000,255,073,123,01101001")
    >>> report.sequence, [int(v) for v in report.analog], report.digital[:3]
    (b'005', [199, 0, 255, 73, 123], (False, True, True))
    """

    sequence: bytes = field(default=b"000")
    """The sequence number as sent: usually 3 digits, or b"MIC"."""
    analog: tuple[Decimal, ...] = field(default=(), converter=lambda v: tuple(v))
    digital: tuple[bool, ...] | None = field(
        default=None, converter=lambda v: None if v is None else tuple(bool(b) for b in v)
    )

    __data_type__ = [DataType.TELEMETRY_DATA]
    __raw_fallback__ = True

    @classmethod
    def new(
        cls,
        sequence: int | str | bytes,
        analog: Iterable[Decimal | float | int],
        digital: Sequence[bool | int] | None = None,
        comment: bytes = b"",
    ) -> "TelemetryReport":
        """
        Build a telemetry report to send.

        >>> bytes(TelemetryReport.new(7, [1, 2.5, 300, 0, 0], [1, 0, 0, 0, 0, 0, 0, 1]))
        b'T#007,001,2.5,300,000,000,10000001'
        """
        if isinstance(sequence, int):
            sequence = b"%03d" % (sequence % 1000)
        elif isinstance(sequence, str):
            sequence = sequence.encode("ascii")
        analog = tuple(
            Decimal(str(v)) if isinstance(v, float) else Decimal(v) for v in analog
        )
        if len(analog) > ANALOG_CHANNELS:
            raise ValueError(f"at most {ANALOG_CHANNELS} analog values")
        if digital is not None and len(analog) != ANALOG_CHANNELS:
            raise ValueError(f"digital bits need all {ANALOG_CHANNELS} analog values")
        return cls(
            raw=b"",
            data_type=DataType.TELEMETRY_DATA,
            data=b"",
            sequence=sequence,
            analog=analog,
            digital=digital,
            comment=comment,
        )

    @classmethod
    def from_bytes(cls, raw: bytes) -> "TelemetryReport":
        data_type = DataType(raw[0:1])
        if data_type not in cls.__data_type__:
            raise DataTypeError(
                f"{data_type!r} cannot be handled by {cls!r} (expecting {cls.__data_type__!r})",
            )
        if raw[1:2] != b"#":
            raise ValueError(f"{raw!r} is not a T# telemetry report")
        body = raw[2:]
        if body.startswith(b"MIC"):
            sequence, body = b"MIC", body[3:].removeprefix(b",")
        else:
            sequence, comma, body = body.partition(b",")
            if not comma or not sequence.isdigit():
                raise ValueError(f"{raw!r}: bad telemetry sequence number")
        parts = body.split(b",", ANALOG_CHANNELS)
        digital, comment = None, b""
        if len(parts) == ANALOG_CHANNELS + 1:
            last = parts.pop()
            digital, comment = _bits(last[:DIGITAL_CHANNELS]), last[DIGITAL_CHANNELS:]
        analog = tuple(_number(p) for p in parts if p.strip() or len(parts) > 1)
        return cls(
            raw=raw,
            data_type=data_type,
            data=raw[: len(raw) - len(comment)],
            sequence=sequence,
            analog=analog,
            digital=digital,
            comment=comment,
        )._keep_source(raw)

    def __bytes__(self) -> bytes:
        if self._source is not None:
            return self._source
        values = [_format_number(v) for v in self.analog]
        if self.digital is not None:
            if len(values) != ANALOG_CHANNELS:
                raise ValueError(f"digital bits need all {ANALOG_CHANNELS} analog values")
            values.append(_format_bits(self.digital) + self.comment)
        return b"T#%s,%s%s" % (
            self.sequence,
            b",".join(values),
            b"" if self.digital is not None else self.comment,
        )

    def scaled(self, equations: "TelemetryEquations") -> tuple[Decimal, ...]:
        """The analog values with the station's ``EQNS.`` applied."""
        return equations.apply(self.analog)


# --- metadata messages (PARM. UNIT. EQNS. BITS.) ---------------------------------


def _split_list(text: bytes) -> tuple[bytes, ...]:
    return tuple(text.split(b",")) if text else ()


@define(frozen=True, slots=True)
class TelemetryNames:
    """``PARM.`` names for the 5 analog and 8 digital channels.

    >>> TelemetryNames.from_text(b"PARM.Battery,Temp").names
    (b'Battery', b'Temp')
    """

    names: tuple[bytes, ...] = field(converter=tuple)
    PREFIX = b"PARM."

    @classmethod
    def from_text(cls, text: bytes) -> "TelemetryNames":
        return cls(_split_list(text.removeprefix(cls.PREFIX)))

    def __bytes__(self) -> bytes:
        return self.PREFIX + b",".join(self.names)

    def to_message(self, addressee: str | bytes) -> Message:
        """The message that sends this metadata; address it to the station itself."""
        return Message.new(addressee, bytes(self))


@define(frozen=True, slots=True)
class TelemetryUnits:
    """``UNIT.`` units (or labels) for the 5 analog and 8 digital channels."""

    units: tuple[bytes, ...] = field(converter=tuple)
    PREFIX = b"UNIT."

    @classmethod
    def from_text(cls, text: bytes) -> "TelemetryUnits":
        return cls(_split_list(text.removeprefix(cls.PREFIX)))

    def __bytes__(self) -> bytes:
        return self.PREFIX + b",".join(self.units)

    def to_message(self, addressee: str | bytes) -> Message:
        """The message that sends this metadata; address it to the station itself."""
        return Message.new(addressee, bytes(self))


def _coefficients(
    value: Iterable[Iterable[Decimal | float | int | str]],
) -> tuple[tuple[Decimal, Decimal, Decimal], ...]:
    result = []
    for abc in value:
        a, b, c = (Decimal(str(v)) for v in abc)
        result.append((a, b, c))
    return tuple(result)


@define(frozen=True, slots=True)
class TelemetryEquations:
    """
    ``EQNS.`` coefficients (a, b, c) per analog channel: value = a·x² + b·x + c.

    >>> eqns = TelemetryEquations.from_text(b"EQNS.0,5.2,0,0,.53,-32,3,4.39,49,-32,3,18,1,2,3")
    >>> [str(v) for v in eqns.apply([1, 1, 1, 1, 1])]
    ['5.2', '-31.47', '56.39', '-11', '6']
    """

    coefficients: tuple[tuple[Decimal, Decimal, Decimal], ...] = field(
        converter=_coefficients
    )
    PREFIX = b"EQNS."

    @classmethod
    def from_text(cls, text: bytes) -> "TelemetryEquations":
        values = [
            _number(v) if v.strip() else Decimal(0)
            for v in _split_list(text.removeprefix(cls.PREFIX))
        ]
        if len(values) % 3:
            raise ValueError(f"{text!r}: coefficients must come in threes")
        return cls([values[i : i + 3] for i in range(0, len(values), 3)])

    def apply(self, analog: Iterable[Decimal | float | int]) -> tuple[Decimal, ...]:
        """Scale raw analog values; channels without coefficients are unchanged."""
        result = []
        for ix, value in enumerate(analog):
            x = Decimal(str(value)) if isinstance(value, float) else Decimal(value)
            if ix < len(self.coefficients):
                a, b, c = self.coefficients[ix]
                x = a * x * x + b * x + c
            result.append(x)
        return tuple(result)

    def __bytes__(self) -> bytes:
        return self.PREFIX + b",".join(
            format(c.normalize(), "f").encode("ascii")
            for abc in self.coefficients
            for c in abc
        )

    def to_message(self, addressee: str | bytes) -> Message:
        """The message that sends this metadata; address it to the station itself."""
        return Message.new(addressee, bytes(self))


@define(frozen=True, slots=True)
class TelemetryBits:
    """
    ``BITS.`` sense of each digital channel (which value is "on"), and the
    project title.
    """

    bits: tuple[bool, ...] = field(converter=lambda v: tuple(bool(b) for b in v))
    project: bytes = b""
    PREFIX = b"BITS."

    @classmethod
    def from_text(cls, text: bytes) -> "TelemetryBits":
        body = text.removeprefix(cls.PREFIX)
        bits, _, project = body.partition(b",")
        return cls(_bits(bits), project)

    def __bytes__(self) -> bytes:
        return self.PREFIX + _format_bits(self.bits) + b"," + self.project

    def to_message(self, addressee: str | bytes) -> Message:
        """The message that sends this metadata; address it to the station itself."""
        return Message.new(addressee, bytes(self))


TelemetryMetadata = TelemetryNames | TelemetryUnits | TelemetryEquations | TelemetryBits
_METADATA: tuple[type[TelemetryMetadata], ...] = (
    TelemetryNames,
    TelemetryUnits,
    TelemetryEquations,
    TelemetryBits,
)


def telemetry_metadata(message: Message) -> TelemetryMetadata | None:
    """
    Parse a ``PARM.``, ``UNIT.``, ``EQNS.`` or ``BITS.`` message; None for
    other messages or metadata that doesn't parse. Also ``Message.telemetry_metadata``.
    """
    for cls in _METADATA:
        if message.text.startswith(cls.PREFIX):
            try:
                return cls.from_text(message.text)
            except ValueError:
                return None
    return None


# --- base91 telemetry in comments: |ss1122334455bb| ------------------------------

COMMENT_TELEMETRY = re.compile(rb"\|((?:[!-{]{2}){2,7})\|")


@define(frozen=True, slots=True)
class CommentTelemetry:
    """
    Base91 telemetry in a comment (``|ss11223344|``), common from Mic-E and
    compressed-position trackers. Values are 0-8280.

    >>> CommentTelemetry.from_comment(b"Battery |!!!!!+|")
    CommentTelemetry(sequence=0, analog=(0, 10), digital=None)
    """

    sequence: int
    analog: tuple[int, ...] = field(converter=tuple)
    digital: tuple[bool, ...] | None = field(
        default=None, converter=lambda v: None if v is None else tuple(bool(b) for b in v)
    )

    @classmethod
    def from_comment(cls, comment: bytes) -> "CommentTelemetry | None":
        match = COMMENT_TELEMETRY.search(comment)
        if match is None:
            return None
        text = match.group(1).decode("ascii")
        values = [to_decimal(text[i : i + 2]) for i in range(0, len(text), 2)]
        sequence, analog = values[0], values[1:]
        digital = None
        if len(analog) == ANALOG_CHANNELS + 1:
            bits = analog.pop()
            digital = tuple(bool(bits >> i & 1) for i in range(DIGITAL_CHANNELS))
        return cls(sequence, analog, digital)

    def __bytes__(self) -> bytes:
        if not 1 <= len(self.analog) <= ANALOG_CHANNELS:
            raise ValueError(f"1 to {ANALOG_CHANNELS} analog values")
        values = [self.sequence % 8281, *self.analog]
        if self.digital is not None:
            if len(self.analog) != ANALOG_CHANNELS:
                raise ValueError("digital bits need all 5 analog values")
            values.append(sum(1 << i for i, b in enumerate(self.digital) if b))
        return b"|%s|" % "".join(from_decimal(int(v), 2) for v in values).encode("ascii")
