import asyncio
import os

from aprs import APRSFrame, create_aprsis_connection, InformationField

MYCALL = os.environ.get("MYCALL", "N0CALL")
DESTINATION = os.environ.get("DESTINATION", "APZ069")
HOST = os.environ.get("APRSIS_HOST", "noam.aprs2.net")
PORT = int(os.environ.get("APRSIS_PORT", "14580"))
PASSCODE = os.environ.get("PASSCODE", "-1")
COMMAND = os.environ.get("COMMAND", "filter r/46.1/-122.9/50")
INFO = os.environ.get("INFO", ":TEST     :this is only a test message")


async def main():
    transport, protocol = await create_aprsis_connection(
        host=HOST,
        port=PORT,
        user=MYCALL,
        passcode=PASSCODE,
        command=COMMAND,
    )
    if int(PASSCODE) > 0:
        protocol.write(
            APRSFrame.ui(
                destination=DESTINATION,
                source=MYCALL,
                info=InformationField.from_bytes(INFO.encode("ascii")),
            )
        )

    async for packet in protocol.read():
        print(str(packet))
        print(repr(packet.info))


if __name__ == "__main__":
    asyncio.run(main())
