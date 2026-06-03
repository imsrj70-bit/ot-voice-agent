import streamlit as st
import streamlit.components.v1 as components

VAPI_PUBLIC_KEY = "6434064f-a019-4986-9e62-8b384f282bbf"
ASSISTANT_ID    = "3bba9f4c-82be-4133-99de-c7460d29de70"

st.set_page_config(
    page_title="Riley — Ordertron Voice Agent",
    page_icon="🤖",
    layout="centered",
)

# Hide Streamlit chrome for a cleaner demo look
st.markdown("""
<style>
  #MainMenu, header, footer { visibility: hidden; }
  .block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

components.html(f"""
<!DOCTYPE html>
<html>
<head>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: transparent;
    display: flex;
    justify-content: center;
    padding: 24px 0;
  }}
  .card {{
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 20px;
    padding: 40px 48px;
    text-align: center;
    width: 320px;
    box-shadow: 0 8px 40px rgba(0,0,0,0.4);
  }}
  .avatar {{
    font-size: 52px;
    margin-bottom: 12px;
  }}
  h1 {{ font-size: 22px; font-weight: 600; color: #fff; margin-bottom: 4px; }}
  .sub {{ font-size: 13px; color: #666; margin-bottom: 32px; }}

  #callBtn {{
    width: 72px; height: 72px;
    border-radius: 50%; border: none; cursor: pointer;
    font-size: 26px; display: flex; align-items: center;
    justify-content: center; margin: 0 auto 16px;
    transition: transform 0.15s, box-shadow 0.15s;
    background: #22c55e;
    box-shadow: 0 4px 20px rgba(34,197,94,0.4);
    color: #fff;
  }}
  #callBtn:hover {{ transform: scale(1.07); }}
  #callBtn:active {{ transform: scale(0.96); }}
  #callBtn.active {{
    background: #ef4444;
    box-shadow: 0 4px 20px rgba(239,68,68,0.4);
  }}
  #callBtn.connecting {{
    background: #f59e0b;
    box-shadow: 0 4px 20px rgba(245,158,11,0.4);
    animation: pulse 1.1s infinite;
  }}
  @keyframes pulse {{
    0%,100% {{ transform: scale(1); }}
    50%      {{ transform: scale(1.07); }}
  }}

  #status {{ font-size: 13px; color: #888; min-height: 18px; }}
  #error  {{ font-size: 12px; color: #f87171; margin-top: 8px; min-height: 16px; }}

  /* volume bars */
  #volBar {{
    display: flex; align-items: flex-end; justify-content: center;
    gap: 4px; height: 24px; margin: 14px auto 0;
    opacity: 0; transition: opacity 0.3s;
  }}
  #volBar.on {{ opacity: 1; }}
  .b {{ width: 5px; border-radius: 3px; background: #6e40c9; min-height: 3px; transition: height 0.08s; }}
</style>
</head>
<body>
<div class="card">
  <div class="avatar">🤖</div>
  <h1>Riley</h1>
  <p class="sub">Ordertron Voice Agent</p>

  <button id="callBtn">
    <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24"
         fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07
               A19.5 19.5 0 0 1 4.69 12 19.79 19.79 0 0 1 1.6 3.43
               2 2 0 0 1 3.6 1.21h3a2 2 0 0 1 2 1.72c.127.96.36 1.903.7
               2.81a2 2 0 0 1-.45 2.11L7.91 8.82a16 16 0 0 0 6.29 6.29l.88-.88
               a2 2 0 0 1 2.11-.45c.907.34 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/>
    </svg>
  </button>

  <p id="status">Click to start a call</p>
  <div id="volBar">
    <div class="b" id="b1"></div><div class="b" id="b2"></div>
    <div class="b" id="b3"></div><div class="b" id="b4"></div>
    <div class="b" id="b5"></div><div class="b" id="b6"></div>
    <div class="b" id="b7"></div>
  </div>
  <p id="error"></p>
</div>

<script type="module">
  import _m from "https://cdn.jsdelivr.net/npm/@vapi-ai/web@latest/+esm";
  const Vapi = _m.default ?? _m;

  const PUBLIC_KEY   = "{VAPI_PUBLIC_KEY}";
  const ASSISTANT_ID = "{ASSISTANT_ID}";

  const btn    = document.getElementById("callBtn");
  const status = document.getElementById("status");
  const errEl  = document.getElementById("error");
  const volBar = document.getElementById("volBar");
  const bars   = Array.from(document.querySelectorAll(".b"));

  const vapi = new Vapi(PUBLIC_KEY);
  let active = false;

  function setStatus(txt, type="idle") {{
    status.textContent = txt;
    errEl.textContent = "";
    btn.className = type === "active" ? "active" : type === "connecting" ? "connecting" : "";
  }}

  function showBars(on) {{
    volBar.className = on ? "on" : "";
    if (!on) bars.forEach(b => b.style.height = "3px");
  }}

  vapi.on("call-start", () => {{
    active = true;
    setStatus("Call active — click to end", "active");
    showBars(true);
  }});

  vapi.on("call-end", () => {{
    active = false;
    showBars(false);
    setStatus("Call ended");
    btn.className = "";
  }});

  vapi.on("volume-level", vol => {{
    bars.forEach(b => {{
      b.style.height = Math.max(3, Math.round(Math.random() * vol * 22)) + "px";
    }});
  }});

  vapi.on("error", err => {{
    // Ignore non-fatal Krisp warnings
    const t = err?.error?.type ?? err?.type ?? "";
    if (t === "daily-call-object-creation-error" || t === "daily-error") return;
    errEl.textContent = "Error — check browser console.";
    showBars(false);
    active = false;
    btn.className = "";
    console.error("Vapi error:", err);
  }});

  btn.addEventListener("click", async () => {{
    if (active) {{
      await vapi.stop();
    }} else {{
      errEl.textContent = "";
      setStatus("Connecting…", "connecting");
      try {{
        await vapi.start(ASSISTANT_ID);
      }} catch(e) {{
        errEl.textContent = "Could not start call.";
        btn.className = "";
        console.error(e);
      }}
    }}
  }});
</script>
</body>
</html>
""", height=420)
