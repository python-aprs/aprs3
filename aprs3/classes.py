#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Python APRS Module Class Definitions."""

from datetime import datetime
import enum
from functools import lru_cache
import logging
import typing
from typing import Optional, Type

from attrs import define, field

from .parser import decode_position_uncompressed, decode_timestamp

__author__ = 'Greg Albrecht W2GMD <oss@undef.net>'  # NOQA pylint: disable=R0801
__copyright__ = 'Copyright 2017 Greg Albrecht and Contributors'  # NOQA pylint: disable=R0801
__license__ = 'Apache License, Version 2.0'  # NOQA pylint: disable=R0801


class DataType(enum.Enum):
    """APRS101.PDF p. 27"""
    CURRENT_MIC_E_DATA = b'\x1c'
    OLD_MIC_E_DATA = b'\x1c'
    POSITION_W_O_TIMESTAMP = b'!'
    PEET_BROS_U_II = b'#'
    RAW_GPS_DATA = b'$'
    AGRELO_DFJR = b'%'
    OLD_MIC_E_DATA_2 = b"'"
    ITEM = b")"
    PEET_BROS_U_II_2 = b'*'
    INVALID_DATA = b','
    POSITION_W_TIMESTAMP_NO_MSG = b'/'
    MESSAGE = b":"
    OBJECT = b";"
    STATION_CAPABILITIES = b"<"
    POSITION_W_O_TIMESTAMP_MSG = b"="
    STATUS = b">"
    QUERY = b"?"
    POSITION_W_TIMESTAMP_MSG = b"@"
    TELEMETRY_DATA = b"T"
    MAIDENHEAD_GRID_LOCATOR_BEACON = b"["
    WEATHER_REPORT_W_O_POSITION = b"_"
    CURRENT_MIC_E_DATA_2 = b"`"
    USER_DEFINED = b"{"
    THIRD_PARTY_TRAFFIC = b"}"


class DataTypeError(ValueError):
    pass


@define(frozen=True, slots=True)
class InformationField:
    """
    Class for APRS 'Information' Field.
    """
    raw: bytes
    data_type: DataType
    data: bytes
    data_ext: bytes = field(default=b"")
    comment: bytes = field(default=b"")

    @classmethod
    @lru_cache(len(DataType.__members__))
    def _find_handler(cls, data_type: DataType) -> Type["InformationField"]:
        for subcls in cls.__subclasses__():
            if data_type in subcls.__data_type__:
                return subcls

    @classmethod
    def from_bytes(cls, raw: bytes) -> "InformationField":
        data_type = DataType(raw[0:1])
        handler = cls._find_handler(data_type)
        if handler is None:
            x1j_header, found_data_type, data = raw.partition(b"!")
            if len(x1j_header) <= 40:
                # special case in APRS101
                return PositionReportWithoutTimestamp.from_bytes(found_data_type + data)
            return cls(raw=raw, data_type=data_type, data=b"", data_ext=b"", comment=raw[1:])
        return handler.from_bytes(raw)

    def __bytes__(self) -> bytes:
        return self.raw


@define
class PositionReport(InformationField):
    timestamp: Optional[datetime] = field(default=None)
    lat: float = field(default=0.0)
    sym_table_id: bytes = field(default=b"/")
    long: float = field(default=0.0)
    symbol_code: bytes = field(default=b"-")

    __data_type__ = [
        DataType.POSITION_W_O_TIMESTAMP,
        DataType.POSITION_W_O_TIMESTAMP_MSG,
        DataType.POSITION_W_TIMESTAMP_MSG,
        DataType.POSITION_W_TIMESTAMP_NO_MSG,
    ]

    @classmethod
    def from_bytes(cls, raw: bytes) -> "PositionReport":
        data_type = DataType(raw[0:1])
        if data_type not in cls.__data_type__:
            raise DataTypeError("{!r} cannot be handled by {!r} (expecting {!r})".format(data_type, cls, cls.__data_type__))
        timestamp = None
        if data_type in [
            DataType.POSITION_W_TIMESTAMP_MSG,
            DataType.POSITION_W_TIMESTAMP_NO_MSG,
        ]:
            timestamp = decode_timestamp(raw[1:8])
            data = raw[8:]
        else:
            data = raw[1:]
        try:
            position = decode_position_uncompressed(data[:19])
            position["comment"] = data[19:]
        except ValueError:
            # eventually we may try to decode other position types here
            raise
        return cls(
            raw=raw,
            data_type=data_type,
            data=data,
            timestamp=timestamp,
            **position
        )
