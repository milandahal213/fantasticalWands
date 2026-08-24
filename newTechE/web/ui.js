// ui.js - client-side page routing + console drawer. No page reloads, so the
// Web Serial connection (owned by micropico.js / app.py) survives navigation.

const PAGES = [
  { id: "build", title: "Build the box" },
  { id: "flash", title: "Load the code" },
  { id: "i2c", title: "I²C sensor" },
  { id: "analog", title: "Analog sensor" },
];

function currentIndex() {
  const id = (location.hash || "#build").slice(1);
  const i = PAGES.findIndex((p) => p.id === id);
  return i < 0 ? 0 : i;
}

function route() {
  const idx = currentIndex();
  const active = PAGES[idx];

  // Show only the active page.
  PAGES.forEach((p) => {
    const el = document.getElementById("page-" + p.id);
    if (el) el.classList.toggle("active", p.id === active.id);
  });

  // Highlight the active nav tab.
  document.querySelectorAll("nav a").forEach((a) => {
    a.classList.toggle("active", a.getAttribute("href") === "#" + active.id);
  });

  // Update Back / Next.
  const back = document.getElementById("nav-back");
  const next = document.getElementById("nav-next");
  if (idx > 0) {
    back.style.visibility = "visible";
    back.textContent = "← " + PAGES[idx - 1].title;
    back.onclick = () => (location.hash = PAGES[idx - 1].id);
  } else {
    back.style.visibility = "hidden";
  }
  if (idx < PAGES.length - 1) {
    next.style.visibility = "visible";
    next.textContent = PAGES[idx + 1].title + " →";
    next.onclick = () => (location.hash = PAGES[idx + 1].id);
  } else {
    next.style.visibility = "hidden";
  }

  document.getElementById("page-progress").textContent =
    "Step " + (idx + 1) + " of " + PAGES.length;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function initUI() {
  window.addEventListener("hashchange", route);
  const toggle = document.getElementById("drawer-toggle");
  if (toggle) {
    toggle.onclick = () => {
      document.body.classList.toggle("drawer-collapsed");
      toggle.textContent = document.body.classList.contains("drawer-collapsed") ? "▲" : "▼";
    };
  }
  route();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initUI);
} else {
  initUI();
}
