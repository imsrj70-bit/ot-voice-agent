"""
Simple Tkinter UI to test the Riley voice agent via vapi_python.
Run: python frontend/call_ui.py
"""

import threading
import tkinter as tk
from tkinter import font as tkfont

from vapi_python import Vapi

# ── CONFIG ────────────────────────────────────────────────────────────────────
VAPI_PUBLIC_KEY = "6434064f-a019-4986-9e62-8b384f282bbf"
ASSISTANT_ID    = "3bba9f4c-82be-4133-99de-c7460d29de70"
# ─────────────────────────────────────────────────────────────────────────────

vapi = Vapi(api_key=VAPI_PUBLIC_KEY)
call_active = False


# ── UI helpers ────────────────────────────────────────────────────────────────

def set_status(text, color="#888888"):
    status_var.set(text)
    status_label.config(fg=color)

def set_active_state():
    call_btn.config(text="End Call", bg="#ef4444",
                    activebackground="#dc2626")
    set_status("Call active — click to end", color="#4ade80")

def set_idle_state():
    call_btn.config(text="Start Call", bg="#22c55e",
                    activebackground="#16a34a")
    set_status("Call ended — ready")

def set_connecting_state():
    call_btn.config(text="Connecting…", bg="#f59e0b",
                    activebackground="#d97706")
    set_status("Connecting…", color="#fbbf24")


# ── Call logic (runs in background thread) ────────────────────────────────────

def do_start():
    global call_active
    root.after(0, set_connecting_state)
    try:
        vapi.start(assistant_id=ASSISTANT_ID)
        call_active = True
        root.after(0, set_active_state)
    except Exception as e:
        root.after(0, lambda: set_status(f"Failed: {e}", color="#f87171"))
        root.after(0, set_idle_state)

def do_stop():
    global call_active
    try:
        vapi.stop()
    except Exception:
        pass
    call_active = False
    root.after(0, set_idle_state)

def toggle_call():
    if call_active:
        threading.Thread(target=do_stop, daemon=True).start()
    else:
        threading.Thread(target=do_start, daemon=True).start()


# ── Build UI ──────────────────────────────────────────────────────────────────

root = tk.Tk()
root.title("Riley — Ordertron Voice Agent")
root.configure(bg="#0d0d0d")
root.resizable(False, False)

PADX, PADY = 32, 24
BG     = "#0d0d0d"
CARD   = "#1a1a1a"
BORDER = "#2a2a2a"

# Card frame
card = tk.Frame(root, bg=CARD, bd=0, highlightthickness=1,
                highlightbackground=BORDER)
card.pack(padx=PADX, pady=PADY, fill=tk.BOTH, expand=True)

inner = tk.Frame(card, bg=CARD)
inner.pack(padx=32, pady=28)

# Avatar + title
title_font  = tkfont.Font(family="Helvetica", size=18, weight="bold")
small_font  = tkfont.Font(family="Helvetica", size=11)
btn_font    = tkfont.Font(family="Helvetica", size=12, weight="bold")

tk.Label(inner, text="🤖", font=tkfont.Font(size=36), bg=CARD).pack()
tk.Label(inner, text="Riley", font=title_font, fg="#ffffff", bg=CARD).pack(pady=(6, 2))
tk.Label(inner, text="Ordertron Voice Agent", font=small_font,
         fg="#666666", bg=CARD).pack(pady=(0, 20))

# Call button
call_btn = tk.Button(
    inner, text="Start Call",
    font=btn_font, fg="#ffffff",
    bg="#22c55e", activebackground="#16a34a", activeforeground="#ffffff",
    relief=tk.FLAT, bd=0, padx=28, pady=12,
    cursor="hand2", command=toggle_call
)
call_btn.pack(pady=(0, 12))

# Status
status_var = tk.StringVar(value="Click to start a call")
status_label = tk.Label(inner, textvariable=status_var, font=small_font,
                        fg="#888888", bg=CARD)
status_label.pack(pady=(0, 8))

# Footer
tk.Label(root, text="for internal testing only",
         font=tkfont.Font(size=9), fg="#333333", bg=BG).pack(pady=(0, 10))

root.mainloop()
