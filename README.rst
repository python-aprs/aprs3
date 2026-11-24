aprs3 - Python APRS Module
**************************

.. image:: https://github.com/python-aprs/aprs3/actions/workflows/pytest.yml/badge.svg
    :target: https://github.com/python-aprs/aprs3/actions

aprs3 encodes and decodes APRS packets, and talks to APRS-IS servers and
KISS TNCs (Dire Wolf, hardware TNCs) with asyncio or plain blocking calls.
It needs Python 3.11 or newer.

Install it from PyPI::

    pip install aprs3

Decoding packets
================

``APRSFrame`` parses TNC2 text (what APRS-IS sends) or AX.25 bytes (what a
TNC sends), and decodes the information field into a typed report:

>>> import aprs
>>> frame = aprs.APRSFrame.from_str(
...     "KF7HVM-9>APZ069,WIDE1-1:!4610.00N/12255.00W>090/025/A=000500 on the road"
... )
>>> type(frame.info).__name__
'PositionReport'
>>> round(float(frame.info.lat), 4), round(float(frame.info.long), 4)
(46.1667, -122.9167)
>>> frame.info.data_ext, frame.info.altitude_ft
(CourseSpeed(course=90, speed=25), 500)

The report types are:

* ``PositionReport``: compressed or uncompressed, with or without a
  timestamp, with altitude and a course/speed, PHG, RNG or DFS extension.
  ``.weather`` reads a weather station's data, ``.df`` a DF bearing and
  ``.comment_telemetry`` base91 ``|ss11|`` telemetry
* ``MicEReport``: Mic-E positions from Kenwood and Yaesu radios, with the
  message code, altitude and radio model
* ``ObjectReport`` and ``ItemReport``
* ``StatusReport``
* ``Message``: acks and rejects (``is_ack``, ``acked_number``), reply-acks,
  bulletins and announcements, directed queries, and telemetry metadata
  (``PARM.``/``UNIT.``/``EQNS.``/``BITS.``)
* ``WeatherReport`` (positionless weather) and ``TelemetryReport`` (``T#``)
* ``ThirdPartyReport``: a packet gated from APRS-IS, with the inner frame
* ``NMEAReport``, ``QueryReport``, ``CapabilitiesReport``,
  ``MaidenheadReport`` and ``UserDefinedReport``

>>> msg = aprs.APRSFrame.from_str("KF7HVM>APZ069::N0CALL   :hello there{42}AB").info
>>> msg.addressee, msg.text, msg.message_number, msg.reply_ack
(b'N0CALL', b'hello there', b'42', b'AB')
>>> aprs.APRSFrame.from_str("N0CALL>APZ069::KF7HVM   :ack42").info.acked_number
b'42'
>>> wx = aprs.APRSFrame.from_str(
...     "N0CALL>APRS:_10090556c220s004g005t077r000p000P000h50b09900wRSW"
... ).info.weather
>>> wx.wind_direction, wx.temperature_f, wx.pressure_mbar
(220, 77, Decimal('990.0'))
>>> mic_e = aprs.APRSFrame.from_str('N0CALL-9>S32U6T:`(_fn"Oj/>=').info
>>> type(mic_e).__name__, mic_e.message_text, mic_e.device
('MicEReport', 'Returning', 'Kenwood TH-D72')

Anything else (and a packet that doesn't parse as its data type says)
decodes as a plain ``InformationField`` that keeps the raw bytes. Every
decoded packet re-encodes to the same bytes.

Encoding packets
================

Build a report, then wrap it in a frame with ``APRSFrame.ui``. ``bytes(frame)``
is ready for a TNC, and ``str(frame)`` for APRS-IS:

>>> beacon = aprs.PositionReport(
...     raw=b"",
...     data=b"",
...     data_type=aprs.DataType.POSITION_W_O_TIMESTAMP_MSG,
...     position=aprs.Position(lat=46.1, long=-122.9, symbol_code=b"-"),
...     comment=b"Home station",
... )
>>> frame = aprs.APRSFrame.ui("APZ069", "N0CALL", ["WIDE1-1"], bytes(beacon))
>>> str(frame)
'N0CALL>APZ069,WIDE1-1:=4606.00N/12254.00W-Home station'

Messages, acks and telemetry have builders:

>>> bytes(aprs.Message.new("N0CALL-2", "see you at the net", number="7"))
b':N0CALL-2 :see you at the net{7'
>>> bytes(aprs.Message.ack_for("N0CALL", "7"))
b':N0CALL   :ack7'
>>> bytes(aprs.TelemetryReport.new(1, [120, 30, 5, 0, 0], [1, 0, 0, 0, 0, 0, 0, 0]))
b'T#001,120,030,005,000,000,10000000'

Connecting to APRS-IS
=====================

With asyncio, ``create_aprsis_connection`` logs in and ``protocol.read()``
yields decoded frames. A passcode of ``-1`` is receive-only; ``aprs.passcode``
computes a callsign's passcode, and ``login_timeout`` waits for the server
to say whether the login is verified (``protocol.login_response``). A server
that goes silent for ``keepalive_timeout`` seconds (60 by default; servers
send a comment every 20 seconds) is treated as gone: the connection closes
and ``read()`` ends.

.. code-block:: python

    import asyncio

    import aprs


    async def main():
        transport, protocol = await aprs.create_aprsis_connection(
            host="rotate.aprs2.net",
            user="N0CALL",
            passcode="-1",
            command="filter r/46.1/-122.9/50",  # within 50 km
            login_timeout=10,
        )
        print(protocol.login_response)
        async for frame in protocol.read():
            print(frame)


    asyncio.run(main())

Without asyncio, ``aprs.TCP`` takes the same arguments and blocks in
``read()``:

.. code-block:: python

    import aprs

    with aprs.TCP(user="N0CALL", command="filter r/46.1/-122.9/50") as aprs_is:
        for frame in aprs_is.read(min_frames=3):
            print(frame.source, type(frame.info).__name__)

Connecting to a TNC
===================

``TCPKISS`` and ``SerialKISS`` (or ``create_tcp_connection`` and
``create_serial_connection`` with asyncio) speak KISS to a TNC and decode
what it hears into ``APRSFrame`` objects. Dire Wolf listens for KISS on TCP
port 8001:

.. code-block:: python

    import aprs

    tnc = aprs.TCPKISS("localhost", 8001)
    tnc.start()
    try:
        tnc.write(aprs.APRSFrame.from_str("N0CALL>APZ069,WIDE1-1:>on the air"))
        for frame in tnc.read(min_frames=1):
            print(frame)
    finally:
        tnc.stop()

For KISS without the APRS decoding, use `kiss3 <https://github.com/python-aprs/kiss3>`_.

Examples
========

The `examples <./examples>`_ directory has scripts you can run:

* ``aprs_decode.py`` prints a readable line for each packet given on the
  command line or piped in.
* ``aprsis_monitor.py`` watches APRS-IS traffic around a location, with each
  station's distance and bearing.
* ``beacon.py`` sends your position through a KISS TNC or APRS-IS, once or
  on a timer.

Versions
========

8.x is a rewrite with asyncio support and full packet encoding. Earlier
versions were released by Greg Albrecht as ``aprs``.

Testing
=======

Run the tests with `uv <https://docs.astral.sh/uv/>`_::

    uv run pytest

Related projects
================

* `kiss3 <https://github.com/python-aprs/kiss3>`_ and
  `ax253 <https://github.com/python-aprs/ax253>`_, the KISS and AX.25 layers
  this package builds on.
* `base-aprs-client <https://github.com/python-aprs/base-aprs-client>`_, an
  APRS messaging client built on this package.
* `aprslib <https://github.com/rossengeorgiev/aprs-python>`_ by Rossen
  Georgiev, an APRS parser with many more data types.
* `Dire Wolf <https://github.com/wb2osz/direwolf>`_ by WB2OSZ, a sound card
  TNC with a KISS interface.

Source
======
Github: https://github.com/python-aprs/aprs3

Authors
=======
Greg Albrecht W2GMD oss@undef.net

http://ampledata.org/

Masen Furer KF7HVM kf7hvm@0x26.net

Copyright
=========
Copyright 2022 Masen Furer and Contributors

Copyright 2017 Greg Albrecht and Contributors

`Automatic Packet Reporting System (APRS) <http://www.aprs.org/>`_ is Copyright Bob Bruninga WB4APR wb4apr@amsat.org

decimaldegrees.py - Copyright (C) 2006-2013 by Mateusz Łoskot <mateusz@loskot.net>


License
=======
Apache License, Version 2.0. See `LICENSE <./LICENSE>`_ for details.

`decimaldegrees.py <./aprs/decimaldegrees.py>`_ - BSD 3-clause License

`base91.py <./aprs/base91.py>`_ - GPL
