"""
PlaygroundV5 - NFC Tag Writer (Color + Number format)
=======================================================
Board: Seeed XIAO ESP32-C6
NFC: PN532 on I2C (SDA=GPIO22, SCL=GPIO23)

Writes blank NTAG/Ultralight tags using the format we reverse-engineered
from reading existing tags:

    Page 4: 4C 33 47 30   ("L3G0" magic header)
    Page 5: 00 CC NN NN   (CC = color code, NNNN = card number, big-endian)

Run this, type in a color + number, tap a blank tag, and it writes it.
"""

import machine
import time

# ─────────────────────────────────────────────
# PIN CONFIG
# ─────────────────────────────────────────────
I2C_SDA = 22
I2C_SCL = 23
PN532_ADDR = 0x24

# ─────────────────────────────────────────────
# COLOR CODE TABLE (same mapping as the reader)
# ─────────────────────────────────────────────
COLOR_CODES = {
    "pink":   0x01,
    "purple": 0x02,
    "blue":   0x03,
    "yellow": 0x07,
    "orange": 0x08,
    "red":    0x09,
    "teal": 0x05,
    "green":  0x06
}

MAGIC_HEADER = bytes([0x4C, 0x33, 0x47, 0x30])  # "L3G0"

# ─────────────────────────────────────────────
# PN532 CONSTANTS
# ─────────────────────────────────────────────
TFI_HOST2PN532 = 0xD4
TFI_PN5322HOST = 0xD5

CMD_GETFIRMWAREVERSION  = 0x02
CMD_SAMCONFIGURATION    = 0x14
CMD_INLISTPASSIVETARGET = 0x4A
CMD_INDATAEXCHANGE      = 0x40

MIFARE_CMD_READ  = 0x30
NTAG_CMD_WRITE   = 0xA2

TAG_TYPES = {
    (0x0044, 0x00): "MIFARE Ultralight / NTAG2xx",
    (0x0004, 0x00): "MIFARE Ultralight / NTAG2xx",
    (0x0004, 0x20): "MIFARE Plus / NTAG",
}


class PN532:
    def __init__(self, i2c, addr=0x24):
        self.i2c = i2c
        self.addr = addr
        self.debug = False

    def _wait_ready(self, timeout=1000):
        start = time.ticks_ms()
        while True:
            try:
                status = self.i2c.readfrom(self.addr, 1)
                if status[0] == 0x01:
                    return True
            except OSError:
                pass
            if time.ticks_diff(time.ticks_ms(), start) > timeout:
                return False
            time.sleep_ms(10)

    def _write_command(self, cmd, params=b''):
        payload = bytes([TFI_HOST2PN532, cmd]) + bytes(params)
        length = len(payload)
        lcs = (~length + 1) & 0xFF
        frame = bytearray([0x00, 0x00, 0xFF, length, lcs])
        frame.extend(payload)
        dcs = (~sum(payload) + 1) & 0xFF
        frame.append(dcs)
        frame.append(0x00)
        if self.debug:
            print(f"    >> TX: {' '.join(f'{b:02X}' for b in frame)}")
        self.i2c.writeto(self.addr, frame)

    def _read_ack(self, timeout=500):
        if not self._wait_ready(timeout):
            raise RuntimeError("Timeout waiting for ACK ready")
        ack = self.i2c.readfrom(self.addr, 7)
        raw = bytes(ack)
        for i in range(len(raw) - 3):
            if raw[i] == 0x00 and raw[i+1] == 0xFF and raw[i+2] == 0x00 and raw[i+3] == 0xFF:
                return True
        raise RuntimeError(f"Bad ACK: {' '.join(f'{b:02X}' for b in ack)}")

    def _read_response(self, timeout=1000):
        if not self._wait_ready(timeout):
            raise RuntimeError("Timeout waiting for response ready")
        buf = self.i2c.readfrom(self.addr, 64)
        raw = bytes(buf)
        offset = -1
        for i in range(len(raw) - 4):
            if raw[i] == 0x00 and raw[i+1] == 0xFF:
                if i + 2 < len(raw) and raw[i+2] != 0x00:
                    offset = i
                    break
                elif i + 2 < len(raw) and raw[i+2] == 0x00 and i + 3 < len(raw) and raw[i+3] != 0xFF:
                    offset = i
                    break
        if offset < 0:
            raise RuntimeError("No frame start found in response")

        frame_len = raw[offset + 2]
        lcs = raw[offset + 3]
        if ((frame_len + lcs) & 0xFF) != 0:
            raise RuntimeError(f"Length checksum error: len={frame_len} lcs={lcs}")

        data_start = offset + 4
        data = raw[data_start: data_start + frame_len]
        if len(data) < frame_len:
            raise RuntimeError(f"Short response: got {len(data)}, expected {frame_len}")

        dcs = raw[data_start + frame_len]
        if ((sum(data) + dcs) & 0xFF) != 0:
            raise RuntimeError("Data checksum error")

        return data

    def _send_command(self, cmd, params=b'', timeout=1000):
        self._write_command(cmd, params)
        time.sleep_ms(5)
        self._read_ack(timeout=timeout)
        resp = self._read_response(timeout=timeout)
        if len(resp) < 2:
            raise RuntimeError(f"Response too short: {len(resp)} bytes")
        if resp[0] != TFI_PN5322HOST:
            raise RuntimeError(f"Bad TFI: 0x{resp[0]:02X}")
        if resp[1] != (cmd + 1):
            raise RuntimeError(f"Bad response code: 0x{resp[1]:02X}")
        return resp[2:]

    def get_firmware_version(self):
        resp = self._send_command(CMD_GETFIRMWAREVERSION)
        return {'ic': resp[0], 'ver': resp[1], 'rev': resp[2], 'support': resp[3]}

    def sam_config(self):
        self._send_command(CMD_SAMCONFIGURATION, b'\x01\x00\x00')

    def read_passive_target(self, timeout=1000):
        try:
            resp = self._send_command(CMD_INLISTPASSIVETARGET, bytes([0x01, 0x00]), timeout=timeout)
        except RuntimeError:
            return None
        if len(resp) < 6 or resp[0] == 0:
            return None
        atqa = (resp[2] << 8) | resp[3]
        sak = resp[4]
        uid_len = resp[5]
        uid = resp[6:6 + uid_len]
        return {
            'uid': uid,
            'uid_hex': ':'.join(f'{b:02X}' for b in uid),
            'atqa': atqa,
            'sak': sak,
            'tag_type': TAG_TYPES.get((atqa, sak), f"Unknown (ATQA=0x{atqa:04X} SAK=0x{sak:02X})"),
            'is_ntag': sak in (0x00, 0x20),
        }

    def ntag_read_page(self, page):
        params = bytes([0x01, MIFARE_CMD_READ, page])
        resp = self._send_command(CMD_INDATAEXCHANGE, params, timeout=1000)
        if (resp[0] & 0x3F) != 0:
            raise RuntimeError(f"Read status: 0x{resp[0]:02X}")
        return resp[1:5]

    def ntag_write_page(self, page, data):
        if len(data) != 4:
            raise ValueError("Must write exactly 4 bytes")
        params = bytes([0x01, NTAG_CMD_WRITE, page]) + bytes(data)
        resp = self._send_command(CMD_INDATAEXCHANGE, params, timeout=1000)
        if (resp[0] & 0x3F) != 0:
            raise RuntimeError(f"Write status: 0x{resp[0]:02X}")
        return True


# ─────────────────────────────────────────────
# BUILD + WRITE
# ─────────────────────────────────────────────
def build_pages(color_name, number):
    """Return {page_num: 4 bytes} for pages 4 and 5."""
    color_name = color_name.strip().lower()
    if color_name not in COLOR_CODES:
        raise ValueError(f"Unknown color '{color_name}'. Known: {list(COLOR_CODES.keys())}")
    if not (0 <= number <= 0xFFFF):
        raise ValueError("Number must be between 0 and 65535")

    color_byte = COLOR_CODES[color_name]
    hi = (number >> 8) & 0xFF
    lo = number & 0xFF

    return {
        4: MAGIC_HEADER,
        5: bytes([0x00, color_byte, hi, lo]),
    }


def write_tag(nfc, color_name, number):
    pages = build_pages(color_name, number)
    print(f"\n  Writing: color={color_name} (0x{COLOR_CODES[color_name.lower()]:02X}), number={number}")

    for page_num in sorted(pages.keys()):
        data = pages[page_num]
        hex_str = ' '.join(f'{b:02X}' for b in data)
        try:
            nfc.ntag_write_page(page_num, data)
            print(f"  Page {page_num}: {hex_str}  -> OK")
        except RuntimeError as e:
            print(f"  Page {page_num}: {hex_str}  -> FAILED ({e})")
            return False
        time.sleep_ms(30)

    return True


def verify_tag(nfc, color_name, number):
    expected = build_pages(color_name, number)
    ok = True
    for page_num, expected_data in expected.items():
        try:
            actual = nfc.ntag_read_page(page_num)
            match = "OK" if actual == expected_data else "MISMATCH"
            if actual != expected_data:
                ok = False
            print(f"  Page {page_num}: expected {' '.join(f'{b:02X}' for b in expected_data)}"
                  f" | got {' '.join(f'{b:02X}' for b in actual)}  [{match}]")
        except Exception as e:
            print(f"  Page {page_num}: verify error ({e})")
            ok = False
    return ok


# ─────────────────────────────────────────────
# MAIN — interactive CLI
# ─────────────────────────────────────────────
def main():
    print("\n" + "*" * 55)
    print("  PlaygroundV5 — Tag Writer (Color + Number)")
    print("*" * 55)

    i2c = machine.SoftI2C(sda=machine.Pin(I2C_SDA), scl=machine.Pin(I2C_SCL), freq=100_000)
    devices = i2c.scan()
    print(f"\n  I2C devices: {['0x{:02X}'.format(d) for d in devices]}")

    if PN532_ADDR not in devices:
        print(f"  [FAIL] PN532 not found at 0x{PN532_ADDR:02X}")
        return

    nfc = PN532(i2c, PN532_ADDR)

    try:
        fw = nfc.get_firmware_version()
        print(f"  Firmware: {fw['ver']}.{fw['rev']}")
        nfc.sam_config()
        print("  SAM configured\n")
    except Exception as e:
        print(f"  [FAIL] Init error: {e}")
        return

    print(f"  Known colors: {list(COLOR_CODES.keys())}\n")

    while True:
        print("  ─────────────────────────────────────")
        try:
            color_name = input("  Color (or 'quit'): ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if color_name.lower() in ('quit', 'exit', 'q'):
            break

        if color_name.lower() not in COLOR_CODES:
            print(f"  Unknown color. Known: {list(COLOR_CODES.keys())}\n")
            continue

        try:
            num_str = input("  Number (0-65535): ").strip()
            number = int(num_str)
        except ValueError:
            print("  Invalid number.\n")
            continue

        if not (0 <= number <= 0xFFFF):
            print("  Number must be 0-65535.\n")
            continue

        print("\n  Place a blank NTAG/Ultralight tag on the reader...")
        tag = None
        while tag is None:
            tag = nfc.read_passive_target(timeout=500)
            time.sleep_ms(200)

        if not tag['is_ntag']:
            print(f"  This tag is {tag['tag_type']} — need an NTAG/Ultralight tag. Skipping.\n")
            continue

        print(f"  Tag detected: {tag['uid_hex']} ({tag['tag_type']})")

        success = False
        try:
            success = write_tag(nfc, color_name, number)
        except Exception as e:
            print(f"  Write error: {e}")

        if success:
            print("\n  Verifying...")
            time.sleep_ms(200)
            re_tag = nfc.read_passive_target(timeout=500)
            if re_tag:
                verify_tag(nfc, color_name, number)
            print(f"\n  Done: {color_name} #{number} written.\n")
        else:
            print("\n  Write failed.\n")

    print("\n  Goodbye!")


if __name__ == "__main__":
    main()