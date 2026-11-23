#!/usr/bin/env python3
"""
Watch APRS-IS traffic around a location.

Logs in read-only (passcode -1), asks the server for packets within
``--range`` km of ``--near``, and prints each one with its distance and
bearing from you::

    $ python aprsis_monitor.py --near 46.0 -123.0 --range 30
    KF7HVM-9     19.6 km N  position 46.16667, -122.91667  symbol />  course 90° 25 kn

Use ``--filter`` to send any APRS-IS server-side filter instead, such as
``b/KF7HVM*`` for one station's packets, and ``--count`` to stop after a
number of packets.
"""

import argparse
import asyncio
import math

from aprs_decode import describe

import aprs
from aprs.position import PositionMixin

COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def distance_bearing(lat1, lon1, lat2, lon2) -> tuple[float, str]:
    """Great-circle distance in km and compass bearing from point 1 to point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    km = 2 * 6371.0 * math.asin(math.sqrt(a))
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    degrees = math.degrees(math.atan2(y, x)) % 360
    return km, COMPASS[round(degrees / 45) % 8]


def line_for(frame: aprs.APRSFrame, near: tuple[float, float] | None) -> str:
    text = describe(frame)
    info = frame.info
    if near is None or not isinstance(info, PositionMixin) or info.lat is None:
        return text
    km, direction = distance_bearing(*near, float(info.lat), float(info.long or 0))
    source, rest = text[:10], text[10:]
    return f"{source} {km:6.1f} km {direction:<2}{rest}"


async def monitor(args: argparse.Namespace) -> None:
    if args.filter:
        command = f"filter {args.filter}"
    elif args.near:
        command = f"filter r/{args.near[0]}/{args.near[1]}/{args.range}"
    else:
        raise SystemExit("give --near LAT LON or --filter")
    host, _, port = args.server.partition(":")
    transport, protocol = await aprs.create_aprsis_connection(
        host=host, port=int(port or 14580), user=args.call, command=command
    )
    try:
        seen = 0
        async for frame in protocol.read():
            assert isinstance(frame, aprs.APRSFrame)  # APRSISProtocol decodes APRS
            print(line_for(frame, args.near), flush=True)
            seen += 1
            if args.count and seen >= args.count:
                break
    finally:
        transport.close()


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--near", nargs=2, type=float, metavar=("LAT", "LON"))
    parser.add_argument("--range", type=float, default=50, help="km (default 50)")
    parser.add_argument("--filter", help="raw APRS-IS filter, e.g. b/KF7HVM*")
    parser.add_argument("--call", default="N0CALL", help="login callsign")
    parser.add_argument("--server", default="rotate.aprs2.net:14580")
    parser.add_argument("--count", type=int, default=0, help="stop after N packets")
    return parser


def main(argv=None) -> None:
    try:
        asyncio.run(monitor(make_parser().parse_args(argv)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
