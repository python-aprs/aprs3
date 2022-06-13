#!/usr/bin/env python3
import os

import aprs


MYCALL = os.environ.get("MYCALL", "N0CALL")
KISS_HOST = os.environ.get("KISS_HOST", "localhost")
KISS_PORT = os.environ.get("KISS_PORT", "8001")


def main():
    ki = aprs.TCPKISS(host=KISS_HOST, port=int(KISS_PORT))
    ki.start()
    frame = aprs.APRSFrame.ui(
        destination="APZ001",
        source=MYCALL,
        path=["WIDE1-1"],
        info=b">Hello World!",
    )
    ki.write(frame)
    while True:
        for frame in ki.read(min_frames=1):
            print(repr(frame))


if __name__ == "__main__":
    main()
