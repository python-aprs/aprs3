#!/usr/bin/env python3
"""
Decode APRS packets and print what they say.

Pass TNC2 lines (the format APRS-IS and aprs.fi's raw view use) as arguments,
or pipe them in on stdin::

    $ python aprs_decode.py 'KF7HVM-9>APZ069,WIDE1-1:!4610.00N/12255.00W>090/025/A=000500'
    KF7HVM-9   position 46.16667, -122.91667  symbol />  course 90° 25 kn  500 ft

    $ nc rotate.aprs2.net 10152 | python aprs_decode.py

The ``describe()`` function is also used by ``aprsis_monitor.py``.
"""

import re
import sys
from collections.abc import Iterable

import aprs


def _text(value: bytes | None) -> str:
    return (value or b"").decode("latin1").strip()


def _position(report) -> str:
    out = f"{report.lat:.5f}, {report.long:.5f}"
    out += f"  symbol {_text(report.sym_table_id)}{_text(report.symbol_code)}"
    ext = report.data_ext
    if isinstance(ext, aprs.CourseSpeed):
        out += f"  course {ext.course}° {ext.speed} kn"
    elif isinstance(ext, aprs.DataExt):
        out += f"  {_text(bytes(ext))}"
    if report.altitude_ft is not None:
        out += f"  {report.altitude_ft} ft"
    return out


def describe(frame: aprs.APRSFrame) -> str:
    """One human-readable line for a decoded frame."""
    info = frame.info
    source = f"{str(frame.source):<10}"
    if isinstance(info, aprs.Message):
        number = f"  #{_text(info.number)}" if info.number else ""
        return f"{source} message to {_text(info.addressee)}: {_text(info.text)}{number}"
    if isinstance(info, aprs.StatusReport):
        return f"{source} status: {_text(info.status)}"
    if isinstance(info, (aprs.ObjectReport, aprs.ItemReport)):
        kind = type(info).__name__.removesuffix("Report").lower()
        killed = " (killed)" if info.killed else ""
        line = f"{source} {kind} {_text(info.name)!r}{killed} at {_position(info)}"
    elif isinstance(info, aprs.PositionReport):
        line = f"{source} position {_position(info)}"
    else:
        kind = info.data_type.name.lower() if info.data_type else "unknown"
        return f"{source} {kind}: {_text(bytes(info))}"
    # the comment keeps the /A=nnnnnn altitude text; it's shown above already
    comment = re.sub(r"/A=-?\d{5,6}", "", _text(info.comment)).strip()
    return f"{line}  {comment!r}" if comment else line


def decode_lines(lines: Iterable[str]) -> Iterable[str]:
    """Describe each TNC2 line, skipping blanks and APRS-IS comments."""
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            yield describe(aprs.APRSFrame.from_str(line))
        except Exception as exc:  # noqa: BLE001 - report the bad line and go on
            yield f"could not decode {line!r}: {exc}"


def main(argv: list[str]) -> None:
    for out in decode_lines(argv or sys.stdin):
        print(out, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
