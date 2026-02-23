import customtkinter as ctk
from modules.database import db

COLORS = {
    "bg":         "#0f172a",
    "card":       "#1e293b",
    "sidebar":    "#1e293b",
    "border":     "#334155",
    "primary":    "#3b82f6",
    "success":    "#10b981",
    "warning":    "#f59e0b",
    "danger":     "#ef4444",
    "text":       "#f8fafc",
    "text_light": "#94a3b8",
    "gold":       "#d4af37",
}


class OperatorPanel(ctk.CTkToplevel):
    """Panel de operador: buscar y acreditar invitados manualmente."""

    def __init__(self, parent, evento, kiosco_window=None):
        super().__init__(parent)

        self.evento       = evento
        self.kiosco       = kiosco_window   # referencia al KioscoWindow
        self._refresh_job = None
        self._invitado_sel = None           # invitado seleccionado en la lista

        self.title(f"Operador — {evento['nombre']}")
        self.geometry("420x680")
        self.resizable(False, True)
        self.attributes('-topmost', True)
        self.configure(fg_color=COLORS["bg"])

        # Posicionar en la esquina superior derecha
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        self.geometry(f"+{sw - 440}+20")

        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 14, "pady": 6}

        # ── Header ──────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=COLORS["sidebar"], corner_radius=0, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="📋 Panel Operador",
                     font=("Segoe UI", 16, "bold"),
                     text_color=COLORS["gold"]).pack(side="left", padx=16, pady=10)

        self.lbl_stats = ctk.CTkLabel(header, text="",
                                      font=("Segoe UI", 13),
                                      text_color=COLORS["text_light"])
        self.lbl_stats.pack(side="right", padx=16)

        # ── Buscador ────────────────────────────────────────────────
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=14, pady=(10, 4))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._filtrar())

        ctk.CTkEntry(search_frame,
                     textvariable=self.search_var,
                     placeholder_text="🔍  Buscar por nombre o apellido...",
                     height=40, font=("Segoe UI", 13),
                     fg_color=COLORS["card"]).pack(fill="x")

        # ── Filtro estado ────────────────────────────────────────────
        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.pack(fill="x", padx=14, pady=(0, 6))

        self.filtro_var = ctk.StringVar(value="todos")
        for val, label in [("todos", "Todos"), ("pendientes", "Pendientes"), ("acreditados", "Acreditados")]:
            ctk.CTkRadioButton(filter_frame, text=label,
                               variable=self.filtro_var, value=val,
                               font=("Segoe UI", 12),
                               command=self._filtrar).pack(side="left", padx=(0, 12))

        # ── Lista de invitados ────────────────────────────────────────
        self.list_frame = ctk.CTkScrollableFrame(self,
                                                 fg_color=COLORS["bg"],
                                                 border_width=1,
                                                 border_color=COLORS["border"])
        self.list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        # ── Panel inferior: acreditar / repetir ──────────────────────
        bottom = ctk.CTkFrame(self, fg_color=COLORS["card"],
                              corner_radius=10, border_width=1,
                              border_color=COLORS["border"])
        bottom.pack(fill="x", padx=14, pady=(0, 14))

        inner = ctk.CTkFrame(bottom, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        self.lbl_sel = ctk.CTkLabel(inner,
                                    text="Seleccioná un invitado de la lista",
                                    font=("Segoe UI", 12),
                                    text_color=COLORS["text_light"],
                                    wraplength=360, justify="left")
        self.lbl_sel.pack(fill="x", pady=(0, 10))

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x")

        self.btn_acreditar = ctk.CTkButton(btn_row,
                                           text="✅ Acreditar",
                                           command=self._acreditar_manual,
                                           height=44, font=("Segoe UI", 14, "bold"),
                                           fg_color=COLORS["success"],
                                           state="disabled")
        self.btn_acreditar.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_repetir = ctk.CTkButton(btn_row,
                                         text="🔁 Repetir",
                                         command=self._repetir,
                                         height=44, font=("Segoe UI", 14),
                                         fg_color=COLORS["primary"],
                                         state="disabled")
        self.btn_repetir.pack(side="left", fill="x", expand=True)

    # ------------------------------------------------------------------
    # Datos y refresco
    # ------------------------------------------------------------------

    def _refresh(self):
        """Recarga invitados desde la BD y repinta la lista."""
        try:
            db.connect()
            self._todos = db.obtener_invitados_evento(self.evento['id'])
            db.disconnect()
        except Exception as e:
            print(f"[OperatorPanel] Error cargando invitados: {e}")
            self._todos = []

        self._actualizar_stats()
        self._filtrar()

        # Programar próximo refresh (cada 3 segundos)
        self._refresh_job = self.after(3000, self._refresh)

    def _actualizar_stats(self):
        total     = len(self._todos)
        presentes = sum(1 for i in self._todos if i.get('presente'))
        self.lbl_stats.configure(text=f"✅ {presentes} / {total}")

    def _filtrar(self):
        texto  = self.search_var.get().strip().lower()
        filtro = self.filtro_var.get()

        resultado = []
        for inv in self._todos:
            nombre_completo = f"{inv['nombre']} {inv['apellido']}".lower()
            if texto and texto not in nombre_completo:
                continue
            if filtro == "pendientes"  and inv.get('presente'):
                continue
            if filtro == "acreditados" and not inv.get('presente'):
                continue
            resultado.append(inv)

        self._pintar_lista(resultado)

    def _pintar_lista(self, invitados):
        # Destruir filas anteriores
        for w in self.list_frame.winfo_children():
            w.destroy()

        if not invitados:
            ctk.CTkLabel(self.list_frame,
                         text="Sin resultados",
                         font=("Segoe UI", 13),
                         text_color=COLORS["text_light"]).pack(pady=20)
            return

        for inv in invitados:
            self._crear_fila(inv)

    def _crear_fila(self, inv):
        presente = inv.get('presente')
        bg_color = COLORS["card"]

        row = ctk.CTkFrame(self.list_frame,
                           fg_color=bg_color,
                           corner_radius=8,
                           cursor="hand2")
        row.pack(fill="x", pady=3)
        row.bind("<Button-1>", lambda e, i=inv, r=row: self._seleccionar(i, r))

        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=8)
        inner.bind("<Button-1>", lambda e, i=inv, r=row: self._seleccionar(i, r))

        # Estado
        icono = "✅" if presente else "🕐"
        ctk.CTkLabel(inner, text=icono,
                     font=("Segoe UI", 16), width=28).pack(side="left")

        # Nombre
        nombre = f"{inv['nombre']} {inv['apellido']}"
        color_nombre = COLORS["text"] if not presente else COLORS["text_light"]
        lbl_nombre = ctk.CTkLabel(inner, text=nombre,
                                  font=("Segoe UI", 13, "bold" if not presente else "normal"),
                                  text_color=color_nombre,
                                  anchor="w")
        lbl_nombre.pack(side="left", padx=(8, 0), fill="x", expand=True)
        lbl_nombre.bind("<Button-1>", lambda e, i=inv, r=row: self._seleccionar(i, r))

        # Mesa
        if inv.get('mesa'):
            ctk.CTkLabel(inner,
                         text=f"Mesa {inv['mesa']}",
                         font=("Segoe UI", 11),
                         text_color=COLORS["text_light"],
                         width=60).pack(side="right")

    def _seleccionar(self, inv, row_widget):
        self._invitado_sel = inv
        presente = inv.get('presente')
        nombre   = f"{inv['nombre']} {inv['apellido']}"
        mesa_txt = f" · Mesa {inv['mesa']}" if inv.get('mesa') else ""

        if presente:
            self.lbl_sel.configure(
                text=f"✅ {nombre}{mesa_txt}\nYa acreditado — podés repetir su presentación",
                text_color=COLORS["text_light"])
            self.btn_acreditar.configure(state="disabled")
        else:
            self.lbl_sel.configure(
                text=f"🕐 {nombre}{mesa_txt}\nListo para acreditar",
                text_color=COLORS["text"])
            self.btn_acreditar.configure(state="normal")

        self.btn_repetir.configure(state="normal")

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def _acreditar_manual(self):
        inv = self._invitado_sel
        if not inv or inv.get('presente'):
            return

        try:
            db.connect()
            resultado = db.acreditar_invitado(inv['id'], self.evento['id'], kiosco_id=0)
            db.disconnect()
        except Exception as e:
            print(f"[OperatorPanel] Error acreditando: {e}")
            return

        if resultado:
            inv['presente'] = 1  # actualizar objeto local
            nombre = f"{inv['nombre']} {inv['apellido']}"
            mesa   = f" · Mesa {inv['mesa']}" if inv.get('mesa') else ""
            self.lbl_sel.configure(
                text=f"✅ {nombre}{mesa}\nAcreditado manualmente",
                text_color=COLORS["success"])
            self.btn_acreditar.configure(state="disabled")

            # Mostrar en el kiosco si está abierto
            if self.kiosco:
                try:
                    self.kiosco._beep("ok")
                    self.kiosco._mostrar_acreditacion(inv, repetir=False)
                except Exception as e:
                    print(f"[OperatorPanel] Kiosco no disponible: {e}")

            # Refrescar lista
            self._refresh()

    def _repetir(self):
        inv = self._invitado_sel
        if not inv:
            return

        if self.kiosco:
            try:
                self.kiosco._beep("repetir")
                self.kiosco._mostrar_acreditacion(inv, repetir=True)
            except Exception as e:
                print(f"[OperatorPanel] Error repitiendo: {e}")
        else:
            print("[OperatorPanel] Sin kiosco vinculado, no se puede repetir presentación")

    # ------------------------------------------------------------------
    # Cierre
    # ------------------------------------------------------------------

    def _cerrar(self):
        if self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        self.destroy()
