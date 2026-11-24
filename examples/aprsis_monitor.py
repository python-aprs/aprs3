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

from aprs_decode import describe

import aprs

COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def line_for(frame: aprs.APRSFrame, near: tuple[float, float] | None) -> str:
    text = describe(frame)
    position = frame.position
    if near is None or position is None:
        return text
    here = aprs.Position(lat=near[0], lon=near[1])
    km = here.distance_to(position)
    direction = COMPASS[round(here.bearing_to(position) / 45) % 8]
    source, rest = text[:10], text[10:]
    return f"{source} {km:6.1f} km {direction:<2}{rest}"


async def monitor(args: argparse.Namespace) -> None:
    if args.filter:
        filter_ = args.filter
    elif args.near:
        filter_ = f"r/{args.near[0]}/{args.near[1]}/{args.range}"
    else:
        raise SystemExit("give --near LAT LON or --filter")
    host, _, port = args.server.partition(":")
    transport, protocol = await aprs.create_aprsis_connection(
        host=host, port=int(port or 14580), user=args.call, filter=filter_
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
