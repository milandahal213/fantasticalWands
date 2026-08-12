"""
nfc_serial.py - read a LEGO Education connection card over NFC (WS1850S).

LEGO connection cards are NTAG21x tags (7-byte UID, SAK 0x00) that LEGO
pre-encodes; we only READ them. Layout confirmed by dumping real cards:

    page 4 : ASCII "L3G0"  (0x4C 0x33 0x47 0x30) - signature
    page 5 : [0x00, color, serial_hi, serial_lo]
                 color  = LEGO *firmware* color code (see COLOR_NAMES)
                 serial = (serial_hi << 8) | serial_lo   (big-endian uint16)

e.g. page5 = 00 02 04 66 -> Purple (2), serial 0x0466 = 1126
     page5 = 00 06 04 6d -> Green  (6), serial 0x046d = 1133

ul_read(4) returns 16 bytes = pages 4,5,6,7, so one read gives us both pages.
"""

import time

LEGO_SIG = b"L3G0"   # 0x4C 0x33 0x47 0x30, page 4 of every LEGO connection card
SIG_PAGE = 4

# LEGO firmware color codes (from legoeducation/rpc_message.py) - what the card stores.
COLOR_NAMES = {
    0: "Black", 1: "Magenta", 2: "Purple", 3: "Blue", 4: "Azure",
    5: "Turquoise", 6: "Green", 7: "Yellow", 8: "Orange", 9: "Red", 10: "White",
}


def color_name(code):
    return COLOR_NAMES.get(code, "color %d" % code)


def _detect(reader):
    """Full anticollision using WUPA (0x52) instead of REQA (0x26).

    WUPA wakes cards in BOTH the IDLE and HALT states; plain REQA misses a
    card we previously halt()'d, which is why polling would find a tag once
    and then never again. Mirrors reader.read_uid_full(), leaving the card
    ACTIVE so ul_read can follow. Returns (uid, sak) or None.
    """
    status, _ = reader.request(reader.PICC_REQALL)   # 0x52 = WUPA
    if status != reader.MI_OK:
        return None
    status, cl1 = reader.anticoll()
    if status != reader.MI_OK or len(cl1) < 5:
        return None
    sak = reader.select_tag(cl1)
    if sak < 0:                          # -1 == select failed; SAK 0x00 is valid (NTAG)
        return None
    if cl1[0] != reader.CT:
        return bytes(cl1[:4]), sak
    status, cl2 = reader.anticoll_cl2()
    if status != reader.MI_OK or len(cl2) < 5:
        return None
    sak2 = reader.select_tag_cl2(cl2)
    if sak2 < 0:
        return None
    return bytes(cl1[1:4]) + bytes(cl2[:4]), sak2


def wait_for_tag(reader, timeout_ms=10000):
    """Block until a tag is present and selected. Returns (uid, sak) or None."""
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        res = _detect(reader)
        if res:
            return res
        time.sleep_ms(80)
    return None


def _decode_record(reader):
    status, data = reader.ul_read(SIG_PAGE)   # 16 bytes = pages 4..7
    reader.halt()
    if status != reader.MI_OK or len(data) < 8 or bytes(data[0:4]) != LEGO_SIG:
        return None
    return (data[6] << 8) | data[7], data[5]   # (serial, color)


def read_card(reader):
    """Read a LEGO connection card, waiting up to 400ms. Returns (serial, color) or None."""
    if wait_for_tag(reader, timeout_ms=400) is None:
        return None
    return _decode_record(reader)


def read_card_now(reader):
    """Single-shot card read (no wait loop) - safe to poll from a fast loop.
    Returns (serial, color) or None if no card is on the reader right now."""
    if _detect(reader) is None:
        return None
    return _decode_record(reader)


def read_card_full_now(reader):
    """Single-shot read returning (uid, serial, color) or None. The uid (7 bytes)
    is needed to compute the broadcast beacon's card hash (lego_broadcast.card_hash)."""
    res = _detect(reader)
    if res is None:
        return None
    uid, sak = res
    rec = _decode_record(reader)
    if rec is None:
        return None
    return uid, rec[0], rec[1]
