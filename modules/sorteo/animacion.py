"""
WelcomeX - Animación de Sorteo
Scroll vertical suave con easing para selección de ganadores.
Usa tkinter Canvas para animación fluida a ~60fps.
"""

import time
import random
import tkinter as tk
import customtkinter as ctk
from config.settings import COLORS
from modules.i18n import t


# ============================================
# SORTEO GENERAL (1 o más ganadores)
# ============================================

class SorteoAnimacion(ctk.CTkToplevel):
    """Animación de sorteo con scroll vertical suave tipo slot machine.

    Para 1 ganador: animación completa con revelación.
    Para múltiples: animación secuencial de cada ganador.
    """

    ITEM_HEIGHT = 65
    DURATION = 5.0
    ROTATIONS = 3
    FRAME_MS = 16       # ~60fps
    GOLD = "#d4af37"
    HIGHLIGHT_BG = "#1a2a4a"

    def __init__(self, parent, participantes, ganadores, on_complete=None):
        super().__init__(parent)

        self.all_participantes = list(participantes)
        self.all_ganadores = list(ganadores)
        self.on_complete = on_complete
        self.ganador_idx = 0       # índice del ganador actual en la secuencia
        self.animating = False
        self.start_time = None

        self._setup_window()
        self._create_ui()
        self.after(400, self._iniciar_siguiente_ganador)

    def _setup_window(self):
        self.title(t("sorteo.in_progress"))
        w, h = 850, 680
        self.geometry(f"{w}x{h}")
        self.transient(self.master)
        self.grab_set()
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg"])

        self.update_idletasks()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _create_ui(self):
        # Título
        self.title_label = ctk.CTkLabel(
            self, text=f"🎲 {t('sorteo.mixing')}",
            font=("Arial", 30, "bold"), text_color=COLORS["primary"]
        )
        self.title_label.pack(pady=(25, 10))

        # Indicador de ganador actual (para múltiples)
        self.counter_label = ctk.CTkLabel(
            self, text="", font=("Arial", 16), text_color=COLORS["text_light"]
        )
        self.counter_label.pack(pady=(0, 5))

        # Card contenedor del canvas
        card = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=15)
        card.pack(padx=50, pady=10, fill="both", expand=True)

        self.canvas = tk.Canvas(
            card, bg=COLORS["card"], highlightthickness=0, bd=0
        )
        self.canvas.pack(fill="both", expand=True, padx=15, pady=15)

        # Barra de progreso
        prog_container = ctk.CTkFrame(self, fg_color="#1f1f2e", height=6, corner_radius=3)
        prog_container.pack(fill="x", padx=80, pady=(10, 5))
        self.progress_bar = ctk.CTkFrame(
            prog_container, fg_color=COLORS["primary"], height=6, corner_radius=3
        )
        self.progress_bar.place(x=0, y=0, relwidth=0)

        # Frame inferior para botones
        self.bottom_frame = ctk.CTkFrame(self, fg_color="transparent", height=80)
        self.bottom_frame.pack(fill="x", padx=50, pady=(5, 20))

    # --- Secuencia de múltiples ganadores ---

    def _iniciar_siguiente_ganador(self):
        """Inicia la animación para el siguiente ganador en la secuencia"""
        if self.ganador_idx >= len(self.all_ganadores):
            self._mostrar_resumen_final()
            return

        total = len(self.all_ganadores)
        if total > 1:
            self.counter_label.configure(
                text=f"{t('sorteo.winner_num')} {self.ganador_idx + 1} / {total}"
            )
        else:
            self.counter_label.configure(text="")

        ganador = self.all_ganadores[self.ganador_idx]

        # Preparar participantes (shuffle)
        self._participantes = list(self.all_participantes)
        random.shuffle(self._participantes)
        self._ganador = ganador

        # Encontrar índice del ganador en lista shuffled
        self._winner_idx = 0
        for i, p in enumerate(self._participantes):
            if p['id'] == ganador['id']:
                self._winner_idx = i
                break

        n = len(self._participantes)
        if n < 2:
            # Muy pocos participantes, revelar directo
            self._show_winner()
            return

        list_h = n * self.ITEM_HEIGHT
        self._total_scroll = self.ROTATIONS * list_h + self._winner_idx * self.ITEM_HEIGHT

        # Limpiar bottom frame
        for w in self.bottom_frame.winfo_children():
            w.destroy()

        # Reset título
        self.title_label.configure(
            text=f"🎲 {t('sorteo.mixing')}",
            text_color=COLORS["primary"]
        )
        self.progress_bar.place(x=0, y=0, relwidth=0)

        self.start_time = time.time()
        self.animating = True
        self._animate()

    # --- Animación principal ---

    @staticmethod
    def _ease_out_quart(x):
        return 1 - pow(1 - x, 4)

    def _animate(self):
        if not self.animating:
            return
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return

        elapsed = time.time() - self.start_time
        progress = min(elapsed / self.DURATION, 1.0)
        eased = self._ease_out_quart(progress)

        scroll = self._total_scroll * eased

        # Barra de progreso
        self.progress_bar.place(x=0, y=0, relwidth=progress)

        # Título según fase
        if progress < 0.3:
            self.title_label.configure(text=f"🎲 {t('sorteo.mixing')}")
        elif progress < 0.7:
            self.title_label.configure(text=f"🎰 {t('sorteo.selecting')}")
        else:
            self.title_label.configure(text=f"🔥 {t('sorteo.almost')}")

        self._draw_names(scroll)

        if progress < 1.0:
            self.after(self.FRAME_MS, self._animate)
        else:
            self.after(200, self._start_reveal)

    def _draw_names(self, scroll_offset):
        """Dibuja los nombres con scroll vertical en el canvas"""
        self.canvas.delete("all")

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw <= 1 or ch <= 1:
            return

        cx = cw / 2
        cy = ch / 2
        n = len(self._participantes)

        # Banda de selección central
        hl = self.ITEM_HEIGHT * 0.85
        self.canvas.create_rectangle(
            15, cy - hl / 2, cw - 15, cy + hl / 2,
            fill=self.HIGHLIGHT_BG, outline=COLORS["primary"], width=2
        )

        # Flechas indicadoras
        self.canvas.create_polygon(
            8, cy - 8, 8, cy + 8, 18, cy, fill=COLORS["primary"]
        )
        self.canvas.create_polygon(
            cw - 8, cy - 8, cw - 8, cy + 8, cw - 18, cy, fill=COLORS["primary"]
        )

        # Calcular posición de scroll
        center_float = scroll_offset / self.ITEM_HEIGHT
        center_int = int(center_float)
        sub_pixel = (center_float - center_int) * self.ITEM_HEIGHT

        # Dibujar nombres visibles
        num_slots = int(ch / self.ITEM_HEIGHT) + 4
        half = num_slots // 2

        for slot in range(-half, half + 1):
            idx = (center_int + slot) % n
            y = cy + slot * self.ITEM_HEIGHT - sub_pixel

            if y < -self.ITEM_HEIGHT or y > ch + self.ITEM_HEIGHT:
                continue

            p = self._participantes[idx]
            name = f"{p['apellido']}, {p['nombre']}"
            mesa = p.get('mesa', '')
            display = f"{name}    Mesa {mesa}" if mesa else name

            # Estilo según distancia al centro
            dist = abs(y - cy)

            if dist < self.ITEM_HEIGHT * 0.45:
                font = ("Arial", 26, "bold")
                color = self.GOLD
            elif dist < self.ITEM_HEIGHT * 1.3:
                font = ("Arial", 20)
                color = "#ffffff"
            elif dist < self.ITEM_HEIGHT * 2.3:
                font = ("Arial", 16)
                color = "#9ca3af"
            elif dist < self.ITEM_HEIGHT * 3.3:
                font = ("Arial", 13)
                color = "#6b7280"
            else:
                font = ("Arial", 11)
                color = "#4b5563"

            self.canvas.create_text(
                cx, y, text=display,
                font=font, fill=color, anchor="center"
            )

        # Cobertura fade superior e inferior
        fade = 50
        self.canvas.create_rectangle(0, 0, cw, fade, fill=COLORS["card"], outline="")
        self.canvas.create_rectangle(0, ch - fade, cw, ch, fill=COLORS["card"], outline="")

    # --- Revelación del ganador ---

    def _start_reveal(self):
        """Transición con parpadeo antes de revelar"""
        self.animating = False
        self._blink_count = 0
        self._do_blink()

    def _do_blink(self):
        if self._blink_count >= 6:
            self._show_winner()
            return
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return

        if self._blink_count % 2 == 0:
            self.title_label.configure(text="🎯", text_color=COLORS["warning"])
        else:
            self.title_label.configure(text="🎰", text_color=COLORS["primary"])

        self._blink_count += 1
        self.after(150, self._do_blink)

    def _show_winner(self):
        """Muestra el ganador con efecto de celebración"""
        self.canvas.delete("all")

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        cx = cw / 2
        cy = ch / 2

        self.title_label.configure(
            text=f"🏆 {t('sorteo.winner_announce')}",
            text_color=COLORS["success"]
        )
        self.progress_bar.place(x=0, y=0, relwidth=1.0)

        g = self._ganador

        # Nombre del ganador
        self.canvas.create_text(
            cx, cy - 40,
            text=f"✨ {g['apellido']}, {g['nombre']} ✨",
            font=("Arial", 36, "bold"), fill=COLORS["success"], anchor="center"
        )

        # Mesa
        if g.get('mesa'):
            self.canvas.create_text(
                cx, cy + 20,
                text=f"Mesa {g['mesa']}",
                font=("Arial", 24), fill=COLORS["primary"], anchor="center"
            )

        # Felicitaciones
        self.canvas.create_text(
            cx, cy + 75,
            text=f"🎉 {t('sorteo.congratulations')} 🎉",
            font=("Arial", 20), fill=COLORS["text_light"], anchor="center"
        )

        # Botón según si hay más ganadores o no
        for w in self.bottom_frame.winfo_children():
            w.destroy()

        if self.ganador_idx < len(self.all_ganadores) - 1:
            # Hay más ganadores - botón "Siguiente"
            ctk.CTkButton(
                self.bottom_frame,
                text=f"▶ {t('sorteo.next_winner')}",
                command=self._siguiente_ganador,
                height=55, width=300, font=("Arial", 16, "bold"),
                fg_color=COLORS["primary"]
            ).pack(pady=10)
        else:
            # Último ganador - botón cerrar
            ctk.CTkButton(
                self.bottom_frame,
                text=t("sorteo.continue"),
                command=self._close,
                height=55, width=300, font=("Arial", 16, "bold"),
                fg_color=COLORS["success"]
            ).pack(pady=10)

    def _siguiente_ganador(self):
        """Avanza al siguiente ganador"""
        self.ganador_idx += 1
        self._iniciar_siguiente_ganador()

    def _mostrar_resumen_final(self):
        """Para múltiples ganadores: muestra resumen al final"""
        # Solo se llega aquí si se agotaron los ganadores (no debería pasar normalmente)
        self._close()

    def _close(self):
        if self.on_complete:
            self.on_complete()
        self.destroy()


# ============================================
# SORTEO POR MESA (secuencial)
# ============================================

class SorteoPorMesaAnimacion(ctk.CTkToplevel):
    """Animación de sorteo secuencial por mesa.
    Sortea una mesa a la vez, de la mayor a la menor.
    """

    ITEM_HEIGHT = 60
    DURATION_PER_TABLE = 3.5
    ROTATIONS = 2
    FRAME_MS = 16
    PAUSE_BETWEEN = 2000   # ms entre mesas
    GOLD = "#d4af37"
    HIGHLIGHT_BG = "#1a2a4a"

    def __init__(self, parent, participantes_por_mesa, ganadores_por_mesa, on_complete=None):
        super().__init__(parent)

        self.participantes_por_mesa = participantes_por_mesa
        self.ganadores_por_mesa = ganadores_por_mesa
        self.on_complete = on_complete

        self.mesas = sorted(participantes_por_mesa.keys(), reverse=True)
        self.mesa_idx = 0
        self.ganadores_texto = []
        self.animating = False
        self.start_time = None

        self._setup_window()
        self._create_ui()
        self.after(500, self._sortear_siguiente_mesa)

    def _setup_window(self):
        self.title(t("sorteo.per_table_title"))
        w, h = 900, 720
        self.geometry(f"{w}x{h}")
        self.transient(self.master)
        self.grab_set()
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg"])

        self.update_idletasks()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _create_ui(self):
        self.title_label = ctk.CTkLabel(
            self, text=f"🎰 {t('sorteo.per_table_title')}",
            font=("Arial", 30, "bold"), text_color=COLORS["primary"]
        )
        self.title_label.pack(pady=(20, 5))

        self.mesa_label = ctk.CTkLabel(
            self, text="", font=("Arial", 22), text_color=COLORS["text_light"]
        )
        self.mesa_label.pack(pady=(0, 10))

        # Canvas
        card = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=15)
        card.pack(padx=50, pady=5, fill="both", expand=True)

        self.canvas = tk.Canvas(
            card, bg=COLORS["card"], highlightthickness=0, bd=0
        )
        self.canvas.pack(fill="both", expand=True, padx=15, pady=15)

        # Lista de ganadores acumulados
        self.winners_frame = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=10)
        self.winners_frame.pack(fill="x", padx=50, pady=(5, 5))

        self.winners_label = ctk.CTkLabel(
            self.winners_frame, text="",
            font=("Arial", 13), text_color=COLORS["text_light"],
            justify="left"
        )
        self.winners_label.pack(anchor="w", padx=15, pady=8)

        # Frame inferior
        self.bottom_frame = ctk.CTkFrame(self, fg_color="transparent", height=70)
        self.bottom_frame.pack(fill="x", padx=50, pady=(0, 15))

    # --- Secuencia por mesa ---

    def _sortear_siguiente_mesa(self):
        if self.mesa_idx >= len(self.mesas):
            self._show_final()
            return

        mesa = self.mesas[self.mesa_idx]
        participantes = self.participantes_por_mesa[mesa]
        ganador = self.ganadores_por_mesa[mesa]

        self.mesa_label.configure(
            text=f"{t('sorteo.table', mesa=mesa)} ({self.mesa_idx + 1}/{len(self.mesas)})"
        )
        self.title_label.configure(
            text=f"🎰 {t('sorteo.per_table_title')}",
            text_color=COLORS["primary"]
        )

        # Preparar
        self._current_participants = list(participantes)
        random.shuffle(self._current_participants)
        self._current_ganador = ganador

        # Encontrar winner
        self._current_winner_idx = 0
        for i, p in enumerate(self._current_participants):
            if p['id'] == ganador['id']:
                self._current_winner_idx = i
                break

        n = len(self._current_participants)
        if n < 2:
            self._mesa_winner_reveal()
            return

        list_h = n * self.ITEM_HEIGHT
        self._total_scroll = self.ROTATIONS * list_h + self._current_winner_idx * self.ITEM_HEIGHT

        self.start_time = time.time()
        self.animating = True
        self._animate_mesa()

    @staticmethod
    def _ease_out_quart(x):
        return 1 - pow(1 - x, 4)

    def _animate_mesa(self):
        if not self.animating:
            return
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return

        elapsed = time.time() - self.start_time
        progress = min(elapsed / self.DURATION_PER_TABLE, 1.0)
        eased = self._ease_out_quart(progress)

        scroll = self._total_scroll * eased
        self._draw_names(scroll)

        # Título según fase
        if progress < 0.3:
            self.title_label.configure(text=f"🎲 {t('sorteo.mixing')}")
        elif progress < 0.7:
            self.title_label.configure(text=f"🎰 {t('sorteo.selecting')}")
        else:
            self.title_label.configure(text=f"🔥 {t('sorteo.almost')}")

        if progress < 1.0:
            self.after(self.FRAME_MS, self._animate_mesa)
        else:
            self.animating = False
            self.after(300, self._mesa_winner_reveal)

    def _draw_names(self, scroll_offset):
        self.canvas.delete("all")

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw <= 1 or ch <= 1:
            return

        cx = cw / 2
        cy = ch / 2
        n = len(self._current_participants)

        # Banda de selección
        hl = self.ITEM_HEIGHT * 0.85
        self.canvas.create_rectangle(
            15, cy - hl / 2, cw - 15, cy + hl / 2,
            fill=self.HIGHLIGHT_BG, outline=COLORS["primary"], width=2
        )

        # Flechas
        self.canvas.create_polygon(
            8, cy - 8, 8, cy + 8, 18, cy, fill=COLORS["primary"]
        )
        self.canvas.create_polygon(
            cw - 8, cy - 8, cw - 8, cy + 8, cw - 18, cy, fill=COLORS["primary"]
        )

        center_float = scroll_offset / self.ITEM_HEIGHT
        center_int = int(center_float)
        sub = (center_float - center_int) * self.ITEM_HEIGHT

        num_slots = int(ch / self.ITEM_HEIGHT) + 4
        half = num_slots // 2

        for slot in range(-half, half + 1):
            idx = (center_int + slot) % n
            y = cy + slot * self.ITEM_HEIGHT - sub

            if y < -self.ITEM_HEIGHT or y > ch + self.ITEM_HEIGHT:
                continue

            p = self._current_participants[idx]
            display = f"{p['apellido']}, {p['nombre']}"

            dist = abs(y - cy)
            if dist < self.ITEM_HEIGHT * 0.45:
                font, color = ("Arial", 24, "bold"), self.GOLD
            elif dist < self.ITEM_HEIGHT * 1.3:
                font, color = ("Arial", 18), "#ffffff"
            elif dist < self.ITEM_HEIGHT * 2.3:
                font, color = ("Arial", 15), "#9ca3af"
            else:
                font, color = ("Arial", 12), "#4b5563"

            self.canvas.create_text(
                cx, y, text=display,
                font=font, fill=color, anchor="center"
            )

        # Fade
        self.canvas.create_rectangle(0, 0, cw, 40, fill=COLORS["card"], outline="")
        self.canvas.create_rectangle(0, ch - 40, cw, ch, fill=COLORS["card"], outline="")

    def _mesa_winner_reveal(self):
        """Revela el ganador de la mesa actual"""
        self.canvas.delete("all")

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        cx, cy = cw / 2, ch / 2

        g = self._current_ganador
        mesa = self.mesas[self.mesa_idx]

        self.title_label.configure(
            text=f"🏆 {t('sorteo.winner_table', mesa=mesa)}",
            text_color=COLORS["success"]
        )

        self.canvas.create_text(
            cx, cy - 15,
            text=f"🏆 {g['apellido']}, {g['nombre']}",
            font=("Arial", 30, "bold"), fill=COLORS["success"], anchor="center"
        )

        # Actualizar lista acumulada
        self.ganadores_texto.append(
            f"Mesa {mesa}: {g['apellido']}, {g['nombre']}"
        )
        self.winners_label.configure(
            text="  |  ".join(self.ganadores_texto)
        )

        # Siguiente mesa
        self.mesa_idx += 1
        self.after(self.PAUSE_BETWEEN, self._sortear_siguiente_mesa)

    def _show_final(self):
        """Muestra resumen final con todos los ganadores"""
        self.title_label.configure(
            text=f"🏆 {t('sorteo.raffle_complete')}",
            text_color=COLORS["success"]
        )
        self.mesa_label.configure(text="")

        self.canvas.delete("all")
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        cx = cw / 2

        # Calcular posición vertical centrada
        total_h = len(self.ganadores_texto) * 40
        start_y = max(30, (ch - total_h) / 2)

        for i, texto in enumerate(self.ganadores_texto):
            self.canvas.create_text(
                cx, start_y + i * 40,
                text=f"🏆 {texto}",
                font=("Arial", 18, "bold"), fill=COLORS["success"], anchor="center"
            )

        for w in self.bottom_frame.winfo_children():
            w.destroy()

        ctk.CTkButton(
            self.bottom_frame,
            text=t("sorteo.continue"),
            command=self._close,
            height=55, width=300, font=("Arial", 16, "bold"),
            fg_color=COLORS["primary"]
        ).pack(pady=10)

    def _close(self):
        if self.on_complete:
            self.on_complete()
        self.destroy()
