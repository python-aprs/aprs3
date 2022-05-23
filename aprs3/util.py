"""Python APRS Module Utility Functions."""

from datetime import datetime, timezone

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


def utcnow_tz():
    return datetime.now(tz=timezone.utc)
