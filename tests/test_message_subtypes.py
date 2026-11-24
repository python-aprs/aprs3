"""Message subtypes: ack/rej, reply-ack, bulletins, announcements, NWS (#32)."""

import pytest

from aprs import APRSFrame, Message


def msg(text: str) -> Message:
    info = APRSFrame.from_str(f"N0CALL>APRS::{text}").info
    assert isinstance(info, Message)
    return info


@pytest.mark.parametrize(
    "text, is_ack, is_rej, acked, reply_ack",
    [
        ("WU2Z     :ack003", True, False, b"003", None),
        ("WU2Z     :rej003", False, True, b"003", None),
        ("WU2Z     :ackAB}CD", True, False, b"AB", b"CD"),
        ("WU2Z     :ackAB}", True, False, b"AB", b""),
        ("WU2Z     :rejAB}CD", False, True, b"AB", b"CD"),
        # ordinary text that starts with "ack" is not an ack
        ("WU2Z     :acknowledged, thanks", False, False, None, None),
        ("WU2Z     :ack", False, False, None, None),
        ("WU2Z     :ack 12", False, False, None, None),
        ("WU2Z     :Ack12", False, False, None, None),
        # a numbered message is never an ack
        ("WU2Z     :ack12{5", False, False, None, None),
    ],
)
def test_ack_rej(text, is_ack, is_rej, acked, reply_ack):
    m = msg(text)
    assert (m.is_ack, m.is_rej, m.acked_number) == (is_ack, is_rej, acked)
    if m.number is None:
        assert m.reply_ack == reply_ack


@pytest.mark.parametrize(
    "text, number, message_number, reply_ack",
    [
        ("WU2Z     :Testing", None, None, None),
        ("WU2Z     :Testing{003", b"003", b"003", None),
        ("WU2Z     :Testing{AB}", b"AB}", b"AB", b""),
        ("WU2Z     :Testing{AB}CD", b"AB}CD", b"AB", b"CD"),
    ],
)
def test_message_number_and_reply_ack(text, number, message_number, reply_ack):
    m = msg(text)
    assert (m.number, m.message_number, m.reply_ack) == (
        number,
        message_number,
        reply_ack,
    )


@pytest.mark.parametrize(
    "addressee, bulletin, announcement, bulletin_id, group, nws",
    [
        ("BLN1     ", True, False, b"1", b"", False),
        ("BLNA     ", False, True, b"A", b"", False),
        ("BLN3WX   ", True, False, b"3", b"WX", False),
        ("NWS-WARN ", False, False, None, None, True),
        ("SKYCWA   ", False, False, None, None, True),
        ("WU2Z     ", False, False, None, None, False),
        ("BLN      ", False, False, None, None, False),
        ("BLNX1234 ", False, True, b"X", b"1234", False),
    ],
)
def test_bulletins(addressee, bulletin, announcement, bulletin_id, group, nws):
    m = msg(f"{addressee}:text")
    assert m.is_bulletin is bulletin
    assert m.is_announcement is announcement
    assert m.bulletin_id == bulletin_id
    assert m.bulletin_group == group
    assert m.is_nws is nws


def test_new_message():
    m = Message.new("N0CALL-2", "hello", number="12")
    assert bytes(m) == b":N0CALL-2 :hello{12"
    assert APRSFrame.ui("APRS", "N0CALL", info=bytes(m)).info == Message.from_bytes(
        bytes(m)
    )
    assert bytes(Message.new(b"N0CALL", b"hi")) == b":N0CALL   :hi"


def test_new_message_with_reply_ack():
    m = Message.new("N0CALL", "hello", number="12", reply_ack="AB")
    assert bytes(m) == b":N0CALL   :hello{12}AB"
    decoded = Message.from_bytes(bytes(m))
    assert (decoded.message_number, decoded.reply_ack) == (b"12", b"AB")
    with pytest.raises(ValueError):
        Message.new("N0CALL", "hello", reply_ack="AB")


def test_ack_for_round_trips():
    ack = Message.from_bytes(bytes(Message.ack_for("N0CALL-2", "12", reply_ack="AB")))
    assert (ack.addressee, ack.is_ack, ack.acked_number, ack.reply_ack) == (
        b"N0CALL-2",
        True,
        b"12",
        b"AB",
    )
    rej = Message.from_bytes(bytes(Message.ack_for("N0CALL", b"7", reject=True)))
    assert rej.is_rej and rej.acked_number == b"7" and rej.reply_ack is None
