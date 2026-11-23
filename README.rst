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
  timestamp, with altitude and a course/speed, PHG, RNG or DFS extension
* ``ObjectReport`` and ``ItemReport``
* ``StatusReport``
* ``Message``, including acks and rejects

>>> aprs.APRSFrame.from_str("KF7HVM>APZ069::N0CALL   :hello there{42").info
Message(raw=b':N0CALL   :hello there{42', data_type=<DataType.MESSAGE: b':'>, data=b'N0CALL   :hello there{42', comment=b'', addressee=b'N0CALL', text=b'hello there', number=b'42')

Other data types (telemetry, weather, Mic-E and so on) decode as a plain
``InformationField`` that keeps the raw bytes.

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

Connecting to APRS-IS
=====================

With asyncio, ``create_aprsis_connection`` logs in and ``protocol.read()``
yields decoded frames. A passcode of ``-1`` is receive-only:

.. code-block:: python

    import asyncio

    import aprs


    async def main():
        transport, protocol = await aprs.create_aprsis_connection(
            host="rotate.aprs2.net",
            user="N0CALL",
            passcode="-1",
            command="filter r/46.1/-122.9/50",  # within 50 km
        )
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
