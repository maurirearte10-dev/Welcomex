"""
Panel del Operador — buscar, acreditar y desacreditar invitados manualmente.
"""

import threading
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
    """Panel de operador: buscar, acreditar y desacreditar invitados manualmente."""

    def __init__(self, parent, evento, kiosco_window=None):
        super().__init__(parent)

        self.evento        = evento
        self.kiosco        = kiosco_window
        self._refresh_job  = None
        self._invitado_sel = None
        self._hash_lista   = None
        self._todos        = []              # inicializado para evitar AttributeError

        # Widget pool — reusar filas sin destruirlas
        self._row_pool      = []
        self._sel_row_frame = None           # frame destacado actualmente
        self._sel_inv_id    = None           # id del invitado seleccionado (persiste en refresh)

        self.title(f"Operador — {evento['nombre']}")
        self.geometry("420x680")
        self.resizable(True, True)
        self.configure(fg_color=COLORS["bg"])

        # Siempre al frente, sin bloquear el foco en otras ventanas
        self.attributes("-topmost", True)
        self.wm_attributes("-topmost", True)

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
        self._debounce_filtro = None
        self.search_var.trace_add("write", self._on_search_change)

        search_entry = ctk.CTkEntry(search_frame,
                     textvariable=self.search_var,
                     placeholder_text="🔍  Buscar por nombre, apellido o mesa...",
                     height=40, font=("Segoe UI", 13),
                     fg_color=COLORS["card"])
        search_entry.pack(fill="x")

        search_entry.bind("<FocusIn>",  lambda e: self._set_typing_mode(True))
        search_entry.bind("<FocusOut>", lambda e: self._set_typing_mode(False))

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

        # ── Panel inferior ───────────────────────────────────────────
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

    def _set_typing_mode(self, active):
        if self.kiosco:
            self.kiosco.typing_mode = active
            self.kiosco.operator_panel_ref = self if active else None
            if active:
                self.kiosco.qr_buffer = ""

    # ------------------------------------------------------------------
    # Datos y refresco (query en hilo separado → UI libre para drag)
    # ------------------------------------------------------------------

    def _refresh(self):
        """Lanza la query en un thread background para no bloquear el hilo de UI."""
        def _query():
            try:
                db.connect()
                nuevos = db.obtener_invitados_evento(self.evento['id'])
                db.disconnect()
            except Exception as e:
                print(f"[OperatorPanel] Error cargando invitados: {e}")
                nuevos = []
            # Devolver resultado al hilo principal
            try:
                self.after(0, lambda: self._on_datos(nuevos))
            except Exception:
                pass  # ventana ya destruida

        threading.Thread(target=_query, daemon=True).start()
        # Programar próximo refresh (cada 2 segundos)
        self._refresh_job = self.after(2000, self._refresh)

    def _on_datos(self, nuevos):
        """Callback en hilo principal con los datos frescos de la BD."""
        nuevo_hash = str([(i['id'], i.get('presente')) for i in nuevos])
        if nuevo_hash != self._hash_lista:
            self._todos      = nuevos
            self._hash_lista = nuevo_hash
            self._actualizar_stats()
            self._filtrar()

    def _actualizar_stats(self):
        total     = len(self._todos)
        presentes = sum(1 for i in self._todos if i.get('presente'))
        self.lbl_stats.configure(text=f"✅ {presentes} / {total}")

    def _on_search_change(self, *_):
        if self._debounce_filtro:
            try:
                self.after_cancel(self._debounce_filtro)
            except Exception:
                pass
        self._debounce_filtro = self.after(200, self._filtrar)

    def _filtrar(self):
        texto  = self.search_var.get().strip().lower()
        filtro = self.filtro_var.get()

        resultado = []
        for inv in self._todos:
            nombre_completo = f"{inv['nombre']} {inv['apellido']}".lower()
            mesa_txt = str(inv.get('mesa') or '').lower()
            if texto and texto not in nombre_completo and texto not in mesa_txt:
                continue
            if filtro == "pendientes"  and inv.get('presente'):
                continue
            if filtro == "acreditados" and not inv.get('presente'):
                continue
            resultado.append(inv)

        self._pintar_lista(resultado)

    # ------------------------------------------------------------------
    # Renderizado con widget pool
    # ------------------------------------------------------------------

    def _pintar_lista(self, invitados):
        MAX_FILAS = 150
        visibles  = invitados[:MAX_FILAS]

        # Limpiar labels extra (sin resultados / mostrando X de Y)
        pool_frames = {r[0] for r in self._row_pool}
        for w in self.list_frame.winfo_children():
            if w not in pool_frames:
                try:
                    w.destroy()
                except Exception:
                    pass

        if not visibles:
            ctk.CTkLabel(self.list_frame,
                         text="Sin resultados",
                         font=("Segoe UI", 13),
                         text_color=COLORS["text_light"]).pack(pady=20)
            for r in self._row_pool:
                r[0].pack_forget()
            self._sel_row_frame = None
            return

        # Reusar o crear filas del pool
        for i, inv in enumerate(visibles):
            if i < len(self._row_pool):
                self._actualizar_fila(self._row_pool[i], inv)
                self._row_pool[i][0].pack(fill="x", pady=3)
            else:
                self._row_pool.append(self._crear_fila(inv))

        # Ocultar sobrantes sin destruir
        for i in range(len(visibles), len(self._row_pool)):
            self._row_pool[i][0].pack_forget()

        # Restaurar highlight del invitado previamente seleccionado
        self._sel_row_frame = None
        if self._sel_inv_id is not None:
            for i, inv in enumerate(visibles):
                if inv['id'] == self._sel_inv_id and i < len(self._row_pool):
                    row = self._row_pool[i][0]
                    row.configure(fg_color=COLORS["border"])
                    self._sel_row_frame = row
                    break

        if len(invitados) > MAX_FILAS:
            ctk.CTkLabel(self.list_frame,
                         text=f"Mostrando {MAX_FILAS} de {len(invitados)} — usá el buscador para filtrar",
                         font=("Segoe UI", 11),
                         text_color=COLORS["text_light"]).pack(pady=8)

    def _crear_fila(self, inv):
        """Crea una fila nueva y retorna (row_frame, icon_lbl, name_lbl, mesa_lbl)."""
        presente = inv.get('presente')

        row = ctk.CTkFrame(self.list_frame,
                           fg_color=COLORS["card"],
                           corner_radius=8,
                           cursor="hand2")
        row.pack(fill="x", pady=3)

        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=8)

        icon_lbl = ctk.CTkLabel(inner, text="✅" if presente else "🕐",
                                font=("Segoe UI", 16), width=28)
        icon_lbl.pack(side="left")

        nombre = f"{inv['nombre']} {inv['apellido']}"
        name_lbl = ctk.CTkLabel(inner, text=nombre,
                                font=("Segoe UI", 13, "bold" if not presente else "normal"),
                                text_color=COLORS["text"] if not presente else COLORS["text_light"],
                                anchor="w")
        name_lbl.pack(side="left", padx=(8, 0), fill="x", expand=True)

        mesa_lbl = ctk.CTkLabel(inner,
                                text=f"Mesa {inv['mesa']}" if inv.get('mesa') else "",
                                font=("Segoe UI", 11),
                                text_color=COLORS["text_light"],
                                width=60)
        if inv.get('mesa'):
            mesa_lbl.pack(side="right")

        widgets = (row, icon_lbl, name_lbl, mesa_lbl)

        def _click(e, i=inv, r=row):
            self._seleccionar(i, r)

        for w in (row, inner, icon_lbl, name_lbl, mesa_lbl):
            w.bind("<Button-1>", _click)

        return widgets

    def _actualizar_fila(self, widgets, inv):
        """Actualiza contenido de una fila del pool sin destruirla."""
        row, icon_lbl, name_lbl, mesa_lbl = widgets
        presente = inv.get('presente')

        # Resetear color (el highlight se restaura en _pintar_lista)
        row.configure(fg_color=COLORS["card"])

        icon_lbl.configure(text="✅" if presente else "🕐")
        name_lbl.configure(
            text=f"{inv['nombre']} {inv['apellido']}",
            font=("Segoe UI", 13, "bold" if not presente else "normal"),
            text_color=COLORS["text"] if not presente else COLORS["text_light"]
        )

        if inv.get('mesa'):
            mesa_lbl.configure(text=f"Mesa {inv['mesa']}")
            mesa_lbl.pack(side="right")
        else:
            mesa_lbl.pack_forget()

        # Rebindar click al nuevo invitado
        def _click(e, i=inv, r=row):
            self._seleccionar(i, r)

        targets = [row, icon_lbl, name_lbl, mesa_lbl]
        children = row.winfo_children()
        if children:
            targets.append(children[0])  # inner frame
        for w in targets:
            try:
                w.bind("<Button-1>", _click)
            except Exception:
                pass

    def _seleccionar(self, inv, row_widget):
        # Highlight
        if self._sel_row_frame:
            try:
                self._sel_row_frame.configure(fg_color=COLORS["card"])
            except Exception:
                pass
        row_widget.configure(fg_color=COLORS["border"])
        self._sel_row_frame = row_widget
        self._sel_inv_id    = inv['id']

        self._invitado_sel = inv
        presente = inv.get('presente')
        nombre   = f"{inv['nombre']} {inv['apellido']}"
        mesa_txt = f" · Mesa {inv['mesa']}" if inv.get('mesa') else ""
        obs      = inv.get('observaciones', '') or ''
        obs_txt  = f"\n📝 {obs}" if obs else ""

        if presente:
            self.lbl_sel.configure(
                text=f"✅ {nombre}{mesa_txt}{obs_txt}\nYa acreditado — podés repetir o desacreditar",
                text_color=COLORS["text_light"])
            self.btn_acreditar.configure(
                text="🔄 Desacreditar", state="normal",
                fg_color=COLORS["warning"])
        else:
            self.lbl_sel.configure(
                text=f"🕐 {nombre}{mesa_txt}{obs_txt}\nListo para acreditar",
                text_color=COLORS["text"])
            self.btn_acreditar.configure(
                text="✅ Acreditar", state="normal",
                fg_color=COLORS["success"])

        # Repetir solo disponible si hay kiosco vinculado
        self.btn_repetir.configure(state="normal" if self.kiosco else "disabled")

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def _acreditar_manual(self):
        inv = self._invitado_sel
        if not inv:
            return

        era_presente = bool(inv.get('presente'))

        try:
            db.connect()
            resultado = db.acreditar_invitado(inv['id'], self.evento['id'], kiosco_id=0)
            db.disconnect()
        except Exception as e:
            print(f"[OperatorPanel] Error acreditando/desacreditando: {e}")
            return

        if resultado:
            inv['presente'] = 0 if era_presente else 1
            nombre = f"{inv['nombre']} {inv['apellido']}"
            mesa   = f" · Mesa {inv['mesa']}" if inv.get('mesa') else ""

            if era_presente:
                self.lbl_sel.configure(
                    text=f"🔄 {nombre}{mesa}\nDesacreditado manualmente",
                    text_color=COLORS["warning"])
                self.btn_acreditar.configure(
                    text="✅ Acreditar", fg_color=COLORS["success"])
            else:
                self.lbl_sel.configure(
                    text=f"✅ {nombre}{mesa}\nAcreditado manualmente",
                    text_color=COLORS["success"])
                self.btn_acreditar.configure(
                    text="🔄 Desacreditar", fg_color=COLORS["warning"])

            if self.kiosco and not era_presente:
                try:
                    self.kiosco._beep("ok")
                    self.kiosco._mostrar_acreditacion(inv, repetir=False)
                except Exception as e:
                    print(f"[OperatorPanel] Kiosco no disponible: {e}")

            self._refresh()

    def _repetir(self):
        inv = self._invitado_sel
        if not inv or not self.kiosco:
            return
        try:
            self.kiosco._beep("repetir")
            self.kiosco._mostrar_acreditacion(inv, repetir=True)
        except Exception as e:
            print(f"[OperatorPanel] Error repitiendo: {e}")

    # ------------------------------------------------------------------
    # Cierre
    # ------------------------------------------------------------------

    def _cerrar(self):
        # Liberar typing_mode antes de destruir (evita leak en el kiosco)
        self._set_typing_mode(False)
        if self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        if self.kiosco:
            self.kiosco.operator_panel_ref = None
        self.destroy()
