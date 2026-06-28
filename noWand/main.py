"""
noWand — main entry point.

Run this script to connect to any LEGO Education hardware by card serial and colour.
Prints live telemetry from all connected devices. Type 'add' to connect more,
'quit' to disconnect everything and exit.
"""

import time
import threading
from device_manager import DeviceManager


def telemetry_loop(manager: DeviceManager, interval: float = 0.1):
    """Background thread: prints telemetry from all connected devices."""
    while _running:
        if manager.devices:
            manager.print_telemetry()
        time.sleep(interval)


def prompt_connect(manager: DeviceManager):
    """Ask the user for a card serial (and optionally colour) and connect.
    Blank or 0 serial = scan for all nearby devices."""
    serial_str = input("  Card serial number (blank or 0 = all): ").strip()
    try:
        card_serial = int(serial_str) if serial_str else 0
    except ValueError:
        print("  Invalid serial — must be a number.")
        return

    color_str = input("  Card colour (blank to skip): ").strip() or None

    try:
        manager.scan_and_connect(card_serial=card_serial, card_color=color_str)
    except Exception as exc:
        print(f"  Error: {exc}")


_running = True


def main():
    global _running
    manager = DeviceManager()

    print("=== noWand ===")
    print("Commands:  add | quit\n")

    # Connect the first device before starting telemetry
    prompt_connect(manager)

    # Start background telemetry printer
    t = threading.Thread(target=telemetry_loop, args=(manager,), daemon=True)
    t.start()

    while True:
        try:
            cmd = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd == 'add':
            prompt_connect(manager)
        elif cmd == 'quit':
            break
        elif cmd == '':
            pass
        else:
            print("  Unknown command. Use 'add' or 'quit'.")

    _running = False
    print("\nDisconnecting...")
    manager.disconnect_all()
    print("Done.")


if __name__ == '__main__':
    main()
