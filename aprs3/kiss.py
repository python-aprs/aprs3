"""Helpers for attaching TNC via Serial KISS or KISS-over-TCP"""
import logging
from typing import Iterable

from attrs import define, field

import kiss3
import kiss3.util

from .classes import APRSFrame

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


log = logging.getLogger(__name__)


@define
class APRSDecode(kiss3.KISSDecode):
    strip_df_start: bool = field(default=True, converter=lambda v: True)

    def decode_frames(self, frame: bytes) -> Iterable[APRSFrame]:
        for kiss_frame in super().decode_frames(frame):
            try:
                yield from APRSFrame.from_bytes(kiss_frame)
            except Exception:
                log.debug("Ignore frame AX.25 decode error %r", frame, exc_info=True)


async def create_tcp_connection(*args, protocol_kwargs=None, **kwargs):
    if protocol_kwargs is None:
        protocol_kwargs = {}
    protocol_kwargs["decoder"] = protocol_kwargs.pop("decoder", APRSDecode())
    return await kiss3.create_tcp_connection(
        *args, protocol_kwargs=protocol_kwargs, **kwargs
    )


async def create_serial_connection(*args, protocol_kwargs=None, **kwargs):
    if protocol_kwargs is None:
        protocol_kwargs = {}
    protocol_kwargs["decoder"] = protocol_kwargs.pop("decoder", APRSDecode())
    return await kiss3.create_serial_connection(
        *args, protocol_kwargs=protocol_kwargs, **kwargs
    )


class TCPKISS(kiss3.TCPKISS):
    decode_class = APRSDecode


class SerialKISS(kiss3.SerialKISS):
    decode_class = APRSDecode
