"""APRS-IS send/receive protocol for async and sync use."""
import asyncio
import functools
import logging
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    Type,
    Union,
)

from attrs import define, field

from kiss3 import AbstractKISS, TNC2Protocol
from kiss3.tnc2 import TNC2Decode
from kiss3.util import FrameDecodeProtocol, GenericDecoder

from .classes import APRSFrame
from .constants import APRSIS_SERVERS, APRSIS_FILTER_PORT, DEFAULT_MYCALL

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


log = logging.getLogger(__name__)


@define
class APRSDecode(TNC2Decode):
    """Decode info fields as APRS."""

    @staticmethod
    def decode_frames(frame: bytes) -> Iterable[APRSFrame]:
        try:
            yield APRSFrame.from_str(frame.decode("latin1"))
        except Exception:
            log.debug("Ignore frame decode error %r", frame, exc_info=True)


@define
class APRSISProtocol(TNC2Protocol):
    """Protocol for logging into APRS-IS servers (TNC2)."""

    decoder: GenericDecoder = field(factory=APRSDecode)

    def login(self, user: str, passcode: str, command: str):
        # avoid circular import
        from . import __distribution__, __version__

        self.transport.write(
            "user {} pass {} vers {} {} {}\r\n".format(
                user,
                passcode,
                __distribution__,
                __version__,
                command,
            ).encode("ascii"),
        )


def _handle_kwargs(
    protocol_kwargs: Dict[str, Any],
    create_connection_kwargs: Dict[str, Any],
    **kwargs: Any
) -> Dict[str, Any]:
    """Handle async connection kwarg combination to avoid duplication."""
    if create_connection_kwargs is None:
        create_connection_kwargs = {}
    create_connection_kwargs.update(kwargs)
    create_connection_kwargs["protocol_factory"] = functools.partial(
        create_connection_kwargs.pop("protocol_factory", APRSISProtocol),
        **(protocol_kwargs or {}),
    )
    return create_connection_kwargs


async def create_aprsis_connection(
    host: str = APRSIS_SERVERS[0],
    port: int = APRSIS_FILTER_PORT,
    user: str = DEFAULT_MYCALL,
    passcode: str = "-1",
    command: str = "",
    protocol_kwargs: Optional[Dict[str, Any]] = None,
    loop: Optional[asyncio.BaseEventLoop] = None,
    create_connection_kwargs: Optional[Dict[str, Any]] = None,
) -> Tuple[asyncio.BaseTransport, APRSISProtocol]:
    """
    Establish an async APRS-IS connection.

    :param host: the APRS-IS host to connect to
    :param port: the TCP port to connect to (14580 is usually a good choice)
    :param user: callsign of the user to authenticate
    :param passcode: APRS-IS passcode associated with the callsign
    :param command: initial command to send after connecting
    :param protocol_kwargs: These kwargs are passed directly to APRSISProtocol
    :param loop: override the asyncio event loop (default calls `get_event_loop()`)
    :param create_connection_kwargs: These kwargs are passed directly to
        loop.create_connection
    :return: (TCPTransport, APRSISProtocol)
    """
    if loop is None:
        loop = asyncio.get_event_loop()
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
    protocol.login(user, passcode, command)
    return transport, protocol


class TCP(AbstractKISS):
    """APRSIS-over-TCP."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__()
        self.args = args
        self.kwargs = kwargs

    def stop(self) -> None:
        if self.protocol:
            self.protocol.transport.close()

    def start(self) -> None:
        """
        Initializes the KISS device and commits configuration.
        """
        _, self.protocol = self.loop.run_until_complete(
            create_aprsis_connection(*self.args, **self.kwargs),
        )
        self.loop.run_until_complete(self.protocol.connection_future)
