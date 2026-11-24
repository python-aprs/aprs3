"""The scripts in examples/ run and print what their docstrings say."""

import asyncio
import pathlib
import socket
import sys
import threading

import pytest

import aprs

EXAMPLES = pathlib.Path(__file__).parent.parent / "examples"
sys.path.insert(0, str(EXAMPLES))

import aprs_decode  # noqa: E402
import aprsis_monitor  # noqa: E402
import beacon  # noqa: E402

MOBILE = "KF7HVM-9>APZ069,WIDE1-1:!4610.00N/12255.00W>090/025/A=000500"
MOBILE_OUT = (
    "KF7HVM-9   position 46.16667, -122.91667  symbol />  course 90° 25 kn  500 ft"
)
MONITOR_OUT = (
    "KF7HVM-9     19.6 km N  position 46.16667, -122.91667  symbol />"
    "  course 90° 25 kn  500 ft"
)


@pytest.mark.parametrize(
    "line, expected",
    [
        (MOBILE, MOBILE_OUT),
        (MOBILE + " on the road", MOBILE_OUT + "  'on the road'"),
        (
            "KF7HVM>APZ069::N0CALL   :hello there{42",
            "KF7HVM     message to N0CALL: hello there  #42",
        ),
        ("KF7HVM>APZ069:>Monitoring 144.390", "KF7HVM     status: Monitoring 144.390"),
        (
            "KF7HVM>APZ069:;NET 7PM  _111111z4610.00N/12255.00W? weekly net",
            "KF7HVM     object 'NET 7PM' (killed) at 46.16667, -122.91667  symbol /?"
            "  'weekly net'",
        ),
        (
            "N0CALL>APRS:)AID #2!4903.50N/07201.75WA",
            "N0CALL     item 'AID #2' at 49.05833, -72.02917  symbol /A",
        ),
        (
            "N0CALL>APRS:=4903.50N/07201.75W#PHG5132",
            "N0CALL     position 49.05833, -72.02917  symbol /#  PHG5132",
        ),
        ("N0CALL>APRS:T#005,199,000", "N0CALL     telemetry_data: T#005,199,000"),
    ],
)
def test_describe(line, expected):
    assert aprs_decode.describe(aprs.APRSFrame.from_str(line)) == expected


def test_decode_lines_skips_comments_and_reports_errors():
    out = list(aprs_decode.decode_lines(["# aprsc 2.1", "", "not a packet", MOBILE]))
    assert out[0].startswith("could not decode 'not a packet'")
    assert out[1] == MOBILE_OUT


def test_decode_docstring_example(capsys):
    aprs_decode.main([MOBILE])
    assert capsys.readouterr().out.strip() == MOBILE_OUT
    doc = aprs_decode.__doc__ or ""
    assert MOBILE in doc and MOBILE_OUT in doc


def test_line_for_adds_distance_and_direction():
    frame = aprs.APRSFrame.from_str("N0CALL>APRS:!4700.00N/12300.00W-")
    line = aprsis_monitor.line_for(frame, (46.0, -123.0))
    assert "111.2 km N " in line
    frame = aprs.APRSFrame.from_str("N0CALL>APRS:!4600.00N/12400.00W-")
    assert " km W " in aprsis_monitor.line_for(frame, (46.0, -123.0))
    status = aprs.APRSFrame.from_str("N0CALL>APRS:>hi")
    assert aprsis_monitor.line_for(status, (46.0, -123.0)) == aprsis_monitor.describe(
        status
    )


async def test_monitor_against_fake_aprsis(capsys):
    login = asyncio.get_running_loop().create_future()

    async def serve(reader, writer):
        writer.write(b"# aprsc 2.1.14\r\n")
        login.set_result(await reader.readline())
        writer.write(b"# logresp N0CALL unverified\r\n" + MOBILE.encode() + b"\r\n")
        await writer.drain()
        await reader.read()  # until the monitor disconnects
        writer.close()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        args = ["--near", "46.0", "-123.0", "--range", "30", "--count", "1"]
        args += ["--server", f"127.0.0.1:{port}"]
        parser_args = aprsis_monitor.make_parser().parse_args(args)
        await asyncio.wait_for(aprsis_monitor.monitor(parser_args), 5)
    assert b"filter r/46.0/-123.0/30.0" in login.result()
    out = capsys.readouterr().out.strip()
    assert out == MONITOR_OUT
    assert MONITOR_OUT.removesuffix("  500 ft") in (aprsis_monitor.__doc__ or "")


class Listener:
    """A TCP server thread that records everything one client sends."""

    def __init__(self, greeting=b""):
        self.sock = socket.create_server(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.greeting = greeting
        self.received = b""
        self.done = threading.Event()
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        conn, _ = self.sock.accept()
        conn.sendall(self.greeting)
        while data := conn.recv(4096):
            self.received += data
        conn.close()
        self.done.set()

    def close(self):
        self.sock.close()


BEACON = ["--call", "N0CALL-10", "--lat", "46.1", "--lon", "-122.9"]
BEACON_TNC2 = "N0CALL-10>APZ069,WIDE1-1:=4606.00N/12254.00W-Home station"


def test_beacon_to_kiss_tnc(capsys):
    tnc = Listener()
    try:
        beacon.main([*BEACON, "--tcp", f"127.0.0.1:{tnc.port}"])
        assert tnc.done.wait(5)
    finally:
        tnc.close()
    assert capsys.readouterr().out.strip() == BEACON_TNC2
    assert BEACON_TNC2 in (beacon.__doc__ or "")
    (frame,) = aprs.kiss.APRSDecode().update(tnc.received)
    assert str(frame) == BEACON_TNC2


def test_beacon_to_aprsis(capsys):
    server = Listener(greeting=b"# aprsc 2.1.14\r\n")
    try:
        beacon.main(
            [
                *BEACON,
                "--altitude",
                "120",
                "--symbol",
                "\\&",
                "--aprsis",
                f"127.0.0.1:{server.port}",
                "--passcode",
                "12345",
            ]
        )
        assert server.done.wait(5)
    finally:
        server.close()
    login, packet = server.received.decode().splitlines()
    assert login.startswith("user N0CALL-10 pass 12345")
    # no digipeater path on APRS-IS
    assert packet == "N0CALL-10>APZ069:=4606.00N\\12254.00W&/A=000120Home station"
    assert capsys.readouterr().out.strip() == packet


def test_beacon_needs_passcode_for_aprsis():
    with pytest.raises(SystemExit, match="passcode"):
        beacon.main([*BEACON, "--aprsis", "localhost:14580"])
