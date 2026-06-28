"""
BLE diagnostic — run this to see what's inside the BLEDevice objects
returned by legoeducation's search().

Run: python ble_diagnostic.py
"""

from lelib import singleMotor, doubleMotor, colorSensor, controller
import threading

SCAN_TIMEOUT = 3
DEVICE_TYPES = [singleMotor, doubleMotor, colorSensor, controller]

print(f"Scanning for {SCAN_TIMEOUT}s for all device types...\n")

all_results = []
lock = threading.Lock()

def try_type(cls):
    dev = cls()
    results = dev.search(timeout=SCAN_TIMEOUT)
    if results:
        with lock:
            for r in results:
                all_results.append((cls.__name__, r))

threads = [threading.Thread(target=try_type, args=(cls,)) for cls in DEVICE_TYPES]
for t in threads: t.start()
for t in threads: t.join()

print(f"Found {len(all_results)} device(s)\n")
print("=" * 60)

for cls_name, r in all_results:
    print(f"\nDevice type : {cls_name}")
    print(f"  name      : {r.name}")
    print(f"  address   : {r.address}")

    print(f"  metadata keys: {list(r.metadata.keys()) if hasattr(r, 'metadata') else 'NO METADATA'}")

    if hasattr(r, 'metadata'):
        mfr = r.metadata.get('manufacturer_data', {})
        print(f"  manufacturer_data keys: {list(mfr.keys())}")
        for k, v in mfr.items():
            print(f"    [{hex(k)}] ({len(v)} bytes): {list(v)}")

    if hasattr(r, 'details'):
        print(f"  details type: {type(r.details)}")

print("\n" + "=" * 60)
print("Done.")
