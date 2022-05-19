#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Python APRS Module Class Definitions."""

import logging
import typing

__author__ = 'Greg Albrecht W2GMD <oss@undef.net>'  # NOQA pylint: disable=R0801
__copyright__ = 'Copyright 2017 Greg Albrecht and Contributors'  # NOQA pylint: disable=R0801
__license__ = 'Apache License, Version 2.0'  # NOQA pylint: disable=R0801


class InformationField(object):
    """
    Class for APRS 'Information' Field.
    """

    _logger = logging.getLogger(__name__)  # pylint: disable=R0801
    if not _logger.handlers:  # pylint: disable=R0801
        _logger.setLevel(aprs.LOG_LEVEL)  # pylint: disable=R0801
        _console_handler = logging.StreamHandler()  # pylint: disable=R0801
        _console_handler.setLevel(aprs.LOG_LEVEL)  # pylint: disable=R0801
        _console_handler.setFormatter(aprs.LOG_FORMAT)  # pylint: disable=R0801
        _logger.addHandler(_console_handler)  # pylint: disable=R0801
        _logger.propagate = False  # pylint: disable=R0801

    __slots__ = ['data_type', 'data', 'safe']

    def __init__(self, data: bytes=b'', data_type: bytes=b'undefined',
                 safe: bool=False) -> None:
        self.data = data
        self.data_type = data_type
        self.safe = safe

    def __repr__(self) -> str:
        if self.safe:
            try:
                decoded_data = self.data.decode('UTF-8')
            except UnicodeDecodeError as ex:
                decoded_data = self.data.decode('UTF-8', 'backslashreplace')
            return decoded_data
        else:
            return self.data.decode()

    def __bytes__(self) -> bytes:
        return self.data


class PositionFrame(Frame):

    __slots__ = ['lat', 'lng', 'source', 'destination', 'path', 'table',
                 'symbol', 'comment', 'ambiguity']

    _logger = logging.getLogger(__name__)  # pylint: disable=R0801
    if not _logger.handlers:  # pylint: disable=R0801
        _logger.setLevel(aprs.LOG_LEVEL)  # pylint: disable=R0801
        _console_handler = logging.StreamHandler()  # pylint: disable=R0801
        _console_handler.setLevel(aprs.LOG_LEVEL)  # pylint: disable=R0801
        _console_handler.setFormatter(aprs.LOG_FORMAT)  # pylint: disable=R0801
        _logger.addHandler(_console_handler)  # pylint: disable=R0801
        _logger.propagate = False  # pylint: disable=R0801

    def __init__(self, source: bytes, destination: bytes, path: typing.List,
                 table: bytes, symbol: bytes, comment: bytes, lat: float,
                 lng: float, ambiguity: float) -> None:
        self.table = table
        self.symbol = symbol
        self.comment = comment
        self.lat = lat
        self.lng = lng
        self.ambiguity = ambiguity
        info = self.create_info_field()
        super(PositionFrame, self).__init__(source, destination, path, info)

    def create_info_field(self) -> bytes:
        enc_lat = aprs.dec2dm_lat(self.lat)
        enc_lat_amb = bytes(aprs.ambiguate(enc_lat, self.ambiguity), 'UTF-8')
        enc_lng = aprs.dec2dm_lng(self.lng)
        enc_lng_amb = bytes(aprs.ambiguate(enc_lng, self.ambiguity), 'UTF-8')
        frame = [
            b'=',
            enc_lat_amb,
            self.table,
            enc_lng_amb,
            self.symbol,
            self.comment
        ]
        return b''.join(frame)
