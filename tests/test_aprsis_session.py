"""APRS-IS login responses, passcodes and dead-connection detection (#34, #35)."""

import asyncio
import logging
import socket

import pytest

import aprs
from aprs import APRSFrame, LoginResponse, passcode
from aprs.aprsis import APRSISProtocol, create_aprsis_connection

from .test_io import STATUS, Server, read_all, threaded_server


@pytest.mark.parametrize(
    "callsign, code",
    [("N0CALL", 13023), ("n0call", 13023), ("N0CALL-9", 13023), ("KF7HVM", 22945)],
)
def test_passcode(callsign, code):
    assert passcode(callsign) == code


def test_passcode_odd_length_and_long_calls():
    # odd-length calls hash their last character into the high byte only
    assert 0 <= passcode("W1AW") <= 0x7FFF
    assert passcode("W1A") != passcode("W1AW")
    # only the first 10 characters count
    assert passcode("ABCDEFGHIJK") == passcode("ABCDEFGHIJ")


@pytest.mark.parametrize(
    "line, expected",
    [
        (
            b"# logresp N0CALL verified, server T2TEST",
            LoginResponse("N0CALL", True, "T2TEST"),
        ),
        (
            b"# logresp N0CALL-9 unverified, server T2TEST\r\n",
            LoginResponse("N0CALL-9", False, "T2TEST"),
        ),
        (b"#logresp N0CALL Verified", LoginResponse("N0CALL", True, None)),
        (b"# aprsc 2.1.14-g5e22b37", None),
        (b"# 22 Nov 2026 19:00:00 GMT T2TEST 127.0.0.1:14580", None),
    ],
)
def test_login_response_from_line(line, expected):
    assert LoginResponse.from_line(line) == expected


def logresp_script(status: str, then: bytes = b""):
    async def script(server, reader, writer):
        writer.write(b"# aprsc 2.1.14-g5e22b37\r\n")
        await server.readline(reader)  # login
        writer.write(f"# logresp N0CALL {status}, server T2TEST\r\n".encode())
        writer.write(then)
        await writer.drain()
        await server.read_until_closed(reader)

    return script


@pytest.mark.parametrize("status, verified", [("verified", True), ("unverified", False)])
async def test_wait_for_login(status, verified):
    async with Server(logresp_script(status)).serving() as server:
        transport, protocol = await create_aprsis_connection(
            host="127.0.0.1",
            port=server.port,
            passcode=passcode("N0CALL"),
            login_timeout=5,
        )
        assert protocol.login_response == LoginResponse("N0CALL", verified, "T2TEST")
        assert protocol.verified is verified
        assert await protocol.wait_for_login() is protocol.login_response
        transport.close()
        await server.done.wait()
    assert f"pass {passcode('N0CALL')} vers" in server.received.decode()


async def test_login_response_arrives_without_waiting():
    async with Server(
        logresp_script("verified", STATUS.encode() + b"\r\n")
    ).serving() as server:
        transport, protocol = await create_aprsis_connection(
            host="127.0.0.1", port=server.port
        )
        assert protocol.verified is None  # not here yet
        (frame,) = [f async for f in protocol.read(n_frames=1)]
        assert str(frame) == STATUS
        assert protocol.verified is True
        transport.close()
        await server.done.wait()


async def test_login_timeout_closes_connection():
    async def script(server, reader, writer):
        await server.read_until_closed(reader)  # never answers

    async with Server(script).serving() as server:
        with pytest.raises(TimeoutError):
            await create_aprsis_connection(
                host="127.0.0.1", port=server.port, login_timeout=0.05
            )
        await asyncio.wait_for(server.done.wait(), 5)


async def test_connection_closed_before_login_response():
    async def script(server, reader, writer):
        await server.readline(reader)  # login, then hang up

    async with Server(script).serving() as server:
        with pytest.raises(ConnectionError):
            await create_aprsis_connection(
                host="127.0.0.1", port=server.port, login_timeout=5
            )


async def test_unverified_write_warns_once(caplog):
    async with Server(logresp_script("unverified")).serving() as server:
        transport, protocol = await create_aprsis_connection(
            host="127.0.0.1", port=server.port, login_timeout=5
        )
        with caplog.at_level(logging.WARNING, logger="aprs.aprsis"):
            protocol.write(APRSFrame.from_str(STATUS))
            protocol.write(APRSFrame.from_str(STATUS))
        transport.close()
        await server.done.wait()
    assert [r.message for r in caplog.records].count(
        "Sending on an unverified APRS-IS login: the server will drop it"
    ) == 1
    assert server.received.decode().count(STATUS) == 2  # still sent


async def test_keepalive_timeout_closes_a_silent_connection():
    async def script(server, reader, writer):
        await server.readline(reader)  # login, then silence
        await server.read_until_closed(reader)

    async with Server(script).serving() as server:
        transport, protocol = await create_aprsis_connection(
            host="127.0.0.1",
            port=server.port,
            protocol_kwargs={"keepalive_timeout": 0.1},
        )
        assert await read_all(protocol) == []  # read() ends instead of hanging
        assert transport.is_closing()
        assert protocol.keepalive_expired
        await asyncio.wait_for(server.done.wait(), 5)


async def test_server_comments_keep_the_connection_alive():
    async def script(server, reader, writer):
        await server.readline(reader)
        for _ in range(6):
            writer.write(b"# keepalive\r\n")
            await writer.drain()
            await asyncio.sleep(0.05)
        writer.write(STATUS.encode() + b"\r\n")
        await writer.drain()

    async with Server(script).serving() as server:
        transport, protocol = await create_aprsis_connection(
            host="127.0.0.1",
            port=server.port,
            protocol_kwargs={"keepalive_timeout": 0.15},
        )
        frames = await read_all(protocol)
        await server.done.wait()
    # 0.3 s of comments outlived the 0.15 s timeout; the server then closed
    assert [str(f) for f in frames] == [STATUS]
    assert not protocol.keepalive_expired


async def test_keepalive_can_be_disabled():
    async def script(server, reader, writer):
        await server.readline(reader)
        await asyncio.sleep(0.2)
        writer.write(STATUS.encode() + b"\r\n")
        await writer.drain()

    async with Server(script).serving() as server:
        transport, protocol = await create_aprsis_connection(
            host="127.0.0.1",
            port=server.port,
            protocol_kwargs={"keepalive_timeout": None, "tcp_keepalive": False},
        )
        frames = await read_all(protocol)
        await server.done.wait()
    assert [str(f) for f in frames] == [STATUS]
    sock = transport.get_extra_info("socket")
    assert sock is None or sock.fileno() == -1  # closed by now


async def test_tcp_keepalive_is_enabled():
    async with Server(logresp_script("verified")).serving() as server:
        transport, protocol = await create_aprsis_connection(
            host="127.0.0.1", port=server.port
        )
        sock = transport.get_extra_info("socket")
        assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE)
        transport.close()
        await server.done.wait()


async def test_custom_decoder_is_left_alone():
    class Decoder(aprs.aprsis.APRSDecode):
        pass

    decoder = Decoder(comment_callback=print)
    protocol = APRSISProtocol(decoder=decoder)
    assert decoder.comment_callback is print
    assert protocol.verified is None


def test_sync_tcp_login_response():
    with threaded_server(logresp_script("verified", STATUS.encode() + b"\r\n")) as server:
        tcp = aprs.TCP(host="127.0.0.1", port=server.port, user="N0CALL", login_timeout=5)
        assert tcp.login_response is None  # not started
        with tcp:
            assert tcp.login_response == LoginResponse("N0CALL", True, "T2TEST")
            assert [str(f) for f in tcp.read(min_frames=1)] == [STATUS]
        server.wait_done()
