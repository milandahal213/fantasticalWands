# fantasticalWands

Hardware, firmware, and software for controlling **LEGO Education** motors,
sensors, and controllers over Bluetooth Low Energy — across several physical
form factors, from a tap-a-card magic wand to a plain desktop app.

Everything here is MicroPython (on ESP32-C6 / Pico W) or Python/PyScript,
built around two ideas LEGO's own hardware supports natively:

- **Connection (GATT)** — a device acts as a BLE central, connects to LEGO
  bricks, and sends commands / reads telemetry.
- **Connectionless broadcast** — a device advertises a `0xFD02` beacon; any
  LEGO brick "grouped" to the same Connection Card (colour + serial) acts on
  it, with no pairing and no connection limit. See
  **[`magicWandandLE/extras/MOTOR_BROADCAST_RECIPE.md`](magicWandandLE/extras/MOTOR_BROADCAST_RECIPE.md)**
  for the protocol — it's the one page to read before touching any broadcast
  code in this repo.

## Layout

### Standalone hardware projects (top-level)

| Folder | What it is |
|---|---|
| **[magicWandandLE/](magicWandandLE)** | ESP32-C6 handheld wand. Tap a LEGO connection card and its **colour picks the mode**: purple = accelerometer-tilt broadcast control, orange = random motor "dance", green/blue = GATT tap-programming (assemble reactive rules by tapping event/action cards). Has its own detailed README. |
| **[newTechE/](newTechE)** | Raspberry Pi Pico W box using the same connectionless broadcast protocol as the wand: tap a card to pick the motor group, drive from analog sensors or an I²C joystick. Includes a PyScript Web-Serial flasher site. |

### [Behaviors/](Behaviors) — BLE centrals with pre-built multi-device behaviors

Four different "runner" form factors that share the same idea: connect to a
group of LEGO devices and run a hardcoded or selectable behavior (Tank Drive,
etc.) across all of them at once.

| Folder | What it is |
|---|---|
| **[Behaviors/puck/](Behaviors/puck)** | Seeed XIAO ESP32-C6 + 3 NeoPixels + a **passive** NFC card. No reader on the puck itself — LEGO devices read *its* card and start advertising that identity; the puck scans for and connects to devices announcing its own colour+serial, then runs one hardcoded behavior. |
| **[Behaviors/box/](Behaviors/box)** | Everything the puck does, plus a 5×5 NeoPixel matrix, buzzer, button, and accelerometer. Shares `behaviors/` with puck. |
| **[Behaviors/noWand/](Behaviors/noWand)** | Cross-platform (macOS/Windows/Linux) Tkinter desktop app: scan, connect, drive motors, watch telemetry, and run 5 pre-built multi-device behaviors from one window. |
| **[Behaviors/pyscript_powered/](Behaviors/pyscript_powered)** | "noWand — PyScript edition": the same idea, 100% in-browser via PyScript + Web Bluetooth. No install — hostable as static files / GitHub Pages. |

### [Extras/](Extras) — reference code and learning material

| Folder | What it is |
|---|---|
| **[Extras/Examples/](Extras/Examples)** | Numbered, incremental demo scripts (single/double motor, controller, colour sensor, IMU, and wand-tilt-driven motor) built on `magicWandandLE`'s libraries — read these in order to learn the BLE API from scratch. |
| **[Extras/spike_prime/](Extras/spike_prime)** | MicroPython for a LEGO SPIKE Prime hub acting as a BLE central to the new tech elements. Documents a key limitation: stock SPIKE firmware allows only **one** simultaneous tech-element connection. |
| **[Extras/Q-learning/](Extras/Q-learning)** | Standalone static HTML/CSS/JS site teaching Q-learning with two interactive simulators (grid maze, line-follower). No LEGO hardware dependency. |

### [Utilities/](Utilities) — standalone tools

| Folder | What it is |
|---|---|
| **[Utilities/LEGO card reader:write/](<Utilities/LEGO card reader:write>)** | Standalone PN532 NFC `reader.py` / `writer.py` scripts for reading and writing the colour+serial connection cards used throughout this repo. |

`magicWandandLE/tools/` also has card-related utilities (`write_card.py`,
`KNOWLEDGE_BASE.md`) specific to that project's tap-programming cards — see
its own README.

## Repo notes

- No LICENSE file yet.
- `.nojekyll` is present at the root — several subfolders (`Extras/Q-learning/`,
  `Behaviors/pyscript_powered/`, `newTechE/web/`) are meant to be served as
  static sites (e.g. GitHub Pages), and this stops Jekyll from mangling them.
- Each subfolder with non-trivial setup has its own README — start there for
  anything hardware-specific (pin maps, flashing instructions, dependencies).
