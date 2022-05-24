#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Python APRS Module Constants."""

import enum
import os

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2017 Greg Albrecht and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801


APRSIS_HTTP_HEADERS = {
    "content-type": "application/octet-stream",
    "accept": "text/plain",
}

APRSIS_SERVERS = [b"rotate.aprs.net", b"noam.aprs2.net"]
APRSIS_FILTER_PORT = int(os.environ.get("APRSIS_FILTER_PORT", 14580))
APRSIS_RX_PORT = int(os.environ.get("APRSIS_RX_PORT", 8080))
APRSIS_URL = os.environ.get("APRSIS_URL", b"http://srvr.aprs-is.net:8080")

DEFAULT_TOCALL = b"APZ069"

DATA_TYPE_MAP = {
    b">": b"status",
    b"!": b"position_nots_nomsg",
    b"=": b"position_nots_msg",
    b"T": b"telemetry",
    b";": b"object",
    b"`": b"old_mice",
}


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
