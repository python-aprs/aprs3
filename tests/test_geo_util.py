#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Python APRS Module Geo Utility Function Tests.

Spec per ftp://ftp.tapr.org/aprssig/aprsspec/spec/aprs101/APRS101.pdf

Latitude
--------

Latitude is expressed as a fixed 8-character field, in degrees and decimal
minutes (to two decimal places), followed by the letter N for north or S for
south.

Latitude degrees are in the range 00 to 90. Latitude minutes are expressed as
whole minutes and hundredths of a minute, separated by a decimal point.

For example:

    4903.50N    is 49 degrees 3 minutes 30 seconds north.

In generic format examples, the latitude is shown as the 8-character string
ddmm.hhN (i.e. degrees, minutes and hundredths of a minute north).


Longitude Format
----------------

Longitude is expressed as a fixed 9-character field, in degrees and decimal
minutes (to two decimal places), followed by the letter E for east or W for
west.

Longitude degrees are in the range 000 to 180. Longitude minutes are expressed
as whole minutes and hundredths of a minute, separated by a decimal point.

For example:

    07201.75W    is 72 degrees 1 minute 45 seconds west.

In generic format examples, the longitude is shown as the 9-character string
dddmm.hhW (i.e. degrees, minutes and hundredths of a minute west).

"""

from aprs3 import geo_util

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2017 Greg Albrecht and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801


def test_latitude_north():
    """Test Decimal to APRS Latitude conversion."""
    test_lat = 37.7418096
    aprs_lat = geo_util.dec2dm_lat(test_lat)

    lat_deg = int(aprs_lat.split(b".")[0][:1])
    # lat_hsec = aprs_lat.split('.')[1]

    assert len(aprs_lat) == 8
    assert lat_deg >= 00
    assert lat_deg <= 90
    assert aprs_lat.endswith(b"N")


def test_latitude_south():
    """Test Decimal to APRS Latitude conversion."""
    test_lat = -37.7418096
    aprs_lat = geo_util.dec2dm_lat(test_lat)

    lat_deg = int(aprs_lat.split(b".")[0][:1])

    assert len(aprs_lat) == 8
    assert lat_deg >= 00
    assert lat_deg <= 90
    assert aprs_lat.endswith(b"S")


def test_latitude_south_padding_minutes():
    """
    Test Decimal to APRS Latitude conversion for latitudes in the
    following situations:
        - minutes < 10
        - whole degrees latitude < 10
    """
    test_lat = -38.01
    aprs_lat = geo_util.dec2dm_lat(test_lat)

    lat_deg = int(aprs_lat.split(b".")[0][:1])

    assert len(aprs_lat) == 8
    assert lat_deg >= 00
    assert lat_deg <= 90
    assert aprs_lat.endswith(b"S")


def test_latitude_south_padding_degrees():
    """
    Test Decimal to APRS Latitude conversion for latitudes in the
    following situations:
        - minutes < 10
        - whole degrees latitude < 10
    """
    test_lat = -8.01
    aprs_lat = geo_util.dec2dm_lat(test_lat)

    lat_deg = int(aprs_lat.split(b".")[0][:1])

    assert len(aprs_lat) == 8
    assert lat_deg >= 00
    assert lat_deg <= 90
    assert aprs_lat.endswith(b"S")


def test_longitude_west():
    """Test Decimal to APRS Longitude conversion."""
    test_lng = -122.38833
    aprs_lng = geo_util.dec2dm_lng(test_lng)

    lng_deg = int(aprs_lng.split(b".")[0][:2])
    # lng_hsec = aprs_lng.split('.')[1]

    assert len(aprs_lng) == 9
    assert lng_deg >= 000
    assert lng_deg <= 180
    assert aprs_lng.endswith(b"W")


def test_longitude_west_padding_minutes():
    """
    Test Decimal to APRS Longitude conversion for longitude in the
    following situations:
        - minutes < 10
        - whole degrees longitude < 100
    """
    test_lng = -122.01
    aprs_lng = geo_util.dec2dm_lng(test_lng)

    lng_deg = int(aprs_lng.split(b".")[0][:2])
    # lng_hsec = aprs_lng.split('.')[1]

    assert len(aprs_lng) == 9
    assert lng_deg >= 000
    assert lng_deg <= 180
    assert aprs_lng.endswith(b"W")


def test_longitude_west_padding_degrees():
    """
    Test Decimal to APRS Longitude conversion for longitude in the
    following situations:
        - minutes < 10
        - whole degrees longitude < 100
    """
    test_lng = -99.01
    aprs_lng = geo_util.dec2dm_lng(test_lng)

    lng_deg = int(aprs_lng.split(b".")[0][:2])
    # lng_hsec = aprs_lng.split('.')[1]

    assert len(aprs_lng) == 9
    assert lng_deg >= 000
    assert lng_deg <= 180
    assert aprs_lng.endswith(b"W")


def test_longitude_east():
    """Test Decimal to APRS Longitude conversion."""
    test_lng = 122.38833
    aprs_lng = geo_util.dec2dm_lng(test_lng)

    lng_deg = int(aprs_lng.split(b".")[0][:2])
    # lng_hsec = aprs_lng.split('.')[1]

    assert len(aprs_lng) == 9
    assert lng_deg >= 000
    assert lng_deg <= 180
    assert aprs_lng.endswith(b"E")
