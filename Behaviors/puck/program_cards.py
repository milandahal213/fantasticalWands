"""
program_cards.py (puck shim) — just the color remap.

bledevice.py lazily imports remap_color() to normalize the color byte from a
LEGO device's BLE advertisement. The puck applies the SAME remap to the color
read off its own NFC sticker, so a matching card compares equal on both sides.

This is a trimmed copy of the repo's single source-of-truth remap table.
"""

# Raw color byte (NFC card OR LEGO BLE advertisement) -> app-aligned color id.
_RAW_TO_APP_COLOR = {
    0x01: 8,   # magenta
    0x02: 2,   # purple
    0x04: 2,   # yellow
    0x06: 6,   # green
    0x07: 2,   # yellow (multi variant)
    0x08: 9,   # orange
    0x09: 1,   # red
}


def remap_color(raw_byte):
    """Translate a raw color byte to the app-aligned color id. Unknown bytes
    pass through unchanged (so matching still works as long as both sides use
    this same function)."""
    return _RAW_TO_APP_COLOR.get(raw_byte, raw_byte)
