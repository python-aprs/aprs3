r"""Encode and decode APRS packets.

``APRSFrame`` is an AX.25 UI frame whose information field is decoded into a
typed report: ``PositionReport``, ``ObjectReport``, ``ItemReport``,
``StatusReport`` or ``Message``. Anything else stays an ``InformationField``.

Decoding
========

APRS-IS sends packets as TNC2 text; a TNC sends AX.25 bytes. Both decode to
the same frame:

>>> import aprs
>>> frame = aprs.APRSFrame.from_str(
...     "KF7HVM-9>APZ069,WIDE1-1:!4610.00N/12255.00W>090/025/A=000500 on the road"
... )
>>> str(frame.source), str(frame.destination), [str(p) for p in frame.path]
('KF7HVM-9', 'APZ069', ['WIDE1-1'])
>>> aprs.APRSFrame.from_bytes(bytes(frame)) == frame
True

Read the report's fields directly. Coordinates are decimal degrees:

>>> report = frame.info
>>> type(report).__name__
'PositionReport'
>>> round(float(report.lat), 4), round(float(report.long), 4)
(46.1667, -122.9167)
>>> report.symbol_code, report.altitude_ft
(b'>', 500)
>>> report.data_ext
CourseSpeed(course=90, speed=25)

Messages carry the addressee, text and message number:

>>> msg = aprs.APRSFrame.from_str("KF7HVM>APZ069::N0CALL   :hello there{42").info
>>> msg.addressee, msg.text, msg.number
(b'N0CALL', b'hello there', b'42')

Encoding
========

Build a report and wrap it in a frame with ``APRSFrame.ui``:

>>> beacon = aprs.PositionReport(
...     raw=b"",
...     data=b"",
...     data_type=aprs.DataType.POSITION_W_O_TIMESTAMP_MSG,
...     position=aprs.Position(lat=46.1, long=-122.9, symbol_code=b"-"),
...     comment=b"Home station",
... )
>>> str(aprs.APRSFrame.ui("APZ069", "N0CALL", ["WIDE1-1"], bytes(beacon)))
'N0CALL>APZ069,WIDE1-1:=4606.00N/12254.00W-Home station'

Connections
===========

Connect to APRS-IS with ``create_aprsis_connection`` (async) or ``TCP``
(sync), or to a TNC with ``create_tcp_connection``, ``create_serial_connection``,
``TCPKISS`` or ``SerialKISS``. All of them yield ``APRSFrame`` objects. The
``examples/`` directory in the repository has runnable scripts.

Based on the original ``aprs`` module by Greg Albrecht W2GMD
(https://github.com/ampledata/aprs), Apache License 2.0.
"""

from importlib.metadata import version

from . import decimaldegrees, geo_util, position, timestamp
from .aprsis import (
    TCP,
    APRSISProtocol,
    LoginResponse,
    create_aprsis_connection,
    passcode,
)
from .classes import (
    APRSFrame,
    DataType,
    DataTypeError,
    InformationField,
    ItemReport,
    Message,
    ObjectReport,
    PositionReport,
    StatusReport,
)
from .constants import (
    APRSIS_FILTER_PORT,
    APRSIS_HTTP_HEADERS,
    APRSIS_RX_PORT,
    APRSIS_SERVERS,
    APRSIS_URL,
    DEFAULT_TOCALL,
    PositionFormat,
    TimestampFormat,
    timestamp_formats_map,
)
from .data_ext import (
    DFS,
    PHG,
    RNG,
    AreaObject,
    CourseSpeed,
    DataExt,
)
from .kiss import TCPKISS, SerialKISS, create_serial_connection, create_tcp_connection
from .nmea import NMEAReport, nmea_checksum
from .position import DirectionFinding, Position
from .reports import (
    CapabilitiesReport,
    MaidenheadReport,
    QueryReport,
    ThirdPartyReport,
    UserDefinedReport,
    grid_to_lat_long,
)
from .telemetry import (
    CommentTelemetry,
    TelemetryBits,
    TelemetryEquations,
    TelemetryMetadata,
    TelemetryNames,
    TelemetryReport,
    TelemetryUnits,
)
from .timestamp import Timestamp

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"
__copyright__ = "Copyright 2017 Greg Albrecht and Contributors"
__license__ = "Apache License, Version 2.0"
__distribution__ = "aprs3"
__version__ = version(__distribution__)
__all__ = [
    "TelemetryUnits",
    "TelemetryReport",
    "TelemetryNames",
    "TelemetryMetadata",
    "TelemetryEquations",
    "TelemetryBits",
    "CommentTelemetry",
    "DirectionFinding",
    "nmea_checksum",
    "NMEAReport",
    "grid_to_lat_long",
    "UserDefinedReport",
    "ThirdPartyReport",
    "QueryReport",
    "MaidenheadReport",
    "CapabilitiesReport",
    "APRSFrame",
    "APRSIS_HTTP_HEADERS",
    "APRSIS_SERVERS",
    "APRSIS_FILTER_PORT",
    "APRSIS_RX_PORT",
    "APRSIS_URL",
    "APRSISProtocol",
    "AreaObject",
    "CourseSpeed",
    "create_aprsis_connection",
    "create_serial_connection",
    "create_tcp_connection",
    "DataExt",
    "DataType",
    "DataTypeError",
    "decimaldegrees",
    "DEFAULT_TOCALL",
    "DFS",
    "geo_util",
    "ItemReport",
    "LoginResponse",
    "InformationField",
    "Message",
    "ObjectReport",
    "passcode",
    "PHG",
    "position",
    "Position",
    "PositionFormat",
    "PositionReport",
    "RNG",
    "SerialKISS",
    "StatusReport",
    "TCP",
    "TCPKISS",
    "timestamp",
    "Timestamp",
    "TimestampFormat",
    "timestamp_formats_map",
    "__author__",
    "__copyright__",
    "__license__",
    "__distribution__",
    "__version__",
]
