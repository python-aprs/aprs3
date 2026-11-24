"""APRS-IS send/receive protocol for async and sync use."""

import asyncio
import functools
import logging
import re
import socket
from collections.abc import Callable, Iterable
from typing import (
    Any,
    SupportsBytes,
)

from attrs import define, field, frozen
from ax253 import Frame, GenericDecoder, SyncFrameDecode, TNC2Decode, TNC2Protocol

# pylint: disable=cyclic-import
from .classes import APRSFrame
from .constants import APRSIS_FILTER_PORT, APRSIS_SERVERS, DEFAULT_MYCALL

# pylint: disable=duplicate-code
__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"
# pylint: enable=duplicate-code


log = logging.getLogger(__name__)


DEFAULT_KEEPALIVE_TIMEOUT = 60.0
"""
Seconds of silence after which an APRS-IS connection is considered dead.
Servers send a ``# ...`` comment line about every 20 seconds.
"""


def passcode(callsign: str) -> int:
    """
    The APRS-IS passcode for ``callsign``; the SSID doesn't matter.

    >>> passcode("N0CALL"), passcode("n0call-9")
    (13023, 13023)
    """
    call = callsign.upper().partition("-")[0][:10].encode("ascii")
    code = 0x73E2
    for i in range(0, len(call), 2):
        code ^= call[i] << 8
        if i + 1 < len(call):
            code ^= call[i + 1]
    return code & 0x7FFF


LOGRESP = re.compile(
    rb"#\s*logresp\s+(?P<callsign>\S+)\s+(?P<status>verified|unverified)"
    rb"(?:\s*,\s*server\s+(?P<server>\S+))?",
    re.IGNORECASE,
)


@frozen
class LoginResponse:
    """The server's ``# logresp`` reply to a login."""

    callsign: str
    verified: bool
    """False for a wrong or missing passcode: the server drops what we send."""
    server: str | None = None
    """The server's name, e.g. ``T2TEST``."""

    @classmethod
    def from_line(cls, line: bytes) -> "LoginResponse | None":
        """
        Parse a ``# logresp`` line, or return None for other server comments.

        >>> LoginResponse.from_line(b"# logresp N0CALL verified, server T2TEST")
        LoginResponse(callsign='N0CALL', verified=True, server='T2TEST')
        """
        match = LOGRESP.match(line.strip())
        if match is None:
            return None
        server = match.group("server")
        return cls(
            callsign=match.group("callsign").decode("latin1"),
            verified=match.group("status").lower() == b"verified",
            server=None if server is None else server.decode("latin1"),
        )


def _frame_from_line(line: bytes, encoding: str | None) -> APRSFrame:
    """
    The frame on a TNC2 line, with its info bytes unchanged.

    ax253 releases with an ``encoding`` on TNC2Decode read lines as that
    encoding (UTF-8 by default); older ones read them as Latin-1.
    """
    if encoding is None:
        return APRSFrame.from_str(line.decode("latin1"))
    return APRSFrame.from_str(
        line.decode(encoding, "surrogateescape"),
        encoding=encoding,  # ty: ignore[unknown-argument]
    )


@define
class APRSTNC2Decode(TNC2Decode):
    """Decode APRS-IS (TNC2 text) lines into ``APRSFrame`` objects."""

    comment_callback: Callable[[bytes], None] | None = field(default=None, kw_only=True)
    """Called with each ``#`` comment line the server sends."""

    def decode_frames(self, frame: bytes) -> Iterable[APRSFrame]:
        try:
            yield _frame_from_line(frame, getattr(self, "encoding", None))
        except Exception:  # pylint: disable=broad-except
            log.debug("Ignore frame decode error %r", frame, exc_info=True)

    def _decode_line(self, packet: bytes) -> Iterable[Frame]:
        if self.comment_callback is not None and packet.strip().startswith(b"#"):
            self.comment_callback(packet)
        yield from super()._decode_line(packet)


@define
class APRSISProtocol(TNC2Protocol):
    """
    Protocol for logging into APRS-IS servers (TNC2).

    After ``login()``, the server's reply is in ``login_response`` (await
    ``wait_for_login()`` to get it). The connection is closed when the server
    stays silent for ``keepalive_timeout`` seconds, so ``read()`` ends and a
    client can reconnect instead of waiting forever on a dead socket.
    """

    decoder: GenericDecoder[Frame] = field(factory=APRSTNC2Decode)
    keepalive_timeout: float | None = field(
        default=DEFAULT_KEEPALIVE_TIMEOUT, kw_only=True
    )
    """Seconds of silence before the connection is closed; None never closes it."""
    tcp_keepalive: bool = field(default=True, kw_only=True)
    """Also enable TCP keepalive (SO_KEEPALIVE) on the socket."""
    login_response: LoginResponse | None = field(default=None, init=False)
    """The server's ``# logresp`` reply, once it has arrived."""
    keepalive_expired: bool = field(default=False, init=False)
    """True if the connection was closed because the server went silent."""
    last_received: float | None = field(default=None, init=False)
    """``loop.time()`` when the server last sent anything."""
    _login_future: "asyncio.Future[LoginResponse]" = field(
        factory=asyncio.Future, init=False, repr=False
    )
    _watchdog: asyncio.TimerHandle | None = field(default=None, init=False, repr=False)
    _warned_unverified: bool = field(default=False, init=False, repr=False)

    def __attrs_post_init__(self) -> None:
        if (
            isinstance(self.decoder, APRSTNC2Decode)
            and self.decoder.comment_callback is None
        ):
            self.decoder.comment_callback = self._server_comment

    def _server_comment(self, line: bytes) -> None:
        response = LoginResponse.from_line(line)
        if response is None:
            return
        self.login_response = response
        if not self._login_future.done():
            self._login_future.set_result(response)
        if not response.verified:
            log.warning(
                "APRS-IS login for %s is unverified (server %s): the server "
                "drops packets we send. Check the passcode.",
                response.callsign,
                response.server,
            )

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        super().connection_made(transport)
        loop = asyncio.get_running_loop()
        self.last_received = loop.time()
        if self.tcp_keepalive:
            sock = transport.get_extra_info("socket")
            if sock is not None:
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                except OSError:  # pragma: no cover - platform specific
                    log.debug("Cannot enable TCP keepalive", exc_info=True)
        if self.keepalive_timeout is not None:
            self._watchdog = loop.call_later(self.keepalive_timeout, self._check_alive)

    def data_received(self, data: bytes) -> None:
        if self.transport is not None and not self.transport.is_closing():
            self.last_received = asyncio.get_running_loop().time()
        super().data_received(data)

    def _check_alive(self) -> None:
        self._watchdog = None
        transport, timeout = self.transport, self.keepalive_timeout
        if transport is None or transport.is_closing() or timeout is None:
            return
        loop = asyncio.get_running_loop()
        silent_for = loop.time() - (self.last_received or 0.0)
        if silent_for >= timeout:
            log.warning(
                "No data from the APRS-IS server for %.0f seconds: closing the "
                "connection",
                silent_for,
            )
            self.keepalive_expired = True
            # abort, not close: a dead peer would never take the buffered data
            transport.abort()
            return
        self._watchdog = loop.call_later(timeout - silent_for, self._check_alive)

    def connection_lost(self, exc: Exception | None) -> None:
        if self._watchdog is not None:
            self._watchdog.cancel()
            self._watchdog = None
        if not self._login_future.done():
            self._login_future.set_exception(
                ConnectionError("connection closed before the login response")
            )
            self._login_future.exception()  # nobody has to be waiting for it
        super().connection_lost(exc)

    def login(self, user: str, passcode: str | int, command: str = "") -> None:
        """
        Send the login line. ``passcode`` -1 logs in receive-only.

        The reply arrives later: see ``login_response`` and ``wait_for_login()``.
        """
        # pylint: disable=import-outside-toplevel
        # avoid circular import
        from . import __distribution__, __version__

        # pylint: enable=import-outside-toplevel

        self._connected_transport().write(
            f"user {user} pass {passcode} vers {__distribution__} {__version__} {command}\r\n".encode(
                "ascii"
            ),
        )

    async def wait_for_login(self, timeout: float | None = 10.0) -> LoginResponse:
        """
        Wait for the server's login response.

        :raises TimeoutError: no response within ``timeout`` seconds
        :raises ConnectionError: the connection closed first
        """
        return await asyncio.wait_for(asyncio.shield(self._login_future), timeout)

    @property
    def verified(self) -> bool | None:
        """Whether the server verified the login; None before its response."""
        if self.login_response is None:
            return None
        return self.login_response.verified

    def write(self, frame: SupportsBytes) -> None:
        """Send a frame; logs a warning if the login is unverified."""
        if self.verified is False and not self._warned_unverified:
            self._warned_unverified = True
            log.warning("Sending on an unverified APRS-IS login: the server will drop it")
        super().write(frame)


APRSDecode = APRSTNC2Decode
"""The former name of ``APRSTNC2Decode``."""


def _login_command(command: str, filter: str | None) -> str:  # pylint: disable=redefined-builtin
    """The text after the login: ``command``, then ``filter ...``."""
    if not filter:
        return command
    return " ".join(part for part in (command, f"filter {filter}") if part)


def _handle_kwargs(
    protocol_kwargs: dict[str, Any] | None,
    create_connection_kwargs: dict[str, Any] | None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Handle async connection kwarg combination to avoid duplication."""
    # a copy: the caller's dict must not collect protocol_factory
    create_connection_kwargs = dict(create_connection_kwargs or {})
    create_connection_kwargs.update(kwargs)
    create_connection_kwargs["protocol_factory"] = functools.partial(
        create_connection_kwargs.pop("protocol_factory", APRSISProtocol),
        **(protocol_kwargs or {}),
    )
    return create_connection_kwargs


async def create_aprsis_connection(  # pylint: disable=too-many-arguments
    host: str = APRSIS_SERVERS[0],
    port: int = APRSIS_FILTER_PORT,
    user: str = DEFAULT_MYCALL,
    passcode: str | int = "-1",
    command: str = "",
    protocol_kwargs: dict[str, Any] | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
    create_connection_kwargs: dict[str, Any] | None = None,
    login_timeout: float | None = None,
    filter: str | None = None,  # pylint: disable=redefined-builtin
) -> tuple[asyncio.BaseTransport, APRSISProtocol]:
    """
    Establish an async APRS-IS connection.

    :param host: the APRS-IS host to connect to
    :param port: the TCP port to connect to (14580 is usually a good choice)
    :param user: callsign of the user to authenticate
    :param passcode: APRS-IS passcode associated with the callsign (see
        ``passcode()``); -1 logs in receive-only
    :param command: initial command to send after connecting
    :param protocol_kwargs: These kwargs are passed directly to APRSISProtocol
    :param loop: override the asyncio event loop (default: the running loop)
    :param create_connection_kwargs: These kwargs are passed directly to
        loop.create_connection
    :param login_timeout: wait up to this many seconds for the server's login
        response (``protocol.login_response``) before returning; None returns
        right after sending the login
    :param filter: a server-side filter (``"r/46.1/-122.9/50"``), sent as
        ``filter ...`` after ``command``
    :raises TimeoutError: no login response within ``login_timeout``
    :return: (TCPTransport, APRSISProtocol)
    """
    if loop is None:
        loop = asyncio.get_running_loop()
    protocol: APRSISProtocol
    transport, protocol = await loop.create_connection(
        host=host,
        port=port,
        **_handle_kwargs(
            protocol_kwargs=protocol_kwargs,
            create_connection_kwargs=create_connection_kwargs,
        ),
    )
    await protocol.connection_future
    protocol.login(user, passcode, _login_command(command, filter))
    if login_timeout is not None:
        try:
            await protocol.wait_for_login(login_timeout)
        except BaseException:
            transport.close()
            raise
    return transport, protocol


class TCP(SyncFrameDecode[APRSFrame]):
    """
    APRSIS-over-TCP, for code without an event loop.

    The arguments are those of ``create_aprsis_connection``. Nothing
    connects until ``start()``.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        host: str = APRSIS_SERVERS[0],
        port: int = APRSIS_FILTER_PORT,
        user: str = DEFAULT_MYCALL,
        passcode: str | int = "-1",
        command: str = "",
        *args: Any,
        filter: str | None = None,  # pylint: disable=redefined-builtin
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.args = (host, port, user, passcode, command, *args)
        self.kwargs = dict(kwargs, filter=filter)

    def stop(self) -> None:
        """
        Close the connection and let the event loop finish closing it.

        asyncio transports release the socket on the next loop iteration
        after close(), and this class's loop only runs inside its calls, so
        the server would otherwise see the connection stay open.
        """
        if self._protocol is None or self._protocol.transport is None:
            return
        transport = self._protocol.transport
        if transport.is_closing():
            return  # already stopped (e.g. stop() and then __del__)
        transport.close()
        loop = self.loop
        if loop is None or loop.is_running() or loop.is_closed():
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            loop.run_until_complete(asyncio.sleep(0))
        # else: stop() (or __del__) ran inside another loop's coroutine; this
        # loop can't run here, and finishes closing the next time it runs

    def start(self, **kwargs: Any) -> None:
        """
        Open the APRS-IS connection and start decoding packets.
        """
        _, self.protocol = self.loop.run_until_complete(
            create_aprsis_connection(*self.args, **self.kwargs),
        )
        self.loop.run_until_complete(self.protocol.connection_future)

    @property
    def login_response(self) -> LoginResponse | None:
        """The server's login response, once it has arrived."""
        if self._protocol is None:
            return None
        return getattr(self._protocol, "login_response", None)
