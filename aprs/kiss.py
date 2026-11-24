"""Helpers for attaching TNC via Serial KISS or KISS-over-TCP"""

import logging
from collections.abc import Iterable

import kiss
from attrs import define, field
from kiss.kiss import GenericKISSDecode, handle_fend

from .classes import APRSFrame

# pylint: disable=duplicate-code
__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"
# pylint: enable=duplicate-code


log = logging.getLogger(__name__)


@define
class APRSKISSDecode(GenericKISSDecode[APRSFrame]):
    """Decode KISS frames from a TNC into ``APRSFrame`` objects."""

    strip_df_start: bool = field(default=True, converter=lambda v: True)

    def decode_frames(self, frame: bytes) -> Iterable[APRSFrame]:
        kiss_frame = handle_fend(frame, strip_df_start=self.strip_df_start)
        if kiss_frame is not None:
            try:
                yield APRSFrame.from_bytes(kiss_frame)
            except Exception:  # pylint: disable=broad-except
                log.debug("Ignore frame AX.25 decode error %r", frame, exc_info=True)


APRSDecode = APRSKISSDecode
"""The former name of ``APRSKISSDecode``."""


async def create_tcp_connection(*args, protocol_kwargs=None, **kwargs):
    if protocol_kwargs is None:
        protocol_kwargs = {}
    protocol_kwargs["decoder"] = protocol_kwargs.pop("decoder", APRSKISSDecode())
    return await kiss.create_tcp_connection(
        *args, protocol_kwargs=protocol_kwargs, **kwargs
    )


async def create_serial_connection(*args, protocol_kwargs=None, **kwargs):
    if protocol_kwargs is None:
        protocol_kwargs = {}
    protocol_kwargs["decoder"] = protocol_kwargs.pop("decoder", APRSKISSDecode())
    return await kiss.create_serial_connection(
        *args, protocol_kwargs=protocol_kwargs, **kwargs
    )


class TCPKISS(kiss.TCPKISS):
    decode_class = APRSKISSDecode


class SerialKISS(kiss.SerialKISS):
    decode_class = APRSKISSDecode
