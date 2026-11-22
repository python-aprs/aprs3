"""Encode and decode APRS packets.

``APRSFrame`` decodes an AX.25 frame or TNC2 text into typed information
fields (positions, objects, items, status reports and messages) and encodes
them back. Connect to APRS-IS with ``TCP`` or ``create_aprsis_connection``,
or to a TNC with ``SerialKISS``, ``TCPKISS``, ``create_serial_connection``
and ``create_tcp_connection``.

Based on the original ``aprs`` module by Greg Albrecht W2GMD
(https://github.com/ampledata/aprs), Apache License 2.0.
"""

from importlib.metadata import version

from . import decimaldegrees, geo_util, position, timestamp
from .aprsis import TCP, APRSISProtocol, create_aprsis_connection
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
from .position import Position
from .timestamp import Timestamp

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"
__copyright__ = "Copyright 2017 Greg Albrecht and Contributors"
__license__ = "Apache License, Version 2.0"
__distribution__ = "aprs3"
__version__ = version(__distribution__)
__all__ = [
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
    "InformationField",
    "Message",
    "ObjectReport",
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
