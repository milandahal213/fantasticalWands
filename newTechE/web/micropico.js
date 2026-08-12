// micropico.js - drive a MicroPython Pico from the browser over Web Serial.
//
// One reader loop feeds every incoming byte into a text buffer; console output
// is echoed to a DOM element unless we're "quiet" (during raw-REPL operations).
//
//   const mp = new MicroPico(document.getElementById("repl"));
//   await mp.connect();                        // prompts for the USB port
//   await mp.flashFromManifest("manifest.json", (done,total,name)=>{...});
//   await mp.runProject("import project1; project1.run(oled=False)");
//   await mp.interrupt();                       // Stop (Ctrl-C)
//
// Web Serial is desktop Chrome/Edge only, and requires HTTPS (GitHub Pages ok).

const CTRL_A = "\x01"; // enter raw REPL
const CTRL_B = "\x02"; // exit raw REPL
const CTRL_C = "\x03"; // interrupt
const CTRL_D = "\x04"; // execute (raw) / soft reset (friendly)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class MicroPico {
  constructor(outputEl) {
    this.out = outputEl;      // DOM element for the on-page REPL
    this.port = null;
    this.reader = null;
    this.writer = null;
    this.rx = "";             // rolling text buffer for waitFor()
    this.quiet = false;       // suppress console echo during raw ops
    this._readLoop = null;
    this.onConnectChange = null;
  }

  get connected() {
    return this.port !== null;
  }

  // ---- console helpers ----
  _echo(text) {
    if (!this.out) return;
    const atBottom =
      this.out.scrollHeight - this.out.scrollTop - this.out.clientHeight < 40;
    this.out.textContent += text;
    if (atBottom) this.out.scrollTop = this.out.scrollHeight;
  }
  log(text) {
    this._echo(text.endsWith("\n") ? text : text + "\n");
  }
  clear() {
    if (this.out) this.out.textContent = "";
  }

  // ---- connection ----
  async connect(baud = 115200) {
    if (!("serial" in navigator)) {
      throw new Error("Web Serial not supported. Use desktop Chrome or Edge.");
    }
    this.port = await navigator.serial.requestPort();
    await this.port.open({ baudRate: baud });
    this.writer = this.port.writable.getWriter();
    this._startReader();
    if (this.onConnectChange) this.onConnectChange(true);
    // Break out of any running program to a clean prompt.
    await this.interrupt();
    this.log("[connected]");
  }

  async _startReader() {
    const decoder = new TextDecoder();
    this.reader = this.port.readable.getReader();
    try {
      while (true) {
        const { value, done } = await this.reader.read();
        if (done) break;
        const text = decoder.decode(value, { stream: true });
        this.rx += text;
        if (this.rx.length > 20000) this.rx = this.rx.slice(-10000);
        if (!this.quiet) this._echo(text);
      }
    } catch (e) {
      this.log("[read error] " + e.message);
    }
  }

  async disconnect() {
    try {
      if (this.reader) {
        await this.reader.cancel().catch(() => {});
        this.reader.releaseLock();
      }
      if (this.writer) this.writer.releaseLock();
      if (this.port) await this.port.close();
    } finally {
      this.port = this.reader = this.writer = null;
      if (this.onConnectChange) this.onConnectChange(false);
      this.log("[disconnected]");
    }
  }

  // ---- raw writes ----
  async _write(str) {
    if (!this.writer) throw new Error("not connected");
    await this.writer.write(new TextEncoder().encode(str));
  }

  async _waitFor(sentinelTest, timeout = 4000) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      if (sentinelTest(this.rx)) return true;
      await sleep(15);
    }
    return false;
  }

  // ---- interrupt / friendly-REPL run ----
  async interrupt() {
    await this._write("\r" + CTRL_C + CTRL_C);
    await sleep(120);
  }

  // Soft-reboot (Ctrl-D): reloads files from flash and clears imported modules,
  // then break back to a clean prompt. Call after flashing so new code takes effect.
  async softReset() {
    await this.interrupt();
    this.rx = "";
    await this._write(CTRL_D);
    await sleep(700);
    await this.interrupt();
  }

  // Run a statement in the FRIENDLY repl; its output streams to the console.
  async runProject(pyStatement) {
    await this.interrupt();
    this.rx = "";
    await this._write(pyStatement + "\r\n");
  }

  // ---- raw REPL one-shot (used for flashing) ----
  async rawExec(code, timeout = 8000) {
    this.quiet = true;
    try {
      await this._write("\r" + CTRL_C + CTRL_C);
      await sleep(60);
      this.rx = "";
      await this._write(CTRL_A);
      if (!(await this._waitFor((b) => b.includes("raw REPL") && b.trimEnd().endsWith(">"), 3000)))
        throw new Error("could not enter raw REPL");
      this.rx = "";
      await this._write(code + CTRL_D);
      // Response: "OK" <stdout> \x04 <stderr> \x04 >
      if (!(await this._waitFor((b) => (b.match(/\x04/g) || []).length >= 2, timeout)))
        throw new Error("exec timed out");
      const buf = this.rx;
      await this._write(CTRL_B); // back to friendly REPL
      await sleep(20);
      const okIdx = buf.indexOf("OK");
      const rest = okIdx >= 0 ? buf.slice(okIdx + 2) : buf;
      const parts = rest.split(CTRL_D);
      const stdout = (parts[0] || "").trim();
      const stderr = (parts[1] || "").trim();
      return { ok: stderr.length === 0, stdout, stderr };
    } finally {
      this.quiet = false;
    }
  }

  // ---- file transfer / flashing ----
  _b64(bytes) {
    let s = "";
    for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s);
  }

  async writeFile(path, bytes) {
    let r = await this.rawExec(`import ubinascii\n_f=open(${JSON.stringify(path)},'wb')`);
    if (!r.ok) throw new Error(`open ${path}: ${r.stderr}`);
    const CH = 512;
    for (let i = 0; i < bytes.length; i += CH) {
      const b64 = this._b64(bytes.slice(i, i + CH));
      r = await this.rawExec(`_f.write(ubinascii.a2b_base64(${JSON.stringify(b64)}))`);
      if (!r.ok) throw new Error(`write ${path}: ${r.stderr}`);
    }
    r = await this.rawExec(`_f.close()`);
    if (!r.ok) throw new Error(`close ${path}: ${r.stderr}`);
  }

  // `base` is prepended when FETCHING each file (e.g. "../" because firmware
  // lives at the repo root while the site is in /web). The file is WRITTEN to
  // the Pico under its basename only.
  async flashFromManifest(manifestUrl, base, onProgress) {
    base = base || "";
    const files = await (await fetch(manifestUrl, { cache: "no-store" })).json();
    for (let i = 0; i < files.length; i++) {
      const name = files[i];
      if (onProgress) onProgress(i, files.length, name);
      const resp = await fetch(base + name, { cache: "no-store" });
      if (!resp.ok) throw new Error(`fetch ${base + name}: HTTP ${resp.status}`);
      const bytes = new Uint8Array(await resp.arrayBuffer());
      await this.writeFile(name, bytes);
      this.log(`  flashed ${name} (${bytes.length} bytes)`);
    }
    if (onProgress) onProgress(files.length, files.length, "");
  }
}

window.MicroPico = MicroPico;
