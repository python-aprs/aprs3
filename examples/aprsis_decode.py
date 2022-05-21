import asyncio
import os

from aprs3 import InformationField
from kiss3 import tnc2

MYCALL = os.environ.get("MYCALL", "N0CALL")
DESTINATION = os.environ.get("DESTINATION", "APZ069")
HOST = os.environ.get("APRSIS_HOST", "noam.aprs2.net")
PORT = int(os.environ.get("APRSIS_PORT", "14580"))
PASSCODE = os.environ.get("PASSCODE", "-1")
COMMAND = os.environ.get("COMMAND", "filter r/46.1/-122.9/50")
INFO = os.environ.get("INFO", ":TEST     :this is only a test message")
DUMP_UNKNOWN_PACKETS = os.environ.get("DUMP_UNKNOWN_PACKETS", "unknown.log")
DUMP_KNOWN_PACKETS = os.environ.get("DUMP_KNOWN_PACKETS", "known.log")


unknown_packets = open(DUMP_UNKNOWN_PACKETS, "a", encoding="utf-8")
known_packets = open(DUMP_KNOWN_PACKETS, "a", encoding="utf-8")


async def main():
    transport, protocol = await tnc2.create_aprsis_connection(
        host=HOST, port=PORT, user=MYCALL, passcode=PASSCODE, command=COMMAND
    )
    async for packet in protocol.read():
        print(str(packet))
        try:
            iframe = InformationField.from_bytes(packet.info)
        except Exception as e:
            print("\t{}\n\n".format(e))
            unknown_packets.write("{}\n\t{}\n\n".format(packet, e))
            continue
        if type(iframe) is InformationField:
            unknown_packets.write("{}\nNo decoder for {!r}\n\n".format(packet, iframe.data_type))
        else:
            known_packets.write("{}\n{!r}\n\n".format(packet, iframe))
        print("\t{!r}\n\n".format(iframe))


if __name__ == "__main__":
    asyncio.run(main())

