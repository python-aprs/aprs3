#!/usr/bin/env python3
"""
Beacon your station's position through a TNC or APRS-IS.

Send one position report to a KISS TNC on TCP (Dire Wolf listens on 8001 by
default) or on a serial port, or to APRS-IS with your passcode::

    $ python beacon.py --call N0CALL-10 --lat 46.1 --lon -122.9 --tcp localhost:8001
    N0CALL-10>APZ069,WIDE1-1:=4606.00N/12254.00W-Home station

    $ python beacon.py --call N0CALL --lat 46.1 --lon -122.9 --serial /dev/ttyUSB0

    $ python beacon.py --call N0CALL --lat 46.1 --lon -122.9 \\
        --aprsis rotate.aprs2.net:14580 --passcode 12345

``--every 30`` repeats the beacon every 30 minutes until interrupted. The
symbol defaults to ``/-`` (a house); see http://www.aprs.org/symbols.html.
"""

import argparse
import time

import aprs

DEFAULT_TOCALL = "APZ069"  # APZxxx is the experimental software range


def position_frame(args: argparse.Namespace) -> aprs.APRSFrame:
    """The beacon frame for the command line options."""
    # without a data type, a position report is sent with "=": this
    # station can receive messages
    report = aprs.PositionReport(
        position=aprs.Position(
            lat=args.lat,
            lon=args.lon,
            symbol=args.symbol,
            altitude_ft=args.altitude,
        ),
        comment=args.comment,
    )
    path = [p for p in args.path.split(",") if p] if not args.aprsis else []
    return aprs.APRSFrame.ui(DEFAULT_TOCALL, args.call, path, bytes(report))


def connect(args: argparse.Namespace):
    """A started TNC or APRS-IS connection for the command line options."""
    if args.tcp:
        host, _, port = args.tcp.partition(":")
        conn = aprs.TCPKISS(host, int(port or 8001))
    elif args.serial:
        conn = aprs.SerialKISS(args.serial, args.baud)
    else:
        if not args.passcode:
            raise SystemExit("APRS-IS needs --passcode to transmit")
        host, _, port = args.aprsis.partition(":")
        conn = aprs.TCP(
            host=host, port=int(port or 14580), user=args.call, passcode=args.passcode
        )
    conn.start()
    return conn


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--call", required=True, help="your callsign, e.g. N0CALL-10")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--symbol", default="/-", help="table and symbol (default /-)")
    parser.add_argument("--altitude", type=int, help="feet")
    parser.add_argument("--comment", default="Home station")
    parser.add_argument("--path", default="WIDE1-1", help="digipeater path for RF")
    parser.add_argument("--every", type=float, help="repeat every N minutes")
    via = parser.add_mutually_exclusive_group(required=True)
    via.add_argument("--tcp", metavar="HOST:PORT", help="KISS TNC over TCP")
    via.add_argument("--serial", metavar="DEVICE", help="KISS TNC on a serial port")
    via.add_argument("--aprsis", metavar="HOST:PORT", help="APRS-IS server")
    parser.add_argument("--baud", type=int, default=9600, help="serial speed")
    parser.add_argument("--passcode", help="APRS-IS passcode for --call")
    args = parser.parse_args(argv)
    if len(args.symbol) != 2:
        parser.error("--symbol is two characters: the table (/ or \\) and the symbol")

    frame = position_frame(args)
    conn = connect(args)
    try:
        while True:
            conn.write(frame)
            print(frame, flush=True)
            if not args.every:
                break
            time.sleep(args.every * 60)
    except KeyboardInterrupt:
        pass
    finally:
        conn.stop()


if __name__ == "__main__":
    main()
