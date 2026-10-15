"""The two front ends: the customer desk at / and the employee desk at /staff. Both tell people, before they type,
that they are talking to an AI and that a person can take over; a test checks that the text is on both pages."""

from html import escape

DISCLOSURE = {
    "customer": "You are chatting with an AI assistant. It can look up your orders, start returns and issue small "
    "refunds; larger refunds are checked by a person. Ask for a person at any time.",
    "employee": "You are chatting with an AI assistant. It can unlock your own account, grant standard access and "
    "explain HR policy. Sensitive access needs an approver, and decisions about you are made by people.",
}
TITLES = {"customer": "Customer help", "employee": "Employee help desk"}

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ --bg: #ffffff; --fg: #16181d; --muted: #5b616e; --line: #d9dce3; --you: #eef1f6; --accent: #1f4fd1; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #121418; --fg: #eceef2; --muted: #a3a9b5; --line: #2c3038; --you: #1d2129; --accent: #8fb0ff; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.6 system-ui, -apple-system, "Segoe UI",
         Roboto, sans-serif; }}
  main {{ max-width: 680px; margin: 0 auto; padding: 24px 16px 48px; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 12px; }}
  .disclosure {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; color: var(--fg); }}
  .meta {{ color: var(--muted); font-size: 0.9rem; }}
  #log p {{ margin: 12px 0; padding: 10px 12px; border-radius: 8px; white-space: pre-wrap; }}
  #log p.user {{ background: var(--you); }}
  form {{ display: flex; gap: 8px; margin-top: 16px; }}
  input, textarea, button {{ font: inherit; color: var(--fg); background: var(--bg); border: 1px solid var(--line);
         border-radius: 8px; padding: 10px 12px; }}
  textarea {{ flex: 1; min-height: 3.2em; }}
  button {{ background: var(--accent); color: var(--bg); border-color: var(--accent); cursor: pointer; }}
  label {{ display: block; margin: 16px 0 4px; }}
  #token {{ width: 100%; }}
</style>
</head>
<body>
<main>
  <h1>{title}</h1>
  <p class="disclosure" role="note" data-testid="ai-disclosure">{disclosure}</p>
  <label for="token" class="meta">Sign-in token (from your identity provider; POST /dev/token in development)</label>
  <input id="token" autocomplete="off">
  <div id="log" aria-live="polite"></div>
  <form id="send">
    <textarea id="text" aria-label="Your message" required></textarea>
    <button>Send</button>
  </form>
  <p class="meta" id="status"></p>
</main>
<script>
  let ticket = null;
  const log = document.getElementById("log"), status = document.getElementById("status");
  function show(t) {{
    log.replaceChildren(...t.messages.map(m => {{
      const p = document.createElement("p"); p.className = m.role; p.textContent = m.text; return p; }}));
    status.textContent = "Ticket " + t.id + ", " + t.status.replace("_", " ");
  }}
  document.getElementById("send").addEventListener("submit", async e => {{
    e.preventDefault();
    const text = document.getElementById("text"), token = document.getElementById("token").value.trim();
    const url = ticket ? "/v1/tickets/" + ticket + "/messages" : "/v1/tickets";
    status.textContent = "Working...";
    const r = await fetch(url, {{ method: "POST", headers: {{ "content-type": "application/json",
      authorization: "Bearer " + token }}, body: JSON.stringify({{ message: text.value }}) }});
    const t = await r.json();
    if (!r.ok) {{ status.textContent = t.detail || "Something went wrong"; return; }}
    ticket = t.id; text.value = ""; show(t);
  }});
</script>
</body>
</html>
"""


def page(tenant: str) -> str:
    return PAGE.format(title=escape(TITLES[tenant]), disclosure=escape(DISCLOSURE[tenant]))
