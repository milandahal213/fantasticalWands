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
  **[`MOTOR_BROADCAST_RECIPE.md`](MOTOR_BROADCAST_RECIPE.md)** for the
  protocol — it's the one page to read before touching any broadcast code
  in this repo.

## Subsystems

### Tangible / card-based control

| Folder | What it is |
|---|---|
| **[magicWandandLE/](magicWandandLE)** | ESP32-C6 handheld wand. Tap a LEGO connection card and its **colour picks the mode**: purple = accelerometer-tilt broadcast control, orange = random motor "dance", green/blue = GATT tap-programming (assemble reactive rules by tapping event/action cards). Has its own detailed README. |
| **[puck/](puck)** | Seeed XIAO ESP32-C6 + 3 NeoPixels + a **passive** NFC card. No reader on the puck itself — LEGO devices read *its* card and start advertising that identity; the puck scans for and connects to devices announcing its own colour+serial, then runs one hardcoded behavior. |
| **[box/](box)** | Everything the puck does, plus a 5×5 NeoPixel matrix, buzzer, button, and accelerometer. Shares `behaviors/` with puck. |
| **[LEGO card reader/](LEGO%20card%20reader)** | Standalone PN532 NFC `reader.py` / `writer.py` scripts for reading and writing the colour+serial connection cards used throughout this repo. |
| **[tools/](tools)** | `KNOWLEDGE_BASE.md` — the design doc for the tangible NFC programming system (pairing cards, programming cards, rules/deck) — and `write_card.py` for encoding programming-card serials onto MIFARE cards. |

### Software-only control (no wand/puck hardware)

| Folder | What it is |
|---|---|
| **[noWand/](noWand)** | Cross-platform (macOS/Windows/Linux) Tkinter desktop app: scan, connect, drive motors, watch telemetry, and run 5 pre-built multi-device behaviors from one window. |
| **[pyscript_powered/](pyscript_powered)** | "noWand — PyScript edition": the same idea, 100% in-browser via PyScript + Web Bluetooth. No install — hostable as static files / GitHub Pages. |

### Other hardware targets

| Folder | What it is |
|---|---|
| **[newTechE/](newTechE)** | Raspberry Pi Pico W box using the same connectionless broadcast protocol as the wand: tap a card to pick the motor group, drive from analog sensors or an I²C joystick. Includes a PyScript Web-Serial flasher site. |
| **[spike_prime/](spike_prime)** | MicroPython for a LEGO SPIKE Prime hub acting as a BLE central to the new tech elements. Documents a key limitation: stock SPIKE firmware allows only **one** simultaneous tech-element connection. |
| **[lego_education/](lego_education)** | Early ESP32-C6 BLE experiments (colour-sensor-drives-motor, multi-hub BLE) — the answer to SPIKE's one-connection limit when you need more. Less polished than the other folders; treat as reference/scratch. |

### Learning materials

| Folder | What it is |
|---|---|
| **[Q-learning/](Q-learning)** | Standalone static HTML/CSS/JS site teaching Q-learning with two interactive simulators (grid maze, line-follower). No LEGO hardware dependency. |
| **[Examples/](Examples)** | Numbered, incremental demo scripts (single/double motor, controller, colour sensor, IMU, and wand-tilt-driven motor) built on `magicWandandLE`'s libraries — read these in order to learn the BLE API from scratch. |

## Repo notes

- No LICENSE file yet.
- `.nojekyll` is present at the root — several subfolders (`Q-learning/`,
  `pyscript_powered/`, `newTechE/web/`) are meant to be served as static
  sites (e.g. GitHub Pages), and this stops Jekyll from mangling them.
- Each subfolder with non-trivial setup has its own README — start there for
  anything hardware-specific (pin maps, flashing instructions, dependencies).
