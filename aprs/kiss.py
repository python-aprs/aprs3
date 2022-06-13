"""Helpers for attaching TNC via Serial KISS or KISS-over-TCP"""
import logging
from typing import Iterable

from attrs import define, field

import kiss

from .classes import APRSFrame

# pylint: disable=duplicate-code
__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"
# pylint: enable=duplicate-code


log = logging.getLogger(__name__)


@define
class APRSDecode(kiss.KISSDecode):
    strip_df_start: bool = field(default=True, converter=lambda v: True)

    def decode_frames(self, frame: bytes) -> Iterable[APRSFrame]:
        for kiss_frame in super().decode_frames(frame):
            try:
                yield APRSFrame.from_bytes(kiss_frame)
            except Exception:  # pylint: disable=broad-except
                log.debug("Ignore frame AX.25 decode error %r", frame, exc_info=True)


async def create_tcp_connection(*args, protocol_kwargs=None, **kwargs):
    if protocol_kwargs is None:
        protocol_kwargs = {}
    protocol_kwargs["decoder"] = protocol_kwargs.pop("decoder", APRSDecode())
    return await kiss.create_tcp_connection(
        *args, protocol_kwargs=protocol_kwargs, **kwargs
    )


async def create_serial_connection(*args, protocol_kwargs=None, **kwargs):
    if protocol_kwargs is None:
        protocol_kwargs = {}
    protocol_kwargs["decoder"] = protocol_kwargs.pop("decoder", APRSDecode())
    return await kiss.create_serial_connection(
        *args, protocol_kwargs=protocol_kwargs, **kwargs
    )


class TCPKISS(kiss.TCPKISS):
    decode_class = APRSDecode


class SerialKISS(kiss.SerialKISS):
    decode_class = APRSDecode
