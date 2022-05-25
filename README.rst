aprs3 - Python APRS Module
**************************

.. image:: https://github.com/python-aprs/aprs3/actions/workflows/pytest.yml/badge.svg
    :target: https://github.com/python-aprs/aprs3/actions

aprs3 is a module for encoding and decoding APRS data for use with AX.25 or APRS-IS.

Supported Data Types
====================

* Position (``PositionReport``)

  * Compressed
  * Uncompressed
  * w/ Timestamp
  * Data Extension
  
    * Course / Speed
    * PHG
    * RNG
    * DFS
    
  * Altitude
  
* Object (``ObjectReport``)
* Item (``ItemReport``)
* Status (``StatusReport``)
* Message (``Message``)

Unknown data types will be decoded as ``InformationField``.

Interfaces
==========

This package supplies async methods for interacting with APRS-IS::

    import asyncio
    from aprs3 import create_aprsis_connection

    async def main():
        transport, protocol = create_aprsis_connection(
            host="noam.aprs2.net",
            port=14580,
            user="KF7HVM",
            passcode="-1",  # use a real passcode for TX
            command='filter r/46.1/-122.9/500',
        )

        async for frame in protocol.read():
            print(frame)

    if __name__ == "__main__":
        asyncio.run(main())

Synchronous wrappers are also included where that may be more convenient::

    from pprint import pformat

    import attrs

    import aprs3

    with aprs3.TCP(
        host="noam.aprs2.net",
        port=14580,
        user="KF7HVM",
        passcode="-1",  # use a real passcode for TX
        command='filter r/46.1/-122.9/500',
    ) as aprs_tcp:
        # optional callback can be set on the protocol object
        aprs_tcp.protocol.callback = lambda f: print(f)

        # block until 1 frame is available and print repr
        print(repr(aprs_tcp.read(min_frames=1)[0]))

        # block until 3 frames are available and print decoded form
        for frame in aprs_tcp.read(min_frames=3):
            print(pformat(attrs.asdict(frame)))

Additionally, this package may be used with real TNCs via Serial KISS or KISS-over-TCP.

* serial:

  * sync: ``aprs_serial = aprs3.SerialKISS("/dev/ttyUSB0", 9600)``
  * async: ``transport, protocol = aprs3.create_serial_connection("/dev/ttyUSB0", 9600)``
  
* tcp:

  * sync: ``aprs_kiss_tcp = aprs3.TCPKISS("localhost", 8001)``
  * async: ``transport, protocol = aprs3.create_tcp_connection("localhost", 8001)``

These objects are used in the same way as the sample shown above.

For versions of the KISS transports which do NOT automatically encode/decode APRS data,
see `kiss3 <https://github.com/python-aprs/kiss3>`_.

Versions
========

- **8.x.x branch is a large rewrite as** ``aprs3``, **including async functionality and full packet encoding**.

Previous versions were released by ``ampledata`` as ``aprs``:

- 7.x.x branch and-on will be Python 3.x ONLY.

- 6.5.x branch will be the last version of this Module that supports Python 2.7.x


Installation
============
Install from pypi using pip: ``pip install aprs3``


Usage Examples
==============

Example 1: Library Usage - Receive
----------------------------------

The following example connects to APRS-IS and filters for APRS
frames within 500 miles of 46.1N, 122.9W. Any frames returned are
sent to the callback *p*, which prints them.

Example 1 Code
^^^^^^^^^^^^^^
::


    import aprs3

    def p(x): print(x)

    with aprs3.TCP(command='filter r/46.1/-122.9/500') as aprs_tcp:
        # callback can be set on the protocol object
        aprs_tcp.protocol.callback = p
        aprs_tcp.read()

Example 1 Output
^^^^^^^^^^^^^^^^
::

    W2GMD-6>APRX28,TCPIP*,qAC,APRSFI-I1:T#471,7.5,34.7,37.0,1.0,137.0,00000000

Example 2: Library Usage - Send
----------------------------------

The following example connects to APRS-IS and sends an APRS frame.

Example 2 Code
^^^^^^^^^^^^^^
::

    import aprs3

    frame = aprs3.APRSFrame.from_str('KF7HVM-2>APRS:>Test from aprs3!')

    with aprs3.TCP(user='W2GMD', passcode='12345') as a:
        a.write(frame)

Testing
=======
Run pytest via tox::

    tox


See Also
========

* `Python kiss3 Module <https://github.com/python-aprs/kiss3>`_ Library for interfacing-to and encoding-for various KISS Interfaces.

  * Forked from `ampledata/kiss <https://github.com/ampledata/kiss>`_
  
* `Python aprs3 Module <https://github.com/python-aprs/aprs3>`_ Library for sending, receiving and parsing APRS Frames to and from multiple Interfaces

  * Forked from `ampledata/aprs <https://github.com/ampledata/aprs>`_
  
* `Python APRS Gateway <https://github.com/ampledata/aprsgate>`_ Uses Redis PubSub to run a multi-interface APRS Gateway.
* `Python APRS Tracker <https://github.com/ampledata/aprstracker>`_ TK.
* `dirus <https://github.com/ampledata/dirus>`_ Dirus is a daemon for managing a SDR to Dire Wolf interface. Manifests that interface as a KISS TCP port.


Similar Projects
================

* `apex <https://github.com/Syncleus/apex>`_ by Jeffrey Phillips Freeman (WI2ARD). Next-Gen APRS Protocol.
* `aprslib <https://github.com/rossengeorgiev/aprs-python>`_ by Rossen Georgiev. A Python APRS Library with build-in parsers for several Frame types.
* `aprx <http://thelifeofkenneth.com/aprx/>`_ by Matti & Kenneth. A C-based Digi/IGate Software for POSIX platforms.
* `dixprs <https://sites.google.com/site/dixprs/>`_ by HA5DI. A Python APRS project with KISS, digipeater, et al., support.
* `APRSDroid <http://aprsdroid.org/>`_ by GE0RG. A Java/Scala Android APRS App.
* `YAAC <http://www.ka2ddo.org/ka2ddo/YAAC.html>`_ by KA2DDO. A Java APRS Client.
* `Ham-APRS-FAP <http://search.cpan.org/dist/Ham-APRS-FAP/>`_ by aprs.fi: A Perl APRS Parser.
* `Dire Wolf <https://github.com/wb2osz/direwolf>`_ by WB2OSZ. A C-Based Soft-TNC for interfacing with sound cards. Can present as a KISS interface!


Source
======
Github: https://github.com/python-aprs/aprs3

Author
======
Masen Furer KF7HVM kf7hvm@0x26.net

Originally By
-------------
Greg Albrecht W2GMD oss@undef.net

http://ampledata.org/

Copyright
=========
Copyright 2022 Masen Furer and Contributors

Copyright 2017 Greg Albrecht and Contributors

`Automatic Packet Reporting System (APRS) <http://www.aprs.org/>`_ is Copyright Bob Bruninga WB4APR wb4apr@amsat.org

fcs.py - Copyright (c) 2013 Christopher H. Casebeer. All rights reserved.

decimaldegrees.py - Copyright (C) 2006-2013 by Mateusz Łoskot <mateusz@loskot.net>


License
=======
Apache License, Version 2.0. See `LICENSE <./LICENSE>`_ for details.

`decimaldegrees.py <./aprs3/decimaldegrees.py>`_ - BSD 3-clause License

`base91.py <./aprs3/base91.py>`_ - GPL
