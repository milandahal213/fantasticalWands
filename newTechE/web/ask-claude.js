// ask-claude.js - "Ask Claude" buttons. Opens a new Claude.ai chat with this
// project's KNOWLEDGE.md pre-filled as the first message (via claude.ai's
// ?q= prefill), so the visitor's Claude already knows the codebase instead
// of them having to explain it first.

const KB_URL = "KNOWLEDGE.md";
const CLAUDE_NEW = "https://claude.ai/new?q=";

async function askClaude(question) {
  // Open the tab synchronously (inside the click handler) so popup blockers
  // don't kill it once we `await` the KNOWLEDGE.md fetch below.
  const win = window.open("about:blank", "_blank");
  let kb = "";
  try {
    const res = await fetch(KB_URL);
    if (res.ok) kb = await res.text();
  } catch (e) {
    kb = "";
  }
  const prompt = kb ? kb.trim() + "\n\n---\n\n" + question : question;
  const url = CLAUDE_NEW + encodeURIComponent(prompt);
  if (win) {
    win.location.href = url;
  } else {
    location.href = url; // popup blocked - fall back to same-tab
  }
}

function initAskClaude() {
  document.querySelectorAll("[data-ask-claude]").forEach((btn) => {
    btn.addEventListener("click", () => {
      askClaude(btn.dataset.askClaude || "I have a question about this project.");
    });
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initAskClaude);
} else {
  initAskClaude();
}
