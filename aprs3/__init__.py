#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Python APRS Module.

"""
Python APRS Module.
~~~~


:author: Greg Albrecht W2GMD <oss@undef.net>
:copyright: Copyright 2017 Greg Albrecht and Contributors
:license: Apache License, Version 2.0
:source: <https://github.com/ampledata/aprs>

"""

from .constants import (
    APRSIS_HTTP_HEADERS,
    APRSIS_SERVERS,
    APRSIS_FILTER_PORT,
    APRSIS_RX_PORT,
    APRSIS_URL,
    DEFAULT_TOCALL,
    DATA_TYPE_MAP,
)

from .geo_util import dec2dm_lat, dec2dm_lng, ambiguate  # NOQA

from .classes import InformationField, PositionReport

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2017 Greg Albrecht and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801
