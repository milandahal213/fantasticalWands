# noWand

A Python desktop app for connecting to and controlling LEGO Education hardware over Bluetooth Low Energy (BLE). Scan for nearby devices, connect them, monitor telemetry, drive motors, and run pre-built multi-device behaviors — all from a single window.

Works on **macOS, Windows, and Linux**.

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

- **Python 3.12 or newer** (tested on 3.14). On Windows and macOS, install it from
  [python.org](https://www.python.org/downloads/) — that build includes tkinter.
- **tkinter** — bundled with the python.org installer (Windows/macOS) and most Linux
  distros (see Troubleshooting if it's missing).
- **A Bluetooth adapter:** Windows 10/11, macOS, or Linux with BlueZ.
- **libcairo** (optional) — used for the SVG device icons. The app runs fine without
  it; icons just fall back to text labels. See Troubleshooting for how to add it.
- **LEGO Education BLE hardware:** Single Motor, Double Motor, Color Sensor, or Controller.

---

## Installation

### 1. Get the code

```bash
git clone https://github.com/milandahal213/fantasticalWands.git
cd fantasticalWands/noWand
```

### 2. Run the installer

The installer finds a compatible Python, checks tkinter, creates a `.venv`, installs
the dependencies, verifies SVG rendering, and offers to launch the app.

**Windows** (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

**macOS / Linux** (Terminal):

```bash
bash install.sh
```

### 3. Launch the app (any time after install)

**Windows:**

```powershell
.venv\Scripts\python app.py
```

**macOS / Linux:**

```bash
.venv/bin/python app.py
```

---

### Manual install (works on any OS)

If you'd rather not use the installer script:

**Windows (PowerShell):**

```powershell
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

**macOS / Linux:**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
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

### Icons don't appear (libcairo / Cairo missing)

`pip install cairosvg` succeeds even when the underlying Cairo graphics library
isn't present, so the app starts but shows no icons. The app still works — icons
fall back to text labels. To get the icons, install Cairo:

**Windows** — Cairo ships with the GTK3 runtime. Install the latest
`gtk3-runtime-…-win64.exe` from the
[GTK for Windows Runtime Environment Installer](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases),
then reopen PowerShell and re-run the installer.

**macOS** (requires [Homebrew](https://brew.sh)):

```bash
brew install cairo
```

**Linux:**

```bash
sudo apt install libcairo2        # Ubuntu / Debian
sudo dnf install cairo            # Fedora / RHEL
sudo pacman -S cairo              # Arch
```

Then re-run the installer to verify the fix.

---

### tkinter not found

- **Windows / macOS:** reinstall Python from
  [python.org](https://www.python.org/downloads/) and keep the **“tcl/tk and IDLE”**
  option checked during setup. (On macOS, avoid the Homebrew Python — it omits tkinter.)
- **Ubuntu / Debian:** `sudo apt install python3-tk`
- **Fedora / RHEL:** `sudo dnf install python3-tkinter`

---

### Windows: "running scripts is disabled on this system"

Windows blocks PowerShell scripts by default. Run the installer with the bypass flag
(it only affects that one command):

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

---

### Bluetooth finds no devices

- **Windows:** make sure Bluetooth is turned on (Settings → Bluetooth & devices) and
  you're on Windows 10 or 11. Close the LEGO Education app or any other program that
  might be holding the connection.
- **macOS:** the first run triggers a system permission dialog — click **OK**. If you
  denied it, enable your terminal under **System Settings → Privacy & Security →
  Bluetooth**.
- **Linux:** ensure BlueZ is installed and the Bluetooth service is running.

---

### cairosvg imports but icons still don't appear (mixed Intel + Apple Silicon Mac)

macOS only. libcairo is installed but in a path that doesn't match your Python's
architecture (common when Intel and Apple Silicon Homebrew coexist).

```bash
python3 -c "import platform; print(platform.machine())"
```

- `x86_64` → Homebrew at `/usr/local`
- `arm64` → Homebrew at `/opt/homebrew`

If they don't match, install Python from python.org for the correct architecture, or
reinstall Homebrew to match.

---

### Color sensor shows `…` and never updates

The sensor sometimes needs a physical reset after a crash. Hold the button on the hub
until it restarts. The app shows `…` while waiting for the first reading — this is
normal for 1–2 seconds after connecting.

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
  install.sh              # one-shot installer (macOS / Linux)
  install.ps1             # one-shot installer (Windows / PowerShell)
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
