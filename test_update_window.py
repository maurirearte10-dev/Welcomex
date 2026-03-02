"""
Test ventana de actualización — simula descarga + instalación + reinicio.
Ejecutar: python test_update_window.py
"""
import customtkinter as ctk
import tkinter as tk

ctk.set_appearance_mode("dark")
root = ctk.CTk()
root.withdraw()

def _prog_set(canvas, rect, pct, color="#f59e0b"):
    w = canvas.winfo_width()
    if w < 2:
        w = 480
    canvas.coords(rect, 0, 0, int(w * pct), 14)
    canvas.itemconfig(rect, fill=color)

version = "1.3.8"
win = tk.Toplevel(root)
win.title(f"Actualizando WelcomeX a v{version}")
win.configure(bg="#1a1a2e")
win.resizable(False, False)
win.attributes('-topmost', True)

W, H = 520, 390
win.update_idletasks()
x = (win.winfo_screenwidth()  - W) // 2
y = (win.winfo_screenheight() - H) // 2
win.geometry(f"{W}x{H}+{x}+{y}")

main = tk.Frame(win, bg="#2b2b3c", padx=24, pady=16)
main.pack(expand=True, fill="both", padx=16, pady=16)

tk.Label(main, text="Actualizando WelcomeX",
         font=("Segoe UI", 18, "bold"), fg="#f59e0b", bg="#2b2b3c").pack(pady=(4, 2))
tk.Label(main, text=f"Instalando version {version}",
         font=("Segoe UI", 12), fg="#9ca3af", bg="#2b2b3c").pack(pady=(0, 12))

steps_txt = [
    "OK   Nueva version detectada",
    "...  Descargando actualizacion...",
    "...  Instalando",
    "...  Reiniciando WelcomeX",
]
step_labels = []
steps_bg = tk.Frame(main, bg="#0f0f0f", padx=12, pady=6)
steps_bg.pack(fill="x", pady=(0, 10))
for s in steps_txt:
    lbl = tk.Label(steps_bg, text=s, font=("Segoe UI", 12),
                   fg="#9ca3af", bg="#0f0f0f", anchor="w")
    lbl.pack(fill="x", pady=3)
    step_labels.append(lbl)
step_labels[0].configure(fg="#ffffff")

prog_outer = tk.Frame(main, bg="#374151", height=14)
prog_outer.pack(fill="x", pady=(0, 6))
prog_outer.pack_propagate(False)
prog_canvas = tk.Canvas(prog_outer, height=14, bg="#374151",
                         highlightthickness=0, bd=0)
prog_canvas.pack(fill="both", expand=True)
prog_rect = prog_canvas.create_rectangle(0, 0, 0, 14, fill="#f59e0b", outline="")

detail = tk.Label(main, text="Iniciando descarga...",
                  font=("Segoe UI", 11), fg="#9ca3af", bg="#2b2b3c")
detail.pack(pady=(0, 8))

warn = tk.Frame(main, bg="#2d1b00", padx=10, pady=6)
warn.pack(fill="x")
tk.Label(warn, text="No cierres la aplicacion durante la actualizacion",
         font=("Segoe UI", 10), fg="#f59e0b", bg="#2d1b00").pack()

win.update()

# ── FASE 1: Descarga (0 → 100%) ──────────────────────────────────────────────
_pct = [0.0]
def _fase_descarga():
    _pct[0] += 0.02
    if _pct[0] > 1.0:
        _pct[0] = 1.0
    _prog_set(prog_canvas, prog_rect, _pct[0])
    mb = _pct[0] * 45
    detail.configure(text=f"Descargando...  {mb:.1f} MB / 45.0 MB  ({int(_pct[0]*100)}%)")
    if _pct[0] < 1.0:
        win.after(60, _fase_descarga)
    else:
        win.after(400, _inicio_instalacion)

# ── FASE 2: Instalando (barra lineal 0 → 100%) ───────────────────────────────
_inst = [0.0]
def _inicio_instalacion():
    detail.configure(text="Descarga completa")
    step_labels[1].configure(text="OK   Descarga completa", fg="#ffffff")
    step_labels[2].configure(text="...  Instalando...",     fg="#f59e0b")
    _prog_set(prog_canvas, prog_rect, 0.0)
    win.after(30, _fase_instalacion)

def _fase_instalacion():
    _inst[0] += 0.012
    if _inst[0] >= 1.0:
        _prog_set(prog_canvas, prog_rect, 1.0)
        win.after(300, _inicio_reinicio)
        return
    _prog_set(prog_canvas, prog_rect, _inst[0])
    win.after(30, _fase_instalacion)

# ── FASE 3: Reiniciando ───────────────────────────────────────────────────────
def _inicio_reinicio():
    step_labels[2].configure(text="OK   Instalacion lista",       fg="#ffffff")
    step_labels[3].configure(text="...  Reiniciando WelcomeX...", fg="#f59e0b")
    detail.configure(text="La aplicacion se cerrara y reabrira automaticamente")
    win.after(2000, root.quit)

win.after(500, _fase_descarga)

print("Abierto — se cierra solo al terminar")
root.mainloop()
print("OK")
