# noWand

A Python desktop app for connecting to and controlling LEGO Education hardware over Bluetooth Low Energy (BLE). Scan for nearby devices, connect them, monitor telemetry, drive motors, and run pre-built multi-device behaviors — all from a single window.

---

## What it does

- **Scans** for nearby LEGO Education BLE devices: Single Motor, Double Motor, Color Sensor, and Controller
- **Shows** discovered devices in a compact scan strip at the top of the window
- **Connect** — select devices and click CONNECT; each device moves from the scan strip into its own card
- **Device cards** show the device icon, card emoji, serial number, color name, live telemetry, motor controls (Run / Stop / speed slider), and a Beep button
- **Behaviors** — a panel at the bottom lets you activate one of five pre-built multi-device behaviors; a behavior auto-disables if a required device disconnects

### Built-in behaviors

| # | Name | Description |
|---|------|-------------|
| 1 | Tank Drive | Two motors steered independently by a controller |
| 2 | Arcade Drive | Single-stick arcade-style driving with a double motor |
| 3 | Light Theremin | Color sensor reading maps to motor speed like a theremin |
| 4 | Color Speed Map | Detected color sets a preset motor speed |
| 5 | Alarm System | Color sensor triggers a beep alarm when a condition is met |

---

## Requirements

- Python 3.12 or newer (tested on 3.14)
- tkinter (usually bundled with Python — see Troubleshooting if missing)
- libcairo system library (for SVG icons — app runs without it, icons fall back to text labels)
- LEGO Education BLE hardware: Single Motor, Double Motor, Color Sensor, or Controller

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/fantasticalWands/noWand.git
cd noWand
```

### 2. Run the installer

```bash
bash install.sh
```

The installer:
- Finds a compatible Python 3.12+ interpreter
- Checks that tkinter is available
- Checks for libcairo and warns if it is missing
- Creates a `.venv` virtual environment
- Installs all Python dependencies from `requirements.txt`
- Runs a real cairosvg render test to confirm icons will work
- Offers to launch the app immediately

### 3. Launch the app

```bash
.venv/bin/python app.py
```

---

## Python dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| legoeducation | >= 1.0.5 | LEGO BLE SDK |
| bleak | >= 3.0.1 | BLE (pulled in by legoeducation) |
| cairosvg | >= 2.9.0 | SVG icon rendering |
| Pillow | >= 12.2.0 | Image processing |

---

## Troubleshooting

### libcairo missing — icons don't appear

`pip install cairosvg` succeeds silently even when libcairo is not installed, so the app starts but shows no icons. The app still works; icons fall back to text labels.

Install libcairo for your OS:

```bash
# macOS (requires Homebrew)
brew install cairo

# Ubuntu / Debian
sudo apt install libcairo2

# Fedora / RHEL
sudo dnf install cairo

# Arch
sudo pacman -S cairo
```

Then re-run the installer to verify the fix.

---

### tkinter not found

Homebrew Python on macOS strips tkinter. The official Python installer from python.org includes it.

- **macOS**: download and install Python from [python.org/downloads](https://www.python.org/downloads/)
- **Ubuntu / Debian**: `sudo apt install python3-tk`
- **Fedora / RHEL**: `sudo dnf install python3-tkinter`

---

### cairosvg imports but icons still don't appear (mixed Intel + Apple Silicon Mac)

libcairo is installed but in a path that does not match your Python's architecture. This happens when Intel and Apple Silicon Homebrew coexist on the same Mac.

Check your Python architecture:

```bash
python3 -c "import platform; print(platform.machine())"
```

The output should match your Homebrew prefix:
- `x86_64` → Homebrew at `/usr/local`
- `arm64` → Homebrew at `/opt/homebrew`

If they don't match, install Python from python.org for the correct architecture, or reinstall Homebrew for the matching architecture.

---

### BLE / Bluetooth permission denied on macOS

The first run triggers a system dialog asking for Bluetooth access. Click OK or the scan will find nothing.

If you accidentally denied it: **System Settings → Privacy & Security → Bluetooth** → enable Terminal (or whichever app you run noWand from).

---

### Color sensor shows `…` and never updates

The sensor sometimes needs a physical reset after a crash. Hold the button on the hub until it restarts. The app shows `…` while waiting for the first reading — this is normal for 1–2 seconds after connecting.

---

### "Could not establish BLE connection" on connect

The device was too far away, had low battery, or another app is holding the connection.

- Move the device closer
- Make sure the LEGO Education app and any other noWand instance are closed
- Click CONNECT again — the failed device stays selected in the scan strip for easy retry

---

## Adding a new behavior

Create a file `behaviors/behaviorN.py` (replace N with the next number):

```python
from lelib import controller, doubleMotor   # import whichever device classes you need

NAME        = "My Behavior"
DESCRIPTION = "One line description shown in the UI"
REQUIRED    = [controller, doubleMotor]     # device classes that must be connected

def start(devices: dict) -> None:
    # Called when the user activates this behavior.
    # devices is {label: device_instance} for all currently connected devices.
    # Use isinstance() to find the device type you need:
    #   motor = next((d for d in devices.values() if isinstance(d, doubleMotor)), None)
    ...

def stop() -> None:
    # Called when the user deactivates this behavior or a required device disconnects.
    ...
```

The app discovers behavior files automatically on next launch — no changes to `app.py` needed.

---

## File structure

```
noWand/
  app.py                  # main application
  device_manager.py       # BLE scan + connect logic
  lelib.py                # device wrappers (singleMotor, doubleMotor, colorSensor, controller)
  requirements.txt        # pip dependencies
  install.sh              # one-shot installer script
  icons/
    single_motor.svg
    double_motor.svg
    color_sensor.svg
    controller.svg
    emoji/                # one SVG per LEGO card color (red.svg, blue.svg, …)
  behaviors/
    __init__.py           # auto-discovers behavior files
    behavior1.py          # Tank Drive
    behavior2.py          # Arcade Drive
    behavior3.py          # Light Theremin
    behavior4.py          # Color Speed Map
    behavior5.py          # Alarm System
```
