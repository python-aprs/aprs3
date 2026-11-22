"""
APRS-IS and KISS connection helpers against local servers and a pty.

These cover the aprs layer: frames arrive as APRSFrame with decoded info
fields, undecodable input is dropped without breaking the stream, and frames
written go out in the right wire format.
"""

import asyncio
import contextlib
import gc
import os
import socket
import sys
import threading
from collections.abc import Callable

import pytest

import aprs
from aprs import APRSFrame, Message, PositionReport, StatusReport
from aprs.aprsis import create_aprsis_connection
from aprs.kiss import create_serial_connection, create_tcp_connection

POSITION = "N0CALL-9>APDR16,TCPIP*,qAC,T2TEST:=4903.50N/07201.75W$ via APRSdroid"
STATUS = "N0CALL>APDW17,WIDE1-1:>Dire Wolf status"
MESSAGE = "N0CALL>APRS::N0CALL-2 :ping{7"
RF_POSITION = "N0CALL>APDW17,N0DIGI*,WIDE2-1:!4903.50N/07201.75W#digi"

FEND, FESC, TFEND, TFESC = b"\xc0", b"\xdb", b"\xdc", b"\xdd"


def kiss_frame(payload: bytes, command: int = 0) -> bytes:
    escaped = payload.replace(FESC, FESC + TFESC).replace(FEND, FESC + TFEND)
    return FEND + bytes([command]) + escaped + FEND


def kiss_payloads(data: bytes) -> list[bytes]:
    frames = [f for f in data.split(FEND) if f]
    return [f[1:].replace(FESC + TFEND, FEND).replace(FESC + TFESC, FESC) for f in frames]


class Server:
    """A one-connection TCP server running a scripted coroutine."""

    port: int
    wait_done: Callable[[], None]  # set by threaded_server

    def __init__(self, script):
        self.script = script
        self.received = b""
        self.done = asyncio.Event()

    async def _handle(self, reader, writer):
        try:
            await self.script(self, reader, writer)
        finally:
            writer.close()
            self.done.set()

    async def readline(self, reader) -> bytes:
        line = await reader.readline()
        self.received += line
        return line

    async def read_until_closed(self, reader) -> None:
        while chunk := await reader.read(4096):
            self.received += chunk

    @contextlib.asynccontextmanager
    async def serving(self):
        server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = server.sockets[0].getsockname()[1]
        async with server:
            yield self


async def read_all(protocol, timeout=5.0) -> list:
    async def _read():
        return [frame async for frame in protocol.read()]

    return await asyncio.wait_for(_read(), timeout)


# --- APRS-IS -----------------------------------------------------------------


async def aprsis_script(server, reader, writer):
    writer.write(b"# aprsc 2.1.14-g5e22b37\r\n")
    await server.readline(reader)  # login
    writer.write(b"# logresp N0CALL unverified, server T2TEST\r\n")
    # a line split across writes, then CRLF split across writes
    writer.write(POSITION[:20].encode())
    await writer.drain()
    await asyncio.sleep(0.01)
    writer.write(POSITION[20:].encode() + b"\r")
    await writer.drain()
    await asyncio.sleep(0.01)
    writer.write(b"\n" + STATUS.encode() + b"\r\n")
    writer.write(b"not a packet\r\n")  # dropped
    writer.write(b"N0CALL>APRS:]unknown data type\r\n")  # dropped
    writer.write(b"# 22 Nov 2026 19:00:00 GMT T2TEST 127.0.0.1:14580\r\n")
    writer.write(MESSAGE.encode() + b"\r\n")
    await writer.drain()
    await server.read_until_closed(reader)


async def test_aprsis_login_and_receive():
    async with Server(aprsis_script).serving() as server:
        transport, protocol = await create_aprsis_connection(
            host="127.0.0.1",
            port=server.port,
            user="N0CALL",
            passcode="-1",
            command="filter r/49/-72/50",
        )
        frames = await asyncio.wait_for(_take(protocol, 3), 5)
        transport.close()
        await server.done.wait()

    login = server.received.decode().splitlines()[0]
    assert (
        login == f"user N0CALL pass -1 vers aprs3 {aprs.__version__} filter r/49/-72/50"
    )
    assert [str(f) for f in frames] == [POSITION, STATUS, MESSAGE]
    assert all(isinstance(f, APRSFrame) for f in frames)
    assert [type(f.info) for f in frames] == [PositionReport, StatusReport, Message]


async def _take(protocol, n):
    return [frame async for frame in protocol.read(n_frames=n)]


async def test_aprsis_write_and_eof():
    async def script(server, reader, writer):
        await server.readline(reader)  # login
        await server.readline(reader)  # the frame we send
        writer.write(STATUS.encode() + b"\r\n")
        await writer.drain()

    async with Server(script).serving() as server:
        transport, protocol = await create_aprsis_connection(
            host="127.0.0.1", port=server.port
        )
        protocol.write(APRSFrame.from_str(MESSAGE))
        # the server closes after one frame; read() ends at EOF
        frames = await read_all(protocol)
        await server.done.wait()

    assert server.received.decode().splitlines()[1] == MESSAGE
    assert server.received.endswith(b"\r\n")
    assert [str(f) for f in frames] == [STATUS]


def test_aprsis_sync_tcp_stop_without_start():
    tcp = aprs.TCP(host="127.0.0.1", port=1)
    tcp.stop()  # also what __del__ does; must not raise


def test_aprsis_sync_tcp_failed_start_cleans_up_quietly(monkeypatch):
    """Issue #8: a connect error in __enter__ must not make __del__ raise."""
    unraisable = []
    monkeypatch.setattr(sys, "unraisablehook", unraisable.append)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]  # closed again: connecting is refused
    with pytest.raises(OSError):
        with aprs.TCP(host="127.0.0.1", port=port, user="N0CALL"):
            pass
    gc.collect()
    assert unraisable == []


def test_aprsis_sync_tcp():
    with threaded_server(aprsis_script) as server:
        with aprs.TCP(host="127.0.0.1", port=server.port, user="N0CALL") as tcp:
            frames = tcp.read(min_frames=3)
        # stop() finishes closing: the server sees EOF without another loop run
        server.wait_done()
    assert [str(f) for f in frames] == [POSITION, STATUS, MESSAGE]


# --- KISS --------------------------------------------------------------------


def rf_bytes(tnc2: str) -> bytes:
    return bytes(APRSFrame.from_str(tnc2))


async def test_kiss_tcp_receive_and_write():
    # an info field with FEND/FESC bytes in it must be escaped and unescaped
    escaped_status = "N0CALL>APRS:>\xc0 and \xdb"

    async def script(server, reader, writer):
        writer.write(
            kiss_frame(rf_bytes(RF_POSITION))
            + kiss_frame(b"\x01\x02 not ax.25")  # dropped
            + kiss_frame(rf_bytes(escaped_status))
        )
        await writer.drain()
        # TNCs may send other commands; port 1 data is also a data frame
        writer.write(kiss_frame(rf_bytes(STATUS), command=0x10))
        await writer.drain()
        await server.read_until_closed(reader)

    async with Server(script).serving() as server:
        transport, protocol = await create_tcp_connection(
            host="127.0.0.1", port=server.port
        )
        frames = await asyncio.wait_for(_take(protocol, 2), 5)
        protocol.write(APRSFrame.from_str(MESSAGE))
        await asyncio.sleep(0.05)
        transport.close()
        await server.done.wait()

    assert [str(f) for f in frames] == [RF_POSITION, escaped_status]
    assert isinstance(frames[0].info, PositionReport)
    (payload,) = kiss_payloads(server.received)
    assert str(APRSFrame.from_bytes(payload)) == MESSAGE


async def test_kiss_serial_pty():
    master, slave = os.openpty()
    try:
        transport, protocol = await create_serial_connection(
            port=os.ttyname(slave), baudrate=9600
        )
        os.write(master, kiss_frame(rf_bytes(RF_POSITION)))
        (frame,) = await asyncio.wait_for(_take(protocol, 1), 5)
        assert str(frame) == RF_POSITION

        protocol.write(APRSFrame.from_str(STATUS))
        data = b""
        while data.count(FEND) < 2:
            data += await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(None, os.read, master, 1024),
                5,
            )
        (payload,) = kiss_payloads(data)
        assert str(APRSFrame.from_bytes(payload)) == STATUS
        transport.close()
    finally:
        os.close(master)
        os.close(slave)


def test_kiss_sync_tcpkiss():
    async def script(server, reader, writer):
        writer.write(kiss_frame(rf_bytes(RF_POSITION)))
        await writer.drain()
        await server.read_until_closed(reader)

    with threaded_server(script) as server:
        tnc = aprs.TCPKISS("127.0.0.1", server.port)
        tnc.start()
        try:
            (frame,) = tnc.read(min_frames=1)
            tnc.write(APRSFrame.from_str(STATUS))
        finally:
            tnc.stop()
        # stop() finishes closing: the server sees EOF without another loop run
        server.wait_done()

    assert str(frame) == RF_POSITION
    assert [str(APRSFrame.from_bytes(p)) for p in kiss_payloads(server.received)] == [
        STATUS
    ]


# --- helpers -----------------------------------------------------------------


@contextlib.contextmanager
def threaded_server(script):
    """Run a Server on its own event loop thread, for the sync wrappers."""
    loop = asyncio.new_event_loop()
    server = Server(script)
    ready = threading.Event()
    stop = asyncio.Event()

    async def main():
        async with server.serving():
            ready.set()
            await stop.wait()

    def wait_done(timeout=5):
        asyncio.run_coroutine_threadsafe(server.done.wait(), loop).result(timeout)

    server.wait_done = wait_done
    thread = threading.Thread(target=loop.run_until_complete, args=(main(),), daemon=True)
    thread.start()
    assert ready.wait(5)
    try:
        yield server
    finally:
        loop.call_soon_threadsafe(stop.set)
        thread.join(5)
        loop.close()
