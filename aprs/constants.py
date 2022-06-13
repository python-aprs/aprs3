"""Python APRS Module Constants."""
import enum
import os

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"
__copyright__ = "Copyright 2017 Greg Albrecht and Contributors"
__license__ = "Apache License, Version 2.0"


APRSIS_HTTP_HEADERS = {
    "content-type": "application/octet-stream",
    "accept": "text/plain",
}

APRSIS_SERVERS = ["rotate.aprs.net", "noam.aprs2.net"]
APRSIS_FILTER_PORT = int(os.environ.get("APRSIS_FILTER_PORT", 14580))
APRSIS_RX_PORT = int(os.environ.get("APRSIS_RX_PORT", 8080))
APRSIS_URL = os.environ.get("APRSIS_URL", "http://srvr.aprs-is.net:8080")

DEFAULT_MYCALL = "N0CALL"
DEFAULT_TOCALL = "APZ069"


class TimestampFormat(enum.Enum):
    DayHoursMinutesLocal = b"/"
    DayHoursMinutesZulu = b"z"
    HoursMinutesSecondsZulu = b"h"
    MonthDayHoursMinutesZulu = b""


timestamp_formats_map = {
    TimestampFormat.DayHoursMinutesZulu: "%d%H%M",
    TimestampFormat.DayHoursMinutesLocal: "%d%H%M",
    TimestampFormat.HoursMinutesSecondsZulu: "%H%M%S",
    TimestampFormat.MonthDayHoursMinutesZulu: "%m%d%H%M",
}


class PositionFormat(enum.Enum):
    Uncompressed = 0
    Compressed = 1
