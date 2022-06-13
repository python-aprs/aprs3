"""
Python APRS Module.
~~~~

:author: Greg Albrecht W2GMD <oss@undef.net>
:copyright: Copyright 2017 Greg Albrecht and Contributors
:license: Apache License, Version 2.0
:source: <https://github.com/ampledata/aprs>

"""
from importlib_metadata import version

from . import decimaldegrees, geo_util, position, timestamp
from .aprsis import APRSISProtocol, create_aprsis_connection, TCP
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
    APRSIS_HTTP_HEADERS,
    APRSIS_SERVERS,
    APRSIS_FILTER_PORT,
    APRSIS_RX_PORT,
    APRSIS_URL,
    DEFAULT_TOCALL,
    PositionFormat,
    TimestampFormat,
    timestamp_formats_map,
)
from .data_ext import (
    AreaObject,
    CourseSpeed,
    DataExt,
    DFS,
    PHG,
    RNG,
)
from .kiss import create_serial_connection, create_tcp_connection, SerialKISS, TCPKISS
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
