#!/usr/bin/env python3
"""
WelcomeX - Sistema de Gestión de Eventos
Versión Definitiva
"""

import os
import sys
import customtkinter as ctk
from tkinter import filedialog, messagebox
from datetime import datetime, timedelta
import hashlib
import uuid
import socket
import platform
import webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config.settings import COLORS, PERMISOS, MAX_OPERARIOS, PLANES, RESOURCE_DIR, APP_VERSION
from modules.database import db
from modules.pampa_client import PampaClient
from modules.i18n import t, set_language, get_language, SUPPORTED_LANGUAGES, LANGUAGE_NAMES
from modules.sorteo import SorteoAnimacion, SorteoPorMesaAnimacion

# Cargar preferencia de tema antes de crear la ventana
def _load_theme():
    return "dark"  # Solo modo oscuro

ctk.set_appearance_mode(_load_theme())
ctk.set_default_color_theme("blue")


class WelcomeXApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("WelcomeX - Sistema de Gestión de Eventos")

        # Adaptar tamaño a la resolución de pantalla
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        # Usar 90% de la pantalla sin mínimos fijos — se adapta a cualquier resolución
        width = min(1400, int(screen_width * 0.90))
        height = min(900, int(screen_height * 0.90))

        x = (screen_width - width) // 2
        y = (screen_height - height) // 2

        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(width, height)  # Mínimo = lo que calculamos, nunca mayor a la pantalla

        # Icono de la ventana
        try:
            icon_path = os.path.join(RESOURCE_DIR, "assets", "icon.ico")
            self.iconbitmap(icon_path)
        except Exception as e:
            print(f"[INFO] No se pudo cargar el icono: {e}")

        # Estado
        self.usuario_actual = None
        self.evento_activo = None

        # Machine ID único para restricciones de demo
        self.machine_id = self._generar_machine_id()

        # Cargar idioma guardado
        saved_lang = db.get_config("language")
        if saved_lang and saved_lang in SUPPORTED_LANGUAGES:
            set_language(saved_lang)

        # PAMPA Client - Servidor de Licencias
        self.pampa = PampaClient("WELCOME_X", "https://pampaguazu.com.ar")

        # Info de actualización pendiente (se chequea en background)
        self.update_info = None

        # Verificar licencia o trial demo
        license_status = self.verificar_licencia_startup()

        if license_status == "valid":
            # Verificar integridad del reloj al inicio
            self.after(3000, self._verificar_reloj_startup)
            # Licencia válida → Login normal
            self.mostrar_login()
        elif license_status == "demo_active":
            # Trial demo activo → Login con usuario demo
            self.mostrar_login_demo()
        elif license_status == "requires_connection":
            # Requiere conexión a internet (offline >48h o migración)
            self.mostrar_requiere_conexion()
        elif license_status == "hardware_replaced":
            # Licencia fue activada en otra PC
            self.mostrar_hardware_reemplazado()
        else:
            # Sin licencia ni trial → Mostrar opciones
            self.mostrar_opciones_inicio()

        # Chequear actualizaciones en background (no bloquea el inicio)
        self.after(2000, self._check_for_updates)
    
    # ============================================
    # VERIFICACIÓN DE RELOJ
    # ============================================

    def _verificar_reloj_startup(self):
        """Verifica integridad del reloj del sistema al iniciar"""
        import threading
        def _check():
            try:
                result = self.pampa.check_time_integrity()
                if not result["ok"]:
                    self.after(0, lambda: self._mostrar_advertencia_reloj(
                        result["warning"]
                    ))
            except Exception as e:
                print(f"[WelcomeX] Error verificando reloj: {e}")
        threading.Thread(target=_check, daemon=True).start()

    def _mostrar_advertencia_reloj(self, warning: str):
        """Muestra advertencia de manipulación de reloj"""
        d = ctk.CTkToplevel(self)
        d.title("Advertencia de Reloj")
        d.geometry("550x300")
        d.transient(self)
        d.grab_set()

        x = (d.winfo_screenwidth() - 550) // 2
        y = (d.winfo_screenheight() - 300) // 2
        d.geometry(f"+{x}+{y}")

        frame = ctk.CTkFrame(d, fg_color=COLORS["card"])
        frame.pack(expand=True, fill="both", padx=20, pady=20)

        ctk.CTkLabel(frame, text="⚠️ Advertencia de Reloj",
                    font=("Arial", 22, "bold"),
                    text_color=COLORS["warning"]).pack(pady=(10, 15))

        ctk.CTkLabel(frame, text=warning,
                    font=("Arial", 13), text_color=COLORS["text_light"],
                    wraplength=450, justify="center").pack(pady=(0, 10))

        ctk.CTkLabel(frame,
                    text="Ajusta el reloj de tu sistema a la hora correcta.\n"
                         "El uso con reloj incorrecto quedará registrado.",
                    font=("Arial", 12), text_color=COLORS["text_light"],
                    wraplength=450, justify="center").pack(pady=(0, 20))

        ctk.CTkButton(frame, text="Entendido", command=d.destroy,
                     height=45, width=180, font=("Arial", 14)).pack()

    # ============================================
    # ACTUALIZACIONES
    # ============================================

    def _check_for_updates(self):
        """Chequea si hay una versión nueva y auto-actualiza"""
        import threading
        def _check():
            update = self.pampa.check_for_updates(APP_VERSION)
            if update:
                self.update_info = update
                self.after(0, self._auto_update)
        threading.Thread(target=_check, daemon=True).start()

    def _auto_update(self):
        """Muestra notificación y lanza la descarga automáticamente"""
        if not self.update_info:
            return
        version = self.update_info["latest_version"]
        download_url = self.update_info.get("download_url", "")
        if not download_url:
            return
        self.after(800, lambda: self._start_download(version, download_url))

    def _start_download(self, version, download_url):
        """Ventana prominente de actualización con progreso en tiempo real"""
        import threading, tempfile, os

        self._update_win = ctk.CTkToplevel(self)
        self._update_win.title(f"Actualizando WelcomeX a v{version}")
        self._update_win.geometry("520x440")
        self._update_win.resizable(False, False)
        self._update_win.transient(self)
        self._update_win.attributes('-topmost', True)   # Siempre al frente
        self._update_win.protocol("WM_DELETE_WINDOW", lambda: None)  # No se puede cerrar

        x = (self._update_win.winfo_screenwidth() - 520) // 2
        y = (self._update_win.winfo_screenheight() - 440) // 2
        self._update_win.geometry(f"+{x}+{y}")
        self._update_win.lift()
        self._update_win.focus_force()

        frame = ctk.CTkFrame(self._update_win, fg_color=COLORS["card"])
        frame.pack(expand=True, fill="both", padx=24, pady=24)

        # Título
        ctk.CTkLabel(frame, text="⬆️  Actualización disponible",
                    font=("Segoe UI", 19, "bold"),
                    text_color=COLORS["gold"]).pack(pady=(10, 4))
        ctk.CTkLabel(frame, text=f"Instalando versión {version}",
                    font=("Segoe UI", 13),
                    text_color=COLORS["text_light"]).pack(pady=(0, 18))

        # Pasos
        steps_data = [
            ("✅", "Nueva versión detectada",      COLORS["text"]),
            ("🔄", "Descargando actualización...", COLORS["gold"]),
            ("⏳", "Instalando",                   COLORS["text_light"]),
            ("⏳", "Reiniciando WelcomeX",          COLORS["text_light"]),
        ]
        self._step_icons  = []
        self._step_labels = []
        steps_frame = ctk.CTkFrame(frame, fg_color=COLORS["bg"], corner_radius=8)
        steps_frame.pack(fill="x", padx=4, pady=(0, 16))

        for icon, text, color in steps_data:
            row = ctk.CTkFrame(steps_frame, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=6)
            icon_lbl = ctk.CTkLabel(row, text=icon, font=("Segoe UI", 16), width=28)
            icon_lbl.pack(side="left")
            text_lbl = ctk.CTkLabel(row, text=text, font=("Segoe UI", 13),
                                   text_color=color, anchor="w")
            text_lbl.pack(side="left", padx=(10, 0))
            self._step_icons.append(icon_lbl)
            self._step_labels.append(text_lbl)

        # Barra de progreso
        self._update_progress = ctk.CTkProgressBar(frame, height=14,
                    progress_color=COLORS["gold"], corner_radius=7)
        self._update_progress.pack(fill="x", padx=4, pady=(0, 6))
        self._update_progress.set(0)

        # Texto de progreso detallado
        self._update_detail = ctk.CTkLabel(frame, text="Iniciando descarga...",
                    font=("Segoe UI", 12), text_color=COLORS["text_light"])
        self._update_detail.pack(pady=(0, 10))

        # Advertencia
        warn_frame = ctk.CTkFrame(frame, fg_color="#2d1b00", corner_radius=8)
        warn_frame.pack(fill="x", padx=4, pady=(4, 0))
        ctk.CTkLabel(warn_frame, text="⚠️  No cierres la aplicación durante la actualización",
                    font=("Segoe UI", 11), text_color="#f59e0b").pack(pady=8)

        # Forzar render: withdraw+deiconify obliga a Windows a repintar todo el contenido
        self._update_win.update_idletasks()
        self._update_win.withdraw()
        self._update_win.deiconify()
        self._update_win.update()

        # Iniciar descarga con delay para que el render termine antes del hilo
        dest = os.path.join(tempfile.gettempdir(), "WelcomeX_Setup.exe")

        def _progress(pct, downloaded, total):
            self.after(0, lambda p=pct, d=downloaded, t=total:
                       self._update_set_progress(p, d, t))

        def _download():
            ok = self.pampa.download_update(download_url, dest, progress_callback=_progress)
            self.after(0, lambda: self._update_finished(ok, dest))

        self._update_win.after(400, lambda: threading.Thread(target=_download, daemon=True).start())

    def _update_set_progress(self, pct, downloaded, total):
        """Actualiza barra de progreso con MB descargados"""
        if not hasattr(self, '_update_win') or not self._update_win.winfo_exists():
            return
        self._update_progress.set(pct)
        mb_down  = downloaded / 1_048_576
        mb_total = total      / 1_048_576
        pct_int  = int(pct * 100)
        if mb_total > 0:
            self._update_detail.configure(
                text=f"Descargando...  {mb_down:.1f} MB / {mb_total:.1f} MB  ({pct_int}%)"
            )
        else:
            self._update_detail.configure(text=f"Descargando... {pct_int}%")

    def _update_finished(self, ok, installer_path):
        """Descarga finalizada: actualiza pasos y lanza el instalador"""
        if not hasattr(self, '_update_win') or not self._update_win.winfo_exists():
            return
        if ok:
            self._update_progress.set(1)
            self._update_detail.configure(text="Descarga completa ✅")

            self._step_icons[1].configure(text="✅")
            self._step_labels[1].configure(text="Descarga completa", text_color=COLORS["text"])

            # Paso 3: instalando (barra animada)
            self._step_icons[2].configure(text="🔄")
            self._step_labels[2].configure(text="Instalando...", text_color=COLORS["gold"])

            self._anim_val = 0.0
            self._anim_dir = 1
            def _animar():
                if not self._update_win.winfo_exists():
                    return
                self._anim_val += 0.025 * self._anim_dir
                if self._anim_val >= 1.0:
                    self._anim_dir = -1
                elif self._anim_val <= 0.0:
                    self._anim_dir = 1
                self._update_progress.set(self._anim_val)
                self._update_win.after(30, _animar)
            _animar()

            def _pre_restart():
                if not self._update_win.winfo_exists():
                    return
                self._step_icons[2].configure(text="✅")
                self._step_labels[2].configure(text="Instalación lista", text_color=COLORS["text"])
                self._step_icons[3].configure(text="🔄")
                self._step_labels[3].configure(text="Reiniciando WelcomeX...", text_color=COLORS["gold"])
                self._update_detail.configure(text="La aplicación se cerrará y reabrirá automáticamente")
                self.after(1500, lambda: self._launch_installer(installer_path))

            self.after(2200, _pre_restart)
        else:
            self._step_icons[1].configure(text="❌")
            self._step_labels[1].configure(
                text="Error al descargar. Se reintentará al próximo inicio.",
                text_color="#ef4444")
            self._update_progress.configure(progress_color="#ef4444")
            self._update_detail.configure(
                text="Verificá tu conexión a internet.", text_color="#ef4444")
            self.after(4000, lambda: self._update_win.destroy())

    def _launch_installer(self, installer_path):
        """Ejecuta el instalador en modo silencioso, luego relanza WelcomeX automáticamente"""
        import subprocess, sys
        exe_path = sys.executable
        try:
            cmd = f'cmd /c "{installer_path}" /SILENT /CLOSEAPPLICATIONS && start "" "{exe_path}"'
            subprocess.Popen(cmd, shell=True,
                           creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)
        except Exception:
            subprocess.Popen([installer_path])
        sys.exit(0)

    def mostrar_ventana_updates(self):
        """Ventana visual con historial completo de actualizaciones"""
        import threading

        d = ctk.CTkToplevel(self)
        d.title(t("update.window_title"))
        d.geometry("600x700")
        d.transient(self)
        d.grab_set()

        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() - 600) // 2
        y = (d.winfo_screenheight() - 700) // 2
        d.geometry(f"+{x}+{y}")

        # Header
        header = ctk.CTkFrame(d, fg_color=COLORS["sidebar"], corner_radius=0, height=80)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text=t("update.window_title"),
            font=("Segoe UI", 22, "bold"),
            text_color="#d4af37"
        ).pack(side="left", padx=25, pady=20)

        ctk.CTkLabel(
            header,
            text=f"{t('update.current_version')}: v{APP_VERSION}",
            font=("Segoe UI", 13),
            text_color=COLORS["text_light"]
        ).pack(side="right", padx=25, pady=20)

        # Contenido scrollable
        scroll = ctk.CTkScrollableFrame(d, fg_color=COLORS["bg"])
        scroll.pack(expand=True, fill="both", padx=0, pady=0)

        # Mostrar "Cargando..."
        loading_label = ctk.CTkLabel(
            scroll,
            text=t("update.loading"),
            font=("Segoe UI", 14),
            text_color=COLORS["text_light"]
        )
        loading_label.pack(pady=40)

        # Cargar changelog en background
        def _fetch_changelog():
            try:
                import requests
                resp = requests.get(
                    f"{self.pampa.api_url}/api/v1/version/WELCOME_X",
                    timeout=5
                )
                if resp.status_code == 200:
                    data = resp.json()
                    full_changelog = data.get("full_changelog", [])
                    d.after(0, lambda: _render_changelog(full_changelog))
                else:
                    d.after(0, lambda: _render_error())
            except:
                d.after(0, lambda: _render_error())

        def _render_error():
            loading_label.configure(text=t("update.error_loading"))

        def _render_changelog(changelog):
            loading_label.destroy()
            lang = get_language()

            type_labels = {
                "release": {"text": t("update.type_release"), "color": "#10b981"},
                "update": {"text": t("update.type_update"), "color": "#3b82f6"},
                "fix": {"text": t("update.type_fix"), "color": "#f59e0b"},
            }

            for i, entry in enumerate(changelog):
                ver = entry.get("version", "?")
                date = entry.get("date", "")
                entry_type = entry.get("type", "update")
                changes = entry.get("changes", {})
                items = changes.get(lang, changes.get("es", []))

                is_current = (ver == APP_VERSION)
                is_latest = (i == 0)

                # Card por versión
                card = ctk.CTkFrame(scroll, fg_color=COLORS["card"], corner_radius=12)
                card.pack(fill="x", padx=15, pady=(10 if i > 0 else 15, 5))

                # Header del card: versión + badge + fecha
                card_header = ctk.CTkFrame(card, fg_color="transparent")
                card_header.pack(fill="x", padx=20, pady=(15, 5))

                ver_text = f"v{ver}"
                ctk.CTkLabel(
                    card_header,
                    text=ver_text,
                    font=("Segoe UI", 18, "bold"),
                    text_color="#d4af37" if is_latest else COLORS["text"]
                ).pack(side="left")

                # Badge de tipo
                tipo_info = type_labels.get(entry_type, type_labels["update"])
                badge = ctk.CTkLabel(
                    card_header,
                    text=f"  {tipo_info['text']}  ",
                    font=("Segoe UI", 11, "bold"),
                    fg_color=tipo_info["color"],
                    corner_radius=6,
                    text_color="white"
                )
                badge.pack(side="left", padx=10)

                # Badge "instalada" si es la versión actual
                if is_current:
                    installed_badge = ctk.CTkLabel(
                        card_header,
                        text=f"  {t('update.installed')}  ",
                        font=("Segoe UI", 11, "bold"),
                        fg_color="#6b7280",
                        corner_radius=6,
                        text_color="white"
                    )
                    installed_badge.pack(side="left", padx=5)

                # Fecha
                if date:
                    ctk.CTkLabel(
                        card_header,
                        text=date,
                        font=("Segoe UI", 12),
                        text_color=COLORS["text_light"]
                    ).pack(side="right")

                # Lista de cambios
                changes_frame = ctk.CTkFrame(card, fg_color="transparent")
                changes_frame.pack(fill="x", padx=20, pady=(5, 15))

                for item in items:
                    item_frame = ctk.CTkFrame(changes_frame, fg_color="transparent")
                    item_frame.pack(fill="x", pady=2)

                    ctk.CTkLabel(
                        item_frame,
                        text="  •",
                        font=("Segoe UI", 13),
                        text_color="#d4af37",
                        width=25
                    ).pack(side="left", anchor="n")

                    ctk.CTkLabel(
                        item_frame,
                        text=item,
                        font=("Segoe UI", 13),
                        text_color=COLORS["text"],
                        anchor="w",
                        wraplength=480
                    ).pack(side="left", fill="x", expand=True)

                # Botón descargar si hay versión nueva
                if is_latest and not is_current and self.update_info:
                    btn_frame = ctk.CTkFrame(card, fg_color="transparent")
                    btn_frame.pack(fill="x", padx=20, pady=(0, 15))

                    dl_url = self.update_info.get("download_url", "")
                    ctk.CTkButton(
                        btn_frame,
                        text=f"{t('update.download_btn')} v{ver}",
                        height=36,
                        fg_color="#10b981", hover_color="#059669",
                        font=("Segoe UI", 13, "bold"),
                        command=lambda url=dl_url: webbrowser.open(url)
                    ).pack(fill="x")

            # Padding final
            ctk.CTkLabel(scroll, text="", height=10).pack()

        threading.Thread(target=_fetch_changelog, daemon=True).start()

        # Footer con botones
        btn_frame = ctk.CTkFrame(d, fg_color=COLORS["sidebar"], height=70, corner_radius=0)
        btn_frame.pack(fill="x", side="bottom")
        btn_frame.pack_propagate(False)

        inner_btn = ctk.CTkFrame(btn_frame, fg_color="transparent")
        inner_btn.pack(expand=True)

        # Botón verificar actualizaciones
        check_btn = ctk.CTkButton(
            inner_btn,
            text="🔍 Verificar actualizaciones",
            width=220, height=40,
            fg_color=COLORS["primary"],
            hover_color="#2563eb",
            font=("Segoe UI", 13, "bold"),
        )
        check_btn.pack(side="left", padx=(0, 12), pady=15)

        status_lbl = ctk.CTkLabel(
            inner_btn,
            text="",
            font=("Segoe UI", 12),
            text_color=COLORS["text_light"],
            width=180
        )
        status_lbl.pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            inner_btn,
            text=t("common.close"),
            width=110, height=40,
            fg_color=COLORS["border"],
            hover_color=COLORS["hover"],
            command=d.destroy
        ).pack(side="left", pady=15)

        def _verificar_ahora():
            check_btn.configure(state="disabled", text="⏳ Verificando...")
            status_lbl.configure(text="", text_color=COLORS["text_light"])

            def _check():
                from config.settings import APP_VERSION as _ver
                update = self.pampa.check_for_updates(_ver)
                d.after(0, lambda: _mostrar_resultado(update))

            def _mostrar_resultado(update):
                check_btn.configure(state="normal", text="🔍 Verificar actualizaciones")
                if update:
                    latest = update.get("latest_version", "?")
                    status_lbl.configure(
                        text=f"⬆️ v{latest} disponible — descargando...",
                        text_color="#10b981"
                    )
                    self.update_info = update
                    # Lanzar auto-update (descarga silenciosa)
                    d.after(1500, lambda: (d.destroy(), self._auto_update()))
                else:
                    status_lbl.configure(
                        text="✅ Ya tenés la última versión",
                        text_color="#10b981"
                    )

            threading.Thread(target=_check, daemon=True).start()

        check_btn.configure(command=_verificar_ahora)

    # ============================================
    # UTILIDADES
    # ============================================

    def _generar_machine_id(self):
        """Genera un ID único basado en hardware de la máquina"""
        try:
            # Combinar: hostname + usuario del sistema + MAC address aproximado
            hostname = socket.gethostname()
            username = os.getenv('USERNAME', os.getenv('USER', 'unknown'))
            system_info = platform.node() + platform.machine()

            # Crear hash único
            raw_id = f"{hostname}-{username}-{system_info}"
            machine_id = hashlib.sha256(raw_id.encode()).hexdigest()[:32]
            return machine_id
        except:
            # Fallback: usar UUID guardado en config
            stored_id = db.get_config("machine_uuid")
            if not stored_id:
                stored_id = str(uuid.uuid4())[:32]
                db.set_config("machine_uuid", stored_id)
            return stored_id

    def _get_demo_marker_path(self):
        """Obtiene la ruta del archivo oculto de demo en AppData"""
        appdata = os.getenv('LOCALAPPDATA', os.path.expanduser('~'))
        marker_dir = os.path.join(appdata, '.welcomex')
        os.makedirs(marker_dir, exist_ok=True)
        return os.path.join(marker_dir, f'.demo_{self.machine_id[:16]}')

    def _demo_registrada_persistente(self):
        """Verifica si hay un registro persistente de demo (sobrevive borrado de DB)"""
        import json
        marker_path = self._get_demo_marker_path()
        if not os.path.exists(marker_path):
            return None
        try:
            with open(marker_path, 'r') as f:
                data = json.load(f)
            return data
        except:
            return None

    def _guardar_demo_persistente(self):
        """Guarda registro persistente de demo fuera de la DB"""
        import json
        marker_path = self._get_demo_marker_path()
        data = {
            'machine_id': self.machine_id,
            'started': datetime.now().isoformat(),
            'hostname': socket.gethostname()
        }
        try:
            with open(marker_path, 'w') as f:
                json.dump(data, f)
            # Ocultar archivo en Windows
            if sys.platform == 'win32':
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(marker_path, 0x02)
        except:
            pass

    def _demo_expirada_persistente(self):
        """Verifica si la demo expiró usando el archivo persistente"""
        data = self._demo_registrada_persistente()
        if not data:
            return False
        try:
            fecha_inicio = datetime.fromisoformat(data['started'])
            return datetime.now() > fecha_inicio + timedelta(days=7)
        except:
            return False

    def cambiar_idioma(self, lang):
        """Cambia el idioma y recarga la pantalla actual"""
        set_language(lang)
        db.set_config("language", lang)

        # Recargar pantalla actual
        if self.usuario_actual:
            self.mostrar_principal()
        else:
            # Estamos en login u opciones inicio
            self.mostrar_login()

    def mostrar_selector_idioma(self, parent):
        """Agrega selector de idioma a un frame"""
        lang_frame = ctk.CTkFrame(parent, fg_color="transparent")
        lang_frame.pack(pady=(10, 0))

        current = get_language()
        for code in SUPPORTED_LANGUAGES:
            fg = COLORS["primary"] if code == current else "transparent"
            border = COLORS["primary"] if code == current else COLORS["border"]
            ctk.CTkButton(
                lang_frame,
                text=LANGUAGE_NAMES[code],
                width=90, height=32,
                font=("Arial", 12),
                fg_color=fg,
                border_width=1,
                border_color=border,
                hover_color=COLORS.get("hover", "#333"),
                command=lambda c=code: self.cambiar_idioma(c)
            ).pack(side="left", padx=3)

    def tiene_permiso(self, permiso):
        """Verificar permisos del usuario"""
        if not self.usuario_actual:
            return False

        rol = self.usuario_actual.get('rol', 'operario')

        # Super admin siempre tiene todo
        if rol == 'super_admin':
            return True

        # 'cliente' o 'client' tienen los mismos permisos que 'admin'
        if rol in ('cliente', 'client'):
            rol = 'admin'

        # Verificar en matriz de permisos
        return PERMISOS.get(rol, {}).get(permiso, False)
    
    def es_modo_demo(self):
        """Verificar si está en modo demo"""
        return self.usuario_actual and self.usuario_actual.get('es_demo', False)
    
    def validar_accion_escritura(self, nombre_accion="esta acción"):
        """Validar si puede hacer acciones de escritura (bloquea modo demo excepto acciones demo)"""
        if self.es_modo_demo():
            # Acciones PERMITIDAS en modo demo (para probar el sistema)
            acciones_permitidas_demo = [
                "iniciar eventos",
                "pausar eventos",
                "finalizar eventos",
                "realizar sorteos",
                # Kiosco acredita/desacredita (permitido)
            ]

            if nombre_accion in acciones_permitidas_demo:
                return True

            # Caso especial: generar invitaciones permitido hasta 3 VECES por máquina
            if nombre_accion == "generar invitaciones":
                restantes = db.demo_invitaciones_restantes(self.machine_id)
                if restantes > 0:
                    # Incrementar contador
                    db.incrementar_demo_invitaciones(self.machine_id)
                    restantes -= 1
                    self.mostrar_mensaje(f"🎨 {t('demo.demo_title')}",
                                        t("demo.invitations_allowed_count", remaining=restantes),
                                        "info")
                    return True
                else:
                    self.mostrar_mensaje(f"🎭 {t('demo.mode_label')}",
                                        t("demo.invitations_used"),
                                        "warning")
                    return False

            # Resto de acciones BLOQUEADAS (crear, editar, eliminar, exportar)
            self.mostrar_mensaje(f"🎭 {t('demo.mode_label')}",
                                t("demo.blocked_action", action=nombre_accion),
                                "warning")
            return False
        return True
    
    def limpiar_ventana(self):
        """Limpiar toda la ventana"""
        for widget in self.winfo_children():
            widget.destroy()
    
    def mostrar_mensaje(self, titulo, mensaje, tipo="info"):
        """Mostrar mensaje en ventana emergente"""
        d = ctk.CTkToplevel(self)
        d.title(titulo)
        d.geometry("450x280")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 225
        y = (d.winfo_screenheight() // 2) - 140
        d.geometry(f"450x280+{x}+{y}")
        
        icon = "✅" if tipo == "success" else "❌" if tipo == "error" else "ℹ️" if tipo == "info" else "⚠️"
        
        ctk.CTkLabel(d, text=icon, font=("Arial", 50)).pack(pady=(30, 10))
        ctk.CTkLabel(d, text=titulo, font=("Arial", 20, "bold")).pack(pady=5)
        ctk.CTkLabel(d, text=mensaje, wraplength=380, font=("Arial", 13), 
                    justify="center").pack(pady=20)
        ctk.CTkButton(d, text="OK", command=d.destroy, width=140, height=45,
                     font=("Arial", 14)).pack(pady=15)
    
    # ============================================
    # LOGIN
    # ============================================
    
    
    def gestionar_usuarios(self):
        """Gestión de usuarios (solo super admin)"""
        if self.usuario_actual['rol'] != 'super_admin':
            self.mostrar_mensaje("Acceso Denegado", "Solo Super Admin puede gestionar usuarios", "error")
            return
        
        for w in self.content.winfo_children():
            w.destroy()
        
        # Header
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", pady=(0, 25))
        
        ctk.CTkButton(header, text="← Atrás", command=self.mostrar_eventos,
                     width=110, height=45, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"],
                     font=("Arial", 14)).pack(side="left")

        ctk.CTkButton(header, text="➕ Nuevo Usuario", command=self.crear_usuario_dialog,
                     height=45, width=160, fg_color=COLORS["success"],
                     font=("Arial", 14)).pack(side="right")

        ctk.CTkLabel(header, text="👥 Gestión de Usuarios",
                    font=("Arial", 30, "bold")).pack(side="left", padx=25)
        
        # Obtener usuarios
        usuarios = db.obtener_todos_usuarios()
        
        if not usuarios:
            ctk.CTkLabel(self.content, text="No hay usuarios registrados", 
                        font=("Arial", 17), text_color=COLORS["text_light"]).pack(expand=True, pady=80)
            return
        
        # Stats
        stats_frame = ctk.CTkFrame(self.content, fg_color=COLORS["card"], corner_radius=10)
        stats_frame.pack(fill="x", pady=(0, 20))
        
        stats_inner = ctk.CTkFrame(stats_frame, fg_color="transparent")
        stats_inner.pack(fill="x", padx=25, pady=18)
        
        ctk.CTkLabel(stats_inner, text=f"Total: {len(usuarios)} usuarios",
                    font=("Arial", 15, "bold")).pack(side="left")
        
        activos = len([u for u in usuarios if u.get('activo')])
        ctk.CTkLabel(stats_inner, text=f"✅ Activos: {activos}",
                    font=("Arial", 15), text_color=COLORS["success"]).pack(side="left", padx=25)
        
        # Lista de usuarios
        for usuario in usuarios:
            self.crear_card_usuario(usuario)
    
    def crear_card_usuario(self, usuario):
        """Card de usuario"""
        card = ctk.CTkFrame(self.content, fg_color=COLORS["card"], corner_radius=8)
        card.pack(fill="x", pady=4)
        
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=14)
        
        nombre_completo = f"{usuario['nombre']} {usuario.get('apellido', '')}"
        ctk.CTkLabel(inner, text=nombre_completo, font=("Arial", 16, "bold")).pack(side="left")
        
        rol_texto = usuario['rol'].replace('_', ' ').title()
        ctk.CTkLabel(inner, text=f"• {rol_texto}", font=("Arial", 14),
                    text_color=COLORS["text_light"]).pack(side="left", padx=15)
        
        ctk.CTkLabel(inner, text=f"📧 {usuario['email']}", font=("Arial", 13),
                    text_color=COLORS["text_light"]).pack(side="left", padx=10)
        
        if not usuario.get('activo'):
            ctk.CTkLabel(inner, text="❌ Inactivo", font=("Arial", 12),
                        text_color=COLORS["error"]).pack(side="left", padx=10)
        
        # Botones (solo si no es el usuario actual)
        if usuario['id'] != self.usuario_actual['id']:
            btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
            btn_frame.pack(side="right")
            
            if usuario.get('activo'):
                ctk.CTkButton(btn_frame, text="❌ Desactivar",
                            command=lambda u=usuario: self.desactivar_usuario(u),
                            width=120, height=35, fg_color=COLORS["warning"],
                            font=("Arial", 12)).pack(side="left", padx=5)
            else:
                ctk.CTkButton(btn_frame, text="✅ Activar",
                            command=lambda u=usuario: self.activar_usuario(u),
                            width=120, height=35, fg_color=COLORS["success"],
                            font=("Arial", 12)).pack(side="left", padx=5)
            
            ctk.CTkButton(btn_frame, text="🔑 Cambiar Contraseña",
                        command=lambda u=usuario: self.cambiar_password_usuario(u),
                        width=150, height=35, fg_color=COLORS["primary"],
                        font=("Arial", 12)).pack(side="left", padx=5)

            ctk.CTkButton(btn_frame, text="📨 Código Recuperación",
                        command=lambda u=usuario: self.generar_codigo_recuperacion_manual(u),
                        width=180, height=35, fg_color=COLORS["warning"],
                        font=("Arial", 12)).pack(side="left", padx=5)
    
    def crear_usuario_dialog(self):
        """Diálogo crear usuario"""
        d = ctk.CTkToplevel(self)
        d.title("Nuevo Usuario")
        d.geometry("500x600")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 250
        y = (d.winfo_screenheight() // 2) - 300
        d.geometry(f"500x600+{x}+{y}")
        
        scroll = ctk.CTkScrollableFrame(d, fg_color=COLORS["bg"])
        scroll.pack(fill="both", expand=True, padx=30, pady=30)
        
        ctk.CTkLabel(scroll, text="Crear Usuario", font=("Arial", 24, "bold")).pack(pady=(0, 25))
        
        # Email
        ctk.CTkLabel(scroll, text="Email *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_email = ctk.CTkEntry(scroll, height=45, font=("Arial", 14))
        e_email.pack(fill="x", pady=(8, 12))
        
        # Password
        ctk.CTkLabel(scroll, text="Contraseña *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_password = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), show="*")
        e_password.pack(fill="x", pady=(8, 12))
        
        # Nombre
        ctk.CTkLabel(scroll, text="Nombre *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_nombre = ctk.CTkEntry(scroll, height=45, font=("Arial", 14))
        e_nombre.pack(fill="x", pady=(8, 12))
        
        # Apellido
        ctk.CTkLabel(scroll, text="Apellido", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_apellido = ctk.CTkEntry(scroll, height=45, font=("Arial", 14))
        e_apellido.pack(fill="x", pady=(8, 12))
        
        # Teléfono
        ctk.CTkLabel(scroll, text="Teléfono", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_telefono = ctk.CTkEntry(scroll, height=45, font=("Arial", 14))
        e_telefono.pack(fill="x", pady=(8, 12))
        
        # Rol
        ctk.CTkLabel(scroll, text="Rol *", anchor="w", font=("Arial", 13)).pack(fill="x", pady=(10, 5))
        rol_var = ctk.StringVar(value="admin")
        
        ctk.CTkRadioButton(scroll, text="Admin (gestiona eventos)", variable=rol_var, value="admin",
                          font=("Arial", 13)).pack(anchor="w", padx=20, pady=5)
        ctk.CTkRadioButton(scroll, text="Operario (solo kiosco)", variable=rol_var, value="operario",
                          font=("Arial", 13)).pack(anchor="w", padx=20, pady=5)
        
        def guardar():
            email = e_email.get().strip()
            password = e_password.get().strip()
            nombre = e_nombre.get().strip()
            
            if not email or not password or not nombre:
                self.mostrar_mensaje("Error", "Email, contraseña y nombre son obligatorios", "error")
                return
            
            resultado = db.crear_usuario(
                email=email,
                password=password,
                nombre=nombre,
                apellido=e_apellido.get().strip() or None,
                telefono=e_telefono.get().strip() or None,
                rol=rol_var.get(),
                admin_id=self.usuario_actual['id']
            )
            
            if resultado['success']:
                d.destroy()
                self.mostrar_mensaje("Éxito", f"Usuario '{nombre}' creado", "success")
                self.gestionar_usuarios()
            else:
                self.mostrar_mensaje("Error", resultado['error'], "error")
        
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=20)
        
        ctk.CTkButton(btn_frame, text="💾 Crear Usuario", command=guardar,
                     height=55, font=("Arial", 16, "bold"),
                     fg_color=COLORS["success"]).pack(fill="x", pady=(0, 10))
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=d.destroy,
                     height=50, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"]).pack(fill="x")
    
    def desactivar_usuario(self, usuario):
        """Desactivar usuario"""
        resultado = db.desactivar_usuario(usuario['id'])
        if resultado['success']:
            self.mostrar_mensaje("Éxito", f"Usuario '{usuario['nombre']}' desactivado", "success")
            self.gestionar_usuarios()
        else:
            self.mostrar_mensaje("Error", resultado['error'], "error")
    
    def activar_usuario(self, usuario):
        """Activar usuario"""
        resultado = db.activar_usuario(usuario['id'])
        if resultado['success']:
            self.mostrar_mensaje("Éxito", f"Usuario '{usuario['nombre']}' activado", "success")
            self.gestionar_usuarios()
        else:
            self.mostrar_mensaje("Error", resultado['error'], "error")
    
    def cambiar_password_usuario(self, usuario):
        """Cambiar contraseña de usuario"""
        d = ctk.CTkToplevel(self)
        d.title("Cambiar Contraseña")
        d.geometry("450x300")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 225
        y = (d.winfo_screenheight() // 2) - 150
        d.geometry(f"450x300+{x}+{y}")
        
        container = ctk.CTkFrame(d, fg_color=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=30, pady=30)
        
        ctk.CTkLabel(container, text=f"Cambiar Contraseña", 
                    font=("Arial", 22, "bold")).pack(pady=(0, 10))
        
        ctk.CTkLabel(container, text=f"Usuario: {usuario['nombre']} {usuario.get('apellido', '')}", 
                    font=("Arial", 14), text_color=COLORS["text_light"]).pack(pady=(0, 25))
        
        ctk.CTkLabel(container, text="Nueva Contraseña:", anchor="w", 
                    font=("Arial", 13)).pack(fill="x")
        e_password = ctk.CTkEntry(container, height=45, font=("Arial", 14), show="*")
        e_password.pack(fill="x", pady=(8, 20))
        
        def guardar():
            password = e_password.get().strip()
            if not password:
                self.mostrar_mensaje("Error", "La contraseña no puede estar vacía", "error")
                return
            
            resultado = db.cambiar_password_usuario(usuario['id'], password)
            if resultado['success']:
                d.destroy()
                self.mostrar_mensaje("Éxito", "Contraseña actualizada", "success")
            else:
                self.mostrar_mensaje("Error", resultado['error'], "error")
        
        ctk.CTkButton(container, text="💾 Cambiar Contraseña", command=guardar,
                     height=50, font=("Arial", 15, "bold"),
                     fg_color=COLORS["primary"]).pack(fill="x", pady=(0, 10))
        
        ctk.CTkButton(container, text="Cancelar", command=d.destroy,
                     height=45, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"]).pack(fill="x")

    def generar_codigo_recuperacion_manual(self, usuario):
        """Generar código de recuperación manual para un usuario"""
        import random

        # Generar código de 6 dígitos
        codigo = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        expira = (datetime.now() + timedelta(hours=1)).isoformat()

        # Guardar en configuración temporal
        db.connect()
        try:
            db.cursor.execute('''
                INSERT OR REPLACE INTO configuracion (clave, valor)
                VALUES (?, ?)
            ''', (f'reset_code_{usuario["email"]}', f'{codigo}|{expira}'))
            db.connection.commit()

            # Mostrar código en diálogo
            d = ctk.CTkToplevel(self)
            d.title("Código de Recuperación Generado")
            d.geometry("550x450")
            d.transient(self)
            d.grab_set()

            # Centrar
            d.update_idletasks()
            x = (d.winfo_screenwidth() // 2) - 275
            y = (d.winfo_screenheight() // 2) - 225
            d.geometry(f"550x450+{x}+{y}")

            container = ctk.CTkFrame(d, fg_color=COLORS["bg"])
            container.pack(fill="both", expand=True, padx=40, pady=40)

            ctk.CTkLabel(container, text="✅ Código Generado",
                        font=("Arial", 28, "bold"), text_color=COLORS["success"]).pack(pady=(0, 20))

            # Info del usuario
            info_frame = ctk.CTkFrame(container, fg_color=COLORS["card"], corner_radius=10)
            info_frame.pack(fill="x", pady=20)
            info_inner = ctk.CTkFrame(info_frame, fg_color="transparent")
            info_inner.pack(padx=20, pady=15)

            ctk.CTkLabel(info_inner, text=f"Usuario: {usuario['nombre']} {usuario.get('apellido', '')}",
                        font=("Arial", 15, "bold")).pack(anchor="w")
            ctk.CTkLabel(info_inner, text=f"Email: {usuario['email']}",
                        font=("Arial", 14), text_color=COLORS["text_light"]).pack(anchor="w", pady=(5, 0))

            # Código
            ctk.CTkLabel(container, text="Código de Recuperación:",
                        font=("Arial", 16, "bold")).pack(pady=(10, 10))

            codigo_frame = ctk.CTkFrame(container, fg_color=COLORS["primary"], corner_radius=10)
            codigo_frame.pack(fill="x", pady=10)

            codigo_label = ctk.CTkLabel(codigo_frame, text=codigo,
                                        font=("Arial", 48, "bold"), text_color="white")
            codigo_label.pack(pady=25)

            # Instrucciones
            ctk.CTkLabel(container,
                        text="📋 Copia este código y envíaselo al cliente.\n"
                             "⏰ Válido por 1 hora.\n"
                             "🔐 El cliente podrá usarlo para restablecer su contraseña.",
                        font=("Arial", 13), text_color=COLORS["text_light"],
                        justify="left").pack(pady=20)

            # Botón copiar al portapapeles (usando tkinter nativo)
            def copiar_codigo():
                try:
                    self.clipboard_clear()
                    self.clipboard_append(codigo)
                    self.update()  # Necesario para que persista en el portapapeles
                    self.mostrar_mensaje("Éxito", "Código copiado al portapapeles", "success")
                except Exception as e:
                    self.mostrar_mensaje("Código",
                                        f"Código: {codigo}\n\nCopia manualmente este código.",
                                        "info")

            ctk.CTkButton(container, text="📋 Copiar Código", command=copiar_codigo,
                         width=450, height=50, font=("Arial", 15, "bold"),
                         fg_color=COLORS["success"]).pack(pady=(0, 10))

            ctk.CTkButton(container, text="Cerrar", command=d.destroy,
                         width=450, height=45, fg_color="transparent",
                         border_width=2, border_color=COLORS["border"]).pack()

        except Exception as e:
            self.mostrar_mensaje("Error", f"Error al generar código:\n{str(e)}", "error")
        finally:
            db.disconnect()

    # ============================================
    # CONFIGURACIÓN
    # ============================================

    def mostrar_configuracion(self):
        """Panel de configuración de la aplicación"""
        for w in self.content.winfo_children():
            w.destroy()

        # Header
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", pady=(0, 25))

        ctk.CTkButton(header, text=t("common.back"), command=self.mostrar_eventos,
                     width=110, height=45, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"],
                     font=("Arial", 14)).pack(side="left")

        ctk.CTkLabel(header, text=f"⚙️ {t('config.title')}",
                    font=("Arial", 30, "bold")).pack(side="left", padx=25)

        # ====================
        # 1. ESTADO DE LICENCIA
        # ====================
        licencia_card = ctk.CTkFrame(self.content, fg_color=COLORS["card"], corner_radius=10)
        licencia_card.pack(fill="x", pady=(0, 15))

        lic_inner = ctk.CTkFrame(licencia_card, fg_color="transparent")
        lic_inner.pack(fill="x", padx=25, pady=20)

        ctk.CTkLabel(lic_inner, text=f"🔐 {t('config.license_status')}",
                    font=("Arial", 20, "bold")).pack(anchor="w", pady=(0, 15))

        # Verificar licencia
        license_key = self.cargar_license_key()
        if license_key:
            result = self.pampa.validate_license(license_key, force_online=False)
            if result and result.get('valid'):
                dias = result.get('days_remaining') or 0
                expira = result.get('expires_at', 'N/A')

                # Calcular horas restantes si es menos de 1 día
                horas_restantes = None
                if expira and expira != 'N/A':
                    try:
                        diff = datetime.fromisoformat(expira) - datetime.now()
                        horas_restantes = max(0, int(diff.total_seconds() / 3600))
                    except:
                        pass

                # Formatear fecha de vencimiento (dd/mm/yyyy HH:MM)
                expira_display = 'N/A'
                if expira and expira != 'N/A':
                    try:
                        expira_display = datetime.fromisoformat(expira).strftime('%d/%m/%Y %H:%M') + ' hs'
                    except:
                        expira_display = expira[:16]

                # Color según días restantes
                if dias is not None and dias > 30:
                    color_estado = COLORS["success"]
                    icono = "✅"
                elif dias is not None and dias > 7:
                    color_estado = COLORS["warning"]
                    icono = "⚠️"
                else:
                    color_estado = COLORS["danger"]
                    icono = "⚠️"

                # Texto de tiempo restante
                if dias == 0 and horas_restantes is not None and horas_restantes > 0:
                    tiempo_restante = f"Vence en {horas_restantes} hora{'s' if horas_restantes != 1 else ''}"
                else:
                    tiempo_restante = t("config.days_remaining", days=dias)

                info_frame = ctk.CTkFrame(lic_inner, fg_color=COLORS["bg"], corner_radius=8)
                info_frame.pack(fill="x", pady=10)
                info_content = ctk.CTkFrame(info_frame, fg_color="transparent")
                info_content.pack(padx=15, pady=12)

                ctk.CTkLabel(info_content, text=f"{icono} {t('config.license_active')}",
                            font=("Arial", 16, "bold"), text_color=color_estado).pack(anchor="w")
                ctk.CTkLabel(info_content, text=tiempo_restante,
                            font=("Arial", 14), text_color=COLORS["text_light"]).pack(anchor="w", pady=(5, 0))
                ctk.CTkLabel(info_content, text=t("config.expires", date=expira_display),
                            font=("Arial", 14), text_color=COLORS["text_light"]).pack(anchor="w")

                # Botón renovar/extender
                ctk.CTkButton(lic_inner, text=f"🔄 {t('config.manage_subscription')}",
                            command=self.gestionar_suscripcion,
                            height=45, width=300, font=("Arial", 14, "bold"),
                            fg_color=COLORS["primary"]).pack(pady=(10, 0))

                # Botón liberar licencia (solo si está habilitado)
                allow_release = db.get_config("allow_self_release")
                if allow_release == "1":
                    ctk.CTkButton(lic_inner, text="🔓 Liberar licencia en este equipo",
                                command=self._liberar_licencia,
                                height=40, width=300, font=("Arial", 12),
                                fg_color="transparent", border_width=1,
                                border_color=COLORS["danger"],
                                text_color=COLORS["danger"],
                                hover_color=COLORS["danger"] + "20").pack(pady=(10, 0))
            else:
                ctk.CTkLabel(lic_inner, text=f"❌ {t('config.license_expired')}",
                            font=("Arial", 15), text_color=COLORS["danger"]).pack(anchor="w")
                ctk.CTkButton(lic_inner, text="🔑 Activar Licencia",
                            command=self.activar_licencia_dialog,
                            height=45, width=250, font=("Arial", 14, "bold"),
                            fg_color=COLORS["success"]).pack(pady=(10, 0))
        else:
            # Trial demo
            if self.verificar_trial_demo():
                db.connect()
                db.cursor.execute("SELECT valor FROM configuracion WHERE clave = 'demo_trial_inicio'")
                row = db.cursor.fetchone()
                if row:
                    fecha_inicio = datetime.fromisoformat(row['valor'])
                    dias_transcurridos = (datetime.now() - fecha_inicio).days
                    dias_restantes = 7 - dias_transcurridos

                    ctk.CTkLabel(lic_inner, text=f"🎮 Trial Demo Activo - {dias_restantes} días restantes",
                                font=("Arial", 15), text_color=COLORS["warning"]).pack(anchor="w")
                db.disconnect()

            ctk.CTkButton(lic_inner, text="🔑 Activar Licencia Completa",
                        command=self.activar_licencia_dialog,
                        height=45, width=280, font=("Arial", 14, "bold"),
                        fg_color=COLORS["success"]).pack(pady=(10, 0))

        # ====================
        # 1.5 SEGURIDAD (solo admin/super_admin)
        # ====================
        if self.tiene_permiso('editar_eventos'):
            seguridad_card = ctk.CTkFrame(self.content, fg_color=COLORS["card"], corner_radius=10)
            seguridad_card.pack(fill="x", pady=(0, 15))

            seg_inner = ctk.CTkFrame(seguridad_card, fg_color="transparent")
            seg_inner.pack(fill="x", padx=25, pady=20)

            ctk.CTkLabel(seg_inner, text="🛡️ Seguridad",
                        font=("Arial", 20, "bold")).pack(anchor="w", pady=(0, 15))

            # Toggle permitir autoliberación
            release_frame = ctk.CTkFrame(seg_inner, fg_color="transparent")
            release_frame.pack(fill="x", pady=5)

            ctk.CTkLabel(release_frame, text="Permitir liberar licencia desde este equipo:",
                        font=("Arial", 14)).pack(side="left")

            current_release = db.get_config("allow_self_release") == "1"

            release_switch = ctk.CTkSwitch(
                release_frame, text="",
                onvalue="1", offvalue="0",
                command=lambda: self._toggle_self_release(release_switch)
            )
            if current_release:
                release_switch.select()
            release_switch.pack(side="right", padx=10)

            ctk.CTkLabel(seg_inner,
                        text="Si está activado, podrás liberar la licencia de este equipo\n"
                             "para activarla en otro. Máximo 3 liberaciones por mes.",
                        font=("Arial", 11), text_color=COLORS["text_light"],
                        justify="left").pack(anchor="w", pady=(5, 0))

        # ====================
        # 3. RUTAS Y CARPETAS
        # ====================
        rutas_card = ctk.CTkFrame(self.content, fg_color=COLORS["card"], corner_radius=10)
        rutas_card.pack(fill="x", pady=15)

        rut_inner = ctk.CTkFrame(rutas_card, fg_color="transparent")
        rut_inner.pack(fill="x", padx=25, pady=20)

        ctk.CTkLabel(rut_inner, text=f"📁 {t('config.download_folder')}",
                    font=("Arial", 20, "bold")).pack(anchor="w", pady=(0, 15))

        # Carpeta de descargas
        db.connect()
        db.cursor.execute("SELECT valor FROM configuracion WHERE clave = 'ruta_descargas'")
        row = db.cursor.fetchone()
        ruta_actual = row['valor'] if row else os.path.join(os.path.expanduser("~"), "Downloads")
        db.disconnect()

        ruta_frame = ctk.CTkFrame(rut_inner, fg_color=COLORS["bg"], corner_radius=8)
        ruta_frame.pack(fill="x", pady=10)
        ruta_content = ctk.CTkFrame(ruta_frame, fg_color="transparent")
        ruta_content.pack(fill="x", padx=15, pady=12)

        ctk.CTkLabel(ruta_content, text=t("config.download_folder_label"),
                    font=("Arial", 14)).pack(anchor="w")
        ruta_label = ctk.CTkLabel(ruta_content, text=ruta_actual,
                                  font=("Arial", 13), text_color=COLORS["text_light"])
        ruta_label.pack(anchor="w", pady=(5, 0))

        def cambiar_ruta():
            from tkinter import filedialog
            nueva_ruta = filedialog.askdirectory(title="Seleccionar Carpeta de Descargas")
            if nueva_ruta:
                # Guardar
                db.connect()
                db.cursor.execute('''
                    INSERT OR REPLACE INTO configuracion (clave, valor)
                    VALUES ('ruta_descargas', ?)
                ''', (nueva_ruta,))
                db.connection.commit()
                db.disconnect()

                ruta_label.configure(text=nueva_ruta)
                self.mostrar_mensaje("Éxito", "Carpeta de descargas actualizada", "success")

        ctk.CTkButton(rut_inner, text=f"📂 {t('config.change_folder')}",
                     command=cambiar_ruta,
                     height=40, width=200, font=("Arial", 13),
                     fg_color=COLORS["primary"]).pack(pady=(10, 0))

        # ====================
        # 4. SEGURIDAD
        # ====================
        seguridad_card = ctk.CTkFrame(self.content, fg_color=COLORS["card"], corner_radius=10)
        seguridad_card.pack(fill="x", pady=15)

        seg_inner = ctk.CTkFrame(seguridad_card, fg_color="transparent")
        seg_inner.pack(fill="x", padx=25, pady=20)

        ctk.CTkLabel(seg_inner, text="🔒 Seguridad",
                    font=("Arial", 20, "bold")).pack(anchor="w", pady=(0, 15))

        # Cambiar contraseña
        ctk.CTkButton(seg_inner, text="🔑 Cambiar mi Contraseña",
                     command=self.cambiar_mi_password,
                     height=45, width=250, font=("Arial", 14, "bold"),
                     fg_color=COLORS["primary"]).pack(pady=5)

    def cambiar_mi_password(self):
        """Cambiar contraseña del usuario actual"""
        d = ctk.CTkToplevel(self)
        d.title("Cambiar Contraseña")
        d.geometry("500x450")
        d.transient(self)
        d.grab_set()

        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 250
        y = (d.winfo_screenheight() // 2) - 225
        d.geometry(f"500x450+{x}+{y}")

        container = ctk.CTkFrame(d, fg_color=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=35, pady=35)

        ctk.CTkLabel(container, text="🔑 Cambiar Contraseña",
                    font=("Arial", 24, "bold")).pack(pady=(0, 25))

        # Contraseña actual
        ctk.CTkLabel(container, text="Contraseña Actual:", anchor="w",
                    font=("Arial", 14)).pack(fill="x", pady=(0, 5))
        e_actual = ctk.CTkEntry(container, height=45, font=("Arial", 14), show="●")
        e_actual.pack(fill="x", pady=(0, 20))

        # Nueva contraseña
        ctk.CTkLabel(container, text="Nueva Contraseña:", anchor="w",
                    font=("Arial", 14)).pack(fill="x", pady=(0, 5))
        e_nueva = ctk.CTkEntry(container, height=45, font=("Arial", 14), show="●")
        e_nueva.pack(fill="x", pady=(0, 20))

        # Confirmar nueva
        ctk.CTkLabel(container, text="Confirmar Nueva Contraseña:", anchor="w",
                    font=("Arial", 14)).pack(fill="x", pady=(0, 5))
        e_confirmar = ctk.CTkEntry(container, height=45, font=("Arial", 14), show="●")
        e_confirmar.pack(fill="x", pady=(0, 25))

        def guardar():
            actual = e_actual.get().strip()
            nueva = e_nueva.get().strip()
            confirmar = e_confirmar.get().strip()

            if not actual or not nueva or not confirmar:
                self.mostrar_mensaje("Error", "Completa todos los campos", "error")
                return

            if nueva != confirmar:
                self.mostrar_mensaje("Error", "Las contraseñas nuevas no coinciden", "error")
                return

            if len(nueva) < 6:
                self.mostrar_mensaje("Error", "La contraseña debe tener al menos 6 caracteres", "error")
                return

            # Verificar contraseña actual
            import hashlib
            password_hash = hashlib.sha256(actual.encode()).hexdigest()

            db.connect()
            try:
                db.cursor.execute('SELECT password FROM usuarios WHERE id = ?',
                                (self.usuario_actual['id'],))
                row = db.cursor.fetchone()

                if not row or row['password'] != password_hash:
                    self.mostrar_mensaje("Error", "Contraseña actual incorrecta", "error")
                    return

                # Actualizar
                nueva_hash = hashlib.sha256(nueva.encode()).hexdigest()
                db.cursor.execute('UPDATE usuarios SET password = ? WHERE id = ?',
                                (nueva_hash, self.usuario_actual['id']))
                db.connection.commit()

                d.destroy()
                self.mostrar_mensaje("Éxito", "Contraseña actualizada correctamente", "success")

            except Exception as e:
                self.mostrar_mensaje("Error", f"Error al cambiar contraseña:\n{str(e)}", "error")
            finally:
                db.disconnect()

        ctk.CTkButton(container, text="💾 Cambiar Contraseña", command=guardar,
                     height=50, font=("Arial", 15, "bold"),
                     fg_color=COLORS["success"]).pack(fill="x", pady=(0, 10))

        ctk.CTkButton(container, text="Cancelar", command=d.destroy,
                     height=45, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"]).pack(fill="x")

    def gestionar_suscripcion(self):
        """Diálogo para renovar/extender licencia con botones clickeables"""
        d = ctk.CTkToplevel(self)
        d.title(t("subscription.title"))
        d.geometry("480x380")
        d.transient(self)
        d.grab_set()

        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 240
        y = (d.winfo_screenheight() // 2) - 190
        d.geometry(f"480x380+{x}+{y}")

        ctk.CTkLabel(d, text="📋", font=("Arial", 40)).pack(pady=(25, 5))
        ctk.CTkLabel(d, text=t("subscription.title"),
                    font=("Arial", 20, "bold")).pack(pady=5)
        ctk.CTkLabel(d, text=t("subscription.description"),
                    font=("Arial", 13), text_color=COLORS["text_light"],
                    wraplength=400).pack(pady=(5, 15))

        btn_frame = ctk.CTkFrame(d, fg_color="transparent")
        btn_frame.pack(fill="x", padx=40)

        # Botón WhatsApp
        ctk.CTkButton(btn_frame, text=f"📱 {t('subscription.whatsapp')}",
                     font=("Arial", 14, "bold"), height=45,
                     fg_color="#25D366", hover_color="#128C7E",
                     command=lambda: webbrowser.open(
                         "https://wa.me/5491170821540?text=Hola%2C%20quiero%20gestionar%20mi%20suscripci%C3%B3n%20de%20WelcomeX"
                     )).pack(fill="x", pady=(0, 8))

        # Botón Email
        ctk.CTkButton(btn_frame, text=f"📧 {t('subscription.email')}",
                     font=("Arial", 14, "bold"), height=45,
                     fg_color="#0078D4", hover_color="#005A9E",
                     command=lambda: webbrowser.open(
                         "mailto:info@pampaguazu.com.ar?subject=WelcomeX%20-%20Gestionar%20Suscripci%C3%B3n"
                     )).pack(fill="x", pady=(0, 8))

        # Botón Web
        ctk.CTkButton(btn_frame, text=f"🌐 {t('subscription.website')}",
                     font=("Arial", 14, "bold"), height=45,
                     fg_color=COLORS["primary"], hover_color=COLORS.get("primary_dark", "#1a5fb4"),
                     command=lambda: webbrowser.open(
                         "https://pampaguazu.com.ar"
                     )).pack(fill="x", pady=(0, 8))

        # Botón Cerrar
        ctk.CTkButton(btn_frame, text=t("common.close"), command=d.destroy,
                     height=40, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"],
                     font=("Arial", 13)).pack(fill="x", pady=(5, 0))

    def mostrar_login(self):
        """Pantalla de login"""
        self.limpiar_ventana()

        frame = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        frame.pack(expand=True)

        # Selector de idioma arriba
        self.mostrar_selector_idioma(frame)

        # Logo
        ctk.CTkLabel(frame, text=t("app.title"), font=("Arial", 48, "bold"),
                    text_color=COLORS["primary"]).pack(pady=(30, 10))
        ctk.CTkLabel(frame, text=t("app.subtitle"),
                    font=("Arial", 16), text_color=COLORS["text_light"]).pack(pady=(0, 50))

        # Email
        ctk.CTkLabel(frame, text=t("login.email"), anchor="w", font=("Arial", 13)).pack(fill="x", padx=50)
        entry_email = ctk.CTkEntry(frame, width=450, height=50, font=("Arial", 15),
                                   fg_color=COLORS["card"], border_color=COLORS["border"])
        entry_email.pack(pady=(8, 20), padx=50)

        # Password con toggle mostrar/ocultar
        ctk.CTkLabel(frame, text=t("login.password"), anchor="w", font=("Arial", 13)).pack(fill="x", padx=50)
        pass_frame = ctk.CTkFrame(frame, fg_color="transparent")
        pass_frame.pack(fill="x", padx=50, pady=(8, 10))

        entry_pass = ctk.CTkEntry(pass_frame, width=400, height=50, show="●", font=("Arial", 15),
                                 fg_color=COLORS["card"], border_color=COLORS["border"])
        entry_pass.pack(side="left")

        # Variable de estado para el toggle (más confiable que cget)
        password_visible = {"state": False}

        def toggle_password():
            password_visible["state"] = not password_visible["state"]
            if password_visible["state"]:
                entry_pass.configure(show="")
                btn_eye.configure(text="🙈")
            else:
                entry_pass.configure(show="●")
                btn_eye.configure(text="👁")

        btn_eye = ctk.CTkButton(pass_frame, text="👁", width=45, height=50,
                               fg_color=COLORS["card"], hover_color=COLORS["border"],
                               command=toggle_password, font=("Arial", 16))
        btn_eye.pack(side="left", padx=(5, 0))

        # Checkbox "Recuérdame"
        remember_var = ctk.BooleanVar(value=False)
        remember_check = ctk.CTkCheckBox(
            frame, text=t("login.remember_me"),
            variable=remember_var,
            font=("Arial", 13),
            text_color=COLORS["text_light"],
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary"]
        )
        remember_check.pack(pady=(0, 5), padx=50, anchor="w")

        # Cargar credenciales guardadas
        saved_email = db.get_config("remember_email")
        saved_pass = db.get_config("remember_pass")
        if saved_email and saved_pass:
            entry_email.insert(0, saved_email)
            entry_pass.insert(0, saved_pass)
            remember_var.set(True)

        # Botón "Olvidé mi contraseña"
        btn_olvide = ctk.CTkButton(frame, text=t("login.forgot_password"),
                                    command=lambda: self.mostrar_recuperar_password(entry_email.get()),
                                    width=450, height=35, font=("Arial", 12),
                                    fg_color="transparent", text_color=COLORS["primary"],
                                    hover_color=COLORS["card"])
        btn_olvide.pack(pady=(0, 25), padx=50)

        def login():
            email = entry_email.get().strip()
            password = entry_pass.get().strip()

            if not email or not password:
                self.mostrar_mensaje(t("common.error"), t("login.error_empty"), "error")
                return

            # Guardar o borrar credenciales según checkbox
            if remember_var.get():
                db.set_config("remember_email", email)
                db.set_config("remember_pass", password)
            else:
                db.set_config("remember_email", "")
                db.set_config("remember_pass", "")

            # Intentar autenticar online con PAMPA primero
            from modules.pampa_client import PampaClient
            pampa = PampaClient("WELCOME_X")
            resultado_online = pampa.login(email, password)

            if resultado_online.get("success"):
                # Usuario autenticado online - guardar datos en local para cache
                user_data = resultado_online["usuario"]
                licencias = resultado_online.get("licencias", [])

                # Crear/actualizar usuario en BD local
                db.connect()
                try:
                    db.cursor.execute("SELECT id FROM usuarios WHERE email = ?", (email,))
                    existing = db.cursor.fetchone()

                    import hashlib
                    password_hash = hashlib.sha256(password.encode()).hexdigest()

                    if existing:
                        # Actualizar
                        db.cursor.execute("""
                            UPDATE usuarios SET nombre = ?, apellido = ?, password = ?
                            WHERE email = ?
                        """, (user_data.get('nombre', ''), user_data.get('apellido', ''), password_hash, email))
                        local_id = existing['id']
                    else:
                        # Crear
                        import uuid
                        from datetime import datetime
                        db.cursor.execute("""
                            INSERT INTO usuarios (uuid, email, password, nombre, apellido, rol, activo, fecha_registro)
                            VALUES (?, ?, ?, ?, ?, 'cliente', 1, ?)
                        """, (str(uuid.uuid4()), email, password_hash,
                              user_data.get('nombre', ''), user_data.get('apellido', ''),
                              datetime.now().isoformat()))
                        local_id = db.cursor.lastrowid

                    db.connection.commit()
                except Exception as e:
                    print(f"[LOGIN] Error sincronizando usuario local: {e}")
                finally:
                    db.disconnect()

                # Establecer usuario actual con datos de PAMPA
                self.usuario_actual = {
                    "id": local_id if 'local_id' in dir() else user_data.get('id'),
                    "pampa_id": user_data.get('id'),
                    "email": user_data.get('email'),
                    "nombre": user_data.get('nombre', ''),
                    "apellido": user_data.get('apellido', ''),
                    "rol": user_data.get('rol', 'cliente'),
                    "licencias": licencias
                }
                self.mostrar_principal()
            else:
                # Error online - intentar local como fallback
                error_msg = resultado_online.get("error", "")
                if "conexión" in error_msg.lower() or "timeout" in error_msg.lower() or "conectar" in error_msg.lower():
                    # Sin conexión - intentar BD local
                    resultado_local = db.autenticar_usuario(email, password)
                    if resultado_local["success"]:
                        self.usuario_actual = resultado_local["usuario"]
                        self.mostrar_mensaje(t("common.info"), t("connection.no_connection"), "info")
                        self.mostrar_principal()
                    else:
                        self.mostrar_mensaje("Error", "Sin conexión y credenciales no encontradas localmente.", "error")
                else:
                    self.mostrar_mensaje("Error", resultado_online.get("error", "Error de autenticación"), "error")
        
        entry_pass.bind('<Return>', lambda e: login())
        
        # Botones
        ctk.CTkButton(frame, text=t("login.sign_in"), command=login, width=450, height=55,
                     font=("Arial", 17, "bold"), fg_color=COLORS["primary"],
                     hover_color="#2563eb").pack(pady=15)
        
        ctk.CTkButton(frame, text=t("login.create_account"), command=self.mostrar_registro,
                     width=450, height=50, font=("Arial", 15),
                     fg_color="transparent", border_width=2,
                     border_color=COLORS["border"]).pack(pady=10)
        
        # Botón modo demo
        ctk.CTkButton(frame, text=f"🎭 {t('login.demo_mode')}", command=self.iniciar_modo_demo,
                     width=200, height=40, font=("Arial", 13),
                     fg_color=COLORS["warning"]).pack(pady=20)
    
    def mostrar_registro(self):
        """Formulario de registro"""
        d = ctk.CTkToplevel(self)
        d.title(t("login.create_account"))
        d.geometry("600x750")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 300
        y = (d.winfo_screenheight() // 2) - 375
        d.geometry(f"600x750+{x}+{y}")
        
        scroll = ctk.CTkScrollableFrame(d, fg_color=COLORS["bg"])
        scroll.pack(fill="both", expand=True, padx=30, pady=30)
        
        ctk.CTkLabel(scroll, text=t("register.title"),
                    font=("Arial", 28, "bold")).pack(pady=(0, 30))
        
        # Nombre
        ctk.CTkLabel(scroll, text=t("register.name"), anchor="w", font=("Arial", 13)).pack(fill="x")
        e_nombre = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_nombre.pack(fill="x", pady=(8, 12))

        # Apellido
        ctk.CTkLabel(scroll, text=t("register.surname"), anchor="w", font=("Arial", 13)).pack(fill="x")
        e_apellido = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_apellido.pack(fill="x", pady=(8, 12))

        # Email
        ctk.CTkLabel(scroll, text=t("register.email"), anchor="w", font=("Arial", 13)).pack(fill="x")
        e_email = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_email.pack(fill="x", pady=(8, 12))

        # Password con toggle
        ctk.CTkLabel(scroll, text=t("register.password"), anchor="w", font=("Arial", 13)).pack(fill="x")
        pass_frame1 = ctk.CTkFrame(scroll, fg_color="transparent")
        pass_frame1.pack(fill="x", pady=(8, 12))

        e_pass = ctk.CTkEntry(pass_frame1, height=45, show="●", font=("Arial", 14), fg_color=COLORS["card"])
        e_pass.pack(side="left", fill="x", expand=True)

        # Variable de estado para toggle
        pass1_visible = {"state": False}

        def toggle_pass1():
            pass1_visible["state"] = not pass1_visible["state"]
            if pass1_visible["state"]:
                e_pass.configure(show="")
                btn_eye1.configure(text="🙈")
            else:
                e_pass.configure(show="●")
                btn_eye1.configure(text="👁")

        btn_eye1 = ctk.CTkButton(pass_frame1, text="👁", width=45, height=45,
                                fg_color=COLORS["card"], hover_color=COLORS["border"],
                                command=toggle_pass1, font=("Arial", 14))
        btn_eye1.pack(side="left", padx=(5, 0))

        # Confirmar password con toggle
        ctk.CTkLabel(scroll, text=t("register.confirm_password"), anchor="w", font=("Arial", 13)).pack(fill="x")
        pass_frame2 = ctk.CTkFrame(scroll, fg_color="transparent")
        pass_frame2.pack(fill="x", pady=(8, 25))

        e_pass2 = ctk.CTkEntry(pass_frame2, height=45, show="●", font=("Arial", 14), fg_color=COLORS["card"])
        e_pass2.pack(side="left", fill="x", expand=True)

        # Variable de estado para toggle
        pass2_visible = {"state": False}

        def toggle_pass2():
            pass2_visible["state"] = not pass2_visible["state"]
            if pass2_visible["state"]:
                e_pass2.configure(show="")
                btn_eye2.configure(text="🙈")
            else:
                e_pass2.configure(show="●")
                btn_eye2.configure(text="👁")

        btn_eye2 = ctk.CTkButton(pass_frame2, text="👁", width=45, height=45,
                                fg_color=COLORS["card"], hover_color=COLORS["border"],
                                command=toggle_pass2, font=("Arial", 14))
        btn_eye2.pack(side="left", padx=(5, 0))
        
        # Info
        info_frame = ctk.CTkFrame(scroll, fg_color=COLORS["card"], corner_radius=10)
        info_frame.pack(fill="x", pady=(0, 25))
        
        info_inner = ctk.CTkFrame(info_frame, fg_color="transparent")
        info_inner.pack(padx=20, pady=20)
        
        ctk.CTkLabel(info_inner, text=f"ℹ️ {t('register.info_title')}", font=("Arial", 14, "bold")).pack(anchor="w")
        ctk.CTkLabel(info_inner,
                    text=t("register.info_text"),
                    font=("Arial", 12), text_color=COLORS["text_light"],
                    justify="left").pack(anchor="w", pady=(5, 0))
        
        def registrar():
            nombre = e_nombre.get().strip()
            apellido = e_apellido.get().strip()
            email = e_email.get().strip()
            password = e_pass.get().strip()
            password2 = e_pass2.get().strip()

            if not all([nombre, apellido, email, password, password2]):
                self.mostrar_mensaje(t("common.error"), t("register.error_all_fields"), "error")
                return

            if password != password2:
                self.mostrar_mensaje(t("common.error"), t("register.error_passwords_mismatch"), "error")
                return

            if len(password) < 6:
                self.mostrar_mensaje(t("common.error"), t("register.error_password_short"), "error")
                return

            # Registrar en PAMPA (servidor online)
            from modules.pampa_client import PampaClient
            pampa = PampaClient("WELCOME_X")
            resultado_online = pampa.register(email, password, nombre, apellido)

            if resultado_online.get("success"):
                # También crear en local para cache
                db.crear_usuario(email, password, nombre, apellido, 'cliente', None)

                d.destroy()
                self.mostrar_mensaje("Éxito",
                                   f"Cuenta creada correctamente!\n\n✅ Email: {email}\n\n⚠️ Contacta al administrador para activar tu licencia.\n\nMientras tanto, puedes probar el Modo Demo.",
                                   "success")
            else:
                error_msg = resultado_online.get("error", "")
                # Si es error de conexión, crear solo localmente
                if "conexión" in error_msg.lower() or "timeout" in error_msg.lower() or "conectar" in error_msg.lower():
                    resultado_local = db.crear_usuario(email, password, nombre, apellido, 'cliente', None)
                    if resultado_local["success"]:
                        d.destroy()
                        self.mostrar_mensaje("Info",
                                           f"Sin conexión. Cuenta creada localmente.\n\n✅ Email: {email}\n\n⚠️ Cuando haya conexión, registrate en pampaguazu.com.ar",
                                           "info")
                    else:
                        self.mostrar_mensaje("Error", resultado_local.get("error"), "error")
                else:
                    self.mostrar_mensaje("Error", resultado_online.get("error", "Error al registrar"), "error")
        
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=15)
        
        ctk.CTkButton(btn_frame, text="Crear Cuenta", command=registrar, height=55,
                     font=("Arial", 16, "bold"), fg_color=COLORS["success"]).pack(fill="x", pady=(0, 10))
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=d.destroy, height=50,
                     fg_color="transparent", border_width=2, 
                     border_color=COLORS["border"]).pack(fill="x")
    
    def iniciar_modo_demo(self):
        """Iniciar en modo demo"""
        # Verificar expiración TANTO en DB como en archivo persistente
        if db.demo_expirada(self.machine_id) or self._demo_expirada_persistente():
            self.mostrar_mensaje(
                t("demo.demo_expired_title"),
                t("demo.demo_expired_msg"),
                "warning"
            )
            return

        # Registrar activación en DB y en archivo persistente (solo la primera vez)
        primera_vez = db.registrar_demo_activada(self.machine_id)
        if primera_vez or not self._demo_registrada_persistente():
            self._guardar_demo_persistente()

        # Crear evento demo si no existe
        self.crear_evento_demo()

        # Login como usuario demo
        resultado = db.autenticar_usuario("demo@welcomex.com", "Demo2026!")

        if resultado["success"]:
            self.usuario_actual = resultado["usuario"]
            self.usuario_actual['es_demo'] = True
            self.mostrar_principal()
        else:
            self.mostrar_mensaje("Error", "No se pudo iniciar modo demo", "error")
    
    def crear_evento_demo(self):
        """Crear usuario y evento demo"""
        # Verificar si ya existe
        db.connect()
        try:
            db.cursor.execute("SELECT id FROM usuarios WHERE email = 'demo@welcomex.com'")
            usuario_demo = db.cursor.fetchone()
            
            if usuario_demo:
                # Usuario existe, verificar licencia
                user_id = usuario_demo['id']
                db.cursor.execute("SELECT id FROM licencias WHERE usuario_id = ?", (user_id,))
                licencia = db.cursor.fetchone()
                
                if not licencia:
                    # Crear licencia demo (7 días)
                    db.cursor.execute("""
                        INSERT INTO licencias (usuario_id, plan, fecha_inicio, fecha_vencimiento, 
                                              fecha_ultima_validacion, estado)
                        VALUES (?, 'demo', ?, ?, ?, 'activa')
                    """, (user_id, datetime.now().isoformat(), 
                          (datetime.now() + timedelta(days=7)).isoformat(),
                          datetime.now().isoformat()))
                    db.connection.commit()
                
                # Verificar evento Demo
                db.cursor.execute("SELECT id, video_loop FROM eventos WHERE usuario_id = ? AND nombre = 'Demo'", (user_id,))
                evento_demo = db.cursor.fetchone()
                if not evento_demo:
                    # Crear evento Demo si no existe
                    self._crear_evento_demo_completo(user_id)
                else:
                    # Reparar evento demo si le falta el video_loop
                    self._reparar_videos_demo(evento_demo)
            else:
                # Crear usuario demo desde cero
                resultado = db.crear_usuario("demo@welcomex.com", "Demo2026!", 
                                            "Usuario", "Demo", "admin", None)
                
                if resultado["success"]:
                    user_id = resultado["id"]
                    
                    # Crear licencia demo (7 días)
                    db.crear_licencia(user_id, "demo", 7)
                    
                    # Crear evento completo
                    self._crear_evento_demo_completo(user_id)
        except Exception as e:
            print(f"Error creando demo: {e}")
        finally:
            db.disconnect()
    
    def _crear_evento_demo_completo(self, user_id):
        """Crear evento demo único con invitados preestablecidos y videos"""
        import os
        import shutil
        from config.settings import RESOURCE_DIR, DATA_DIR

        # Carpeta de videos demo en el programa compilado
        demo_videos_src = os.path.join(RESOURCE_DIR, "demo_videos")

        # Carpeta de destino para videos (persistente junto al exe)
        videos_dest_dir = os.path.join(DATA_DIR, "videos_demo")
        os.makedirs(videos_dest_dir, exist_ok=True)

        # Copiar videos demo si existen y no se han copiado antes
        video_loop_dest = None
        video_loop_src = os.path.join(demo_videos_src, "video_loop_demo.mp4")

        if os.path.exists(video_loop_src):
            video_loop_dest = os.path.join(videos_dest_dir, "video_loop_demo.mp4")
            if not os.path.exists(video_loop_dest):
                shutil.copy2(video_loop_src, video_loop_dest)

        # Copiar videos por mesa (mesa_1.mp4, mesa_2.mp4, etc.)
        videos_mesa_paths = {}
        for mesa_num in range(1, 6):  # Mesas 1-5 con video demo
            video_mesa_src = os.path.join(demo_videos_src, f"mesa_{mesa_num}.mp4")
            if os.path.exists(video_mesa_src):
                video_mesa_dest = os.path.join(videos_dest_dir, f"mesa_{mesa_num}.mp4")
                if not os.path.exists(video_mesa_dest):
                    shutil.copy2(video_mesa_src, video_mesa_dest)
                videos_mesa_paths[mesa_num] = video_mesa_dest

        # Crear UN SOLO EVENTO llamado "Demo"
        evento_res = db.crear_evento(user_id, "Demo",
                                      datetime.now().strftime("%Y-%m-%d"),
                                      "20:00", None, video_loop_dest)

        if evento_res["success"]:
            evento_id = evento_res["id"]

            # Configurar videos por mesa si existen
            if videos_mesa_paths:
                db.guardar_videos_mesa(evento_id, videos_mesa_paths)

            # Poblar con invitados
            self._poblar_evento_demo(evento_id)

            # Iniciar evento en estado ACTIVO
            db.cambiar_estado_evento(evento_id, "activo")

    def _reparar_videos_demo(self, evento_demo):
        """Reparar evento demo existente si le faltan videos"""
        import os
        import shutil
        from config.settings import RESOURCE_DIR, DATA_DIR

        evento_id = evento_demo[0]
        video_loop_actual = evento_demo[1]

        # Si ya tiene video_loop válido, no hacer nada
        if video_loop_actual and os.path.exists(video_loop_actual):
            return

        demo_videos_src = os.path.join(RESOURCE_DIR, "demo_videos")
        videos_dest_dir = os.path.join(DATA_DIR, "videos_demo")
        os.makedirs(videos_dest_dir, exist_ok=True)

        # Copiar video_loop si existe en origen
        video_loop_src = os.path.join(demo_videos_src, "video_loop_demo.mp4")
        if os.path.exists(video_loop_src):
            video_loop_dest = os.path.join(videos_dest_dir, "video_loop_demo.mp4")
            if not os.path.exists(video_loop_dest):
                shutil.copy2(video_loop_src, video_loop_dest)

            # Actualizar en la base de datos
            db.cursor.execute("UPDATE eventos SET video_loop = ? WHERE id = ?",
                            (video_loop_dest, evento_id))
            db.connection.commit()
            print(f"Video loop demo reparado: {video_loop_dest}")

        # Reparar videos por mesa también
        videos_mesa_paths = {}
        for mesa_num in range(1, 6):
            video_mesa_src = os.path.join(demo_videos_src, f"mesa_{mesa_num}.mp4")
            if os.path.exists(video_mesa_src):
                video_mesa_dest = os.path.join(videos_dest_dir, f"mesa_{mesa_num}.mp4")
                if not os.path.exists(video_mesa_dest):
                    shutil.copy2(video_mesa_src, video_mesa_dest)
                videos_mesa_paths[mesa_num] = video_mesa_dest

        if videos_mesa_paths:
            db.guardar_videos_mesa(evento_id, videos_mesa_paths)
            print(f"Videos por mesa demo reparados: {len(videos_mesa_paths)} videos")

    def _poblar_evento_demo(self, evento_id):
        """Poblar evento con invitados demo"""
        import random
        import os
        import shutil
        from config.settings import RESOURCE_DIR, DATA_DIR

        nombres = ["Juan", "María", "Carlos", "Ana", "Luis", "Laura", "Pedro", "Sofía", "Diego", "Valentina"]
        apellidos = ["García", "Rodríguez", "Martínez", "López", "González", "Pérez", "Sánchez", "Fernández"]

        # === INVITADOS VIP CON VIDEO PERSONALIZADO ===
        # Copiar video personalizado demo si existe
        demo_videos_src = os.path.join(RESOURCE_DIR, "demo_videos")
        videos_dest_dir = os.path.join(DATA_DIR, "videos_demo")
        os.makedirs(videos_dest_dir, exist_ok=True)

        # Videos personalizados para VIPs
        vip_video_src = os.path.join(demo_videos_src, "vip_maria.mp4")
        vip_video_dest = os.path.join(videos_dest_dir, "vip_maria.mp4")

        if os.path.exists(vip_video_src) and not os.path.exists(vip_video_dest):
            shutil.copy2(vip_video_src, vip_video_dest)

        # Crear invitados VIP con video personalizado (NO acreditados para demo)
        invitados_vip = [
            {"nombre": "María", "apellido": "González", "mesa": 1, "video": vip_video_dest if os.path.exists(vip_video_dest) else None, "obs": "👑 VIP - Video Personalizado"},
            {"nombre": "Roberto", "apellido": "Fernández", "mesa": 2, "video": None, "obs": "🎵 DJ del evento"},
            {"nombre": "Carolina", "apellido": "López", "mesa": 3, "video": None, "obs": "📸 Fotógrafa"},
        ]

        invitados_ids = []
        vip_ids = []

        # Agregar VIPs primero (estos NO se acreditan automáticamente)
        for vip in invitados_vip:
            resultado_vip = db.agregar_invitado(
                evento_id,
                vip["nombre"],
                vip["apellido"],
                vip["mesa"],
                observaciones=vip["obs"],
                video_personalizado=vip["video"]
            )
            if resultado_vip["success"]:
                vip_ids.append(resultado_vip["id"])

        # === INVITADOS REGULARES ===
        for i in range(300):
            nombre = random.choice(nombres)
            apellido = random.choice(apellidos)
            mesa = random.randint(1, 30)

            resultado_inv = db.agregar_invitado(evento_id, nombre, apellido, mesa)
            if resultado_inv["success"]:
                invitados_ids.append(resultado_inv["id"])
        
        # IMPORTANTE: Conectar ANTES de acreditar
        db.connect()
        
        # Acreditar 150 invitados random (50%)
        acreditados = random.sample(invitados_ids, min(150, len(invitados_ids)))
        for inv_id in acreditados:
            db.cursor.execute("UPDATE invitados SET presente = 1 WHERE id = ?", (inv_id,))
            # Registrar ingreso
            db.cursor.execute("""
                INSERT INTO acreditaciones (invitado_id, evento_id, tipo, timestamp)
                VALUES (?, ?, 'ingreso', ?)
            """, (inv_id, evento_id, datetime.now().isoformat()))
        
        db.connection.commit()
        db.disconnect()

    def mostrar_recuperar_password(self, email_prefill=""):
        """Diálogo para recuperar contraseña"""
        d = ctk.CTkToplevel(self)
        d.title("Recuperar Contraseña")
        d.geometry("550x400")
        d.transient(self)
        d.grab_set()

        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 275
        y = (d.winfo_screenheight() // 2) - 200
        d.geometry(f"550x400+{x}+{y}")

        container = ctk.CTkFrame(d, fg_color=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=40, pady=40)

        ctk.CTkLabel(container, text="🔑 Recuperar Contraseña",
                    font=("Arial", 24, "bold")).pack(pady=(0, 20))

        ctk.CTkLabel(container,
                    text="Ingresa tu email y te enviaremos un código\nde recuperación de 6 dígitos.",
                    font=("Arial", 13), text_color=COLORS["text_light"]).pack(pady=(0, 30))

        # Email
        ctk.CTkLabel(container, text="Email", anchor="w", font=("Arial", 13)).pack(fill="x")
        entry_email = ctk.CTkEntry(container, width=450, height=45, font=("Arial", 14),
                                   fg_color=COLORS["card"], border_color=COLORS["border"])
        entry_email.pack(pady=(8, 25))

        if email_prefill:
            entry_email.insert(0, email_prefill)

        def enviar_codigo():
            email = entry_email.get().strip()

            if not email:
                self.mostrar_mensaje("Error", "Ingresa tu email", "error")
                return

            # Verificar que el usuario exista
            db.connect()
            try:
                db.cursor.execute('SELECT id, nombre FROM usuarios WHERE email = ?', (email,))
                usuario = db.cursor.fetchone()

                if not usuario:
                    self.mostrar_mensaje("Error", "No existe una cuenta con ese email", "error")
                    return

                # Generar código de 6 dígitos
                import random
                codigo = ''.join([str(random.randint(0, 9)) for _ in range(6)])
                expira = (datetime.now() + timedelta(hours=1)).isoformat()

                # Guardar en configuración temporal
                db.cursor.execute('''
                    INSERT OR REPLACE INTO configuracion (clave, valor)
                    VALUES (?, ?)
                ''', (f'reset_code_{email}', f'{codigo}|{expira}'))
                db.connection.commit()

                # Enviar email (simular por ahora)
                self.mostrar_mensaje("Código Enviado",
                                    f"Se envió un código de recuperación a:\n{email}\n\nCódigo (para pruebas): {codigo}\n\nTienes 1 hora para usarlo.",
                                    "success")

                d.destroy()
                self.mostrar_ingresar_codigo_recuperacion(email)

            except Exception as e:
                self.mostrar_mensaje("Error", f"Error al generar código:\n{str(e)}", "error")
            finally:
                db.disconnect()

        ctk.CTkButton(container, text="Enviar Código", command=enviar_codigo,
                     width=450, height=50, font=("Arial", 15, "bold"),
                     fg_color=COLORS["primary"]).pack(pady=(0, 10))

        ctk.CTkButton(container, text="Cancelar", command=d.destroy,
                     width=450, height=45, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"]).pack()

    def mostrar_ingresar_codigo_recuperacion(self, email):
        """Diálogo para ingresar código y nueva contraseña"""
        d = ctk.CTkToplevel(self)
        d.title("Ingresar Código")
        d.geometry("550x500")
        d.transient(self)
        d.grab_set()

        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 275
        y = (d.winfo_screenheight() // 2) - 250
        d.geometry(f"550x500+{x}+{y}")

        container = ctk.CTkFrame(d, fg_color=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=40, pady=40)

        ctk.CTkLabel(container, text="🔐 Restablecer Contraseña",
                    font=("Arial", 24, "bold")).pack(pady=(0, 20))

        ctk.CTkLabel(container,
                    text=f"Revisa tu email: {email}",
                    font=("Arial", 13), text_color=COLORS["text_light"]).pack(pady=(0, 30))

        # Código
        ctk.CTkLabel(container, text="Código de 6 dígitos", anchor="w", font=("Arial", 13)).pack(fill="x")
        entry_codigo = ctk.CTkEntry(container, width=450, height=45, font=("Arial", 18, "bold"),
                                    justify="center", fg_color=COLORS["card"], border_color=COLORS["border"])
        entry_codigo.pack(pady=(8, 25))

        # Nueva contraseña
        ctk.CTkLabel(container, text="Nueva Contraseña", anchor="w", font=("Arial", 13)).pack(fill="x")
        entry_pass = ctk.CTkEntry(container, width=450, height=45, show="●", font=("Arial", 14),
                                 fg_color=COLORS["card"], border_color=COLORS["border"])
        entry_pass.pack(pady=(8, 20))

        # Confirmar contraseña
        ctk.CTkLabel(container, text="Confirmar Contraseña", anchor="w", font=("Arial", 13)).pack(fill="x")
        entry_pass_confirm = ctk.CTkEntry(container, width=450, height=45, show="●", font=("Arial", 14),
                                         fg_color=COLORS["card"], border_color=COLORS["border"])
        entry_pass_confirm.pack(pady=(8, 25))

        def restablecer():
            codigo = entry_codigo.get().strip()
            password = entry_pass.get().strip()
            password_confirm = entry_pass_confirm.get().strip()

            if not codigo or not password or not password_confirm:
                self.mostrar_mensaje("Error", "Completa todos los campos", "error")
                return

            if password != password_confirm:
                self.mostrar_mensaje("Error", "Las contraseñas no coinciden", "error")
                return

            if len(password) < 6:
                self.mostrar_mensaje("Error", "La contraseña debe tener al menos 6 caracteres", "error")
                return

            # Verificar código
            db.connect()
            try:
                db.cursor.execute('SELECT valor FROM configuracion WHERE clave = ?',
                                (f'reset_code_{email}',))
                row = db.cursor.fetchone()

                if not row:
                    self.mostrar_mensaje("Error", "Código inválido o expirado", "error")
                    return

                codigo_guardado, expira = row['valor'].split('|')

                # Verificar expiración
                if datetime.now() > datetime.fromisoformat(expira):
                    self.mostrar_mensaje("Error", "El código ha expirado. Solicita uno nuevo.", "error")
                    db.cursor.execute('DELETE FROM configuracion WHERE clave = ?',
                                    (f'reset_code_{email}',))
                    db.connection.commit()
                    return

                # Verificar código
                if codigo != codigo_guardado:
                    self.mostrar_mensaje("Error", "Código incorrecto", "error")
                    return

                # Actualizar contraseña
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                db.cursor.execute('UPDATE usuarios SET password = ? WHERE email = ?',
                                (password_hash, email))

                # Eliminar código usado
                db.cursor.execute('DELETE FROM configuracion WHERE clave = ?',
                                (f'reset_code_{email}',))

                db.connection.commit()

                self.mostrar_mensaje("Éxito",
                                    "Contraseña actualizada correctamente.\n\nYa puedes iniciar sesión.",
                                    "success")
                d.destroy()

            except Exception as e:
                self.mostrar_mensaje("Error", f"Error al restablecer contraseña:\n{str(e)}", "error")
            finally:
                db.disconnect()

        ctk.CTkButton(container, text="Restablecer Contraseña", command=restablecer,
                     width=450, height=50, font=("Arial", 15, "bold"),
                     fg_color=COLORS["success"]).pack(pady=(0, 10))

        ctk.CTkButton(container, text="Cancelar", command=d.destroy,
                     width=450, height=45, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"]).pack()

    # ============================================
    # PANTALLA PRINCIPAL
    # ============================================

    def mostrar_principal(self):
        """Pantalla principal con sidebar y contenido"""
        self.limpiar_ventana()
        
        # Sidebar
        sidebar = ctk.CTkFrame(self, width=270, fg_color=COLORS["sidebar"])
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        
        # Logo y usuario
        ctk.CTkLabel(sidebar, text="WelcomeX", font=("Arial", 30, "bold"),
                    text_color=COLORS["primary"]).pack(pady=(35, 15))
        
        ctk.CTkLabel(sidebar, text=f"👤 {self.usuario_actual['nombre']} {self.usuario_actual.get('apellido', '')}",
                    font=("Arial", 12), text_color=COLORS["text_light"]).pack(pady=(0, 10))
        
        # Menú simplificado - sin roles
        ctk.CTkButton(sidebar, text=f"📋 {t('sidebar.my_events')}", command=self.mostrar_eventos,
                     width=230, height=50, anchor="w", font=("Arial", 14),
                     fg_color="transparent", hover_color=COLORS["hover"]).pack(pady=5)

        ctk.CTkButton(sidebar, text=f"⚙️ {t('sidebar.settings')}", command=self.mostrar_configuracion,
                     width=230, height=50, anchor="w", font=("Arial", 14),
                     fg_color="transparent", hover_color=COLORS["hover"]).pack(pady=5)

        ctk.CTkButton(sidebar, text=f"🔄 {t('sidebar.updates')}",
                     command=self.mostrar_ventana_updates,
                     width=230, height=50, anchor="w", font=("Arial", 14),
                     fg_color="transparent", hover_color=COLORS["hover"]).pack(pady=5)

        # Salir
        ctk.CTkButton(sidebar, text=f"🚪 {t('sidebar.logout')}", command=self.mostrar_login,
                     width=230, height=50, fg_color=COLORS["danger"],
                     hover_color="#c53030", font=("Arial", 14)).pack(side="bottom", pady=25)
        
        # Área de contenido
        self.content = ctk.CTkScrollableFrame(self, fg_color=COLORS["bg"])
        self.content.pack(side="right", fill="both", expand=True, padx=25, pady=25)
        
        # Banner demo si es modo demo
        if self.es_modo_demo():
            demo_banner = ctk.CTkFrame(self.content, fg_color="#1e3a8a", corner_radius=10)
            demo_banner.pack(fill="x", pady=(0, 20))
            
            banner_inner = ctk.CTkFrame(demo_banner, fg_color="transparent")
            banner_inner.pack(padx=25, pady=18)
            
            ctk.CTkLabel(banner_inner, text=f"🎭 {t('demo.mode_label')}",
                        font=("Arial", 18, "bold"), text_color="#60a5fa").pack(anchor="w")
            ctk.CTkLabel(banner_inner,
                        text=t("demo.banner_info"),
                        font=("Arial", 12), text_color="#bfdbfe", justify="left").pack(anchor="w", pady=(5, 0))
        
        # Mostrar contenido inicial
        self.mostrar_eventos()

        # Iniciar validación silenciosa cada 6 horas (solo si tiene licencia, no demo)
        self._iniciar_validacion_silenciosa()

    # ============================================
    # EVENTOS
    # ============================================
    
    def mostrar_eventos(self):
        """Lista de eventos del usuario"""
        for w in self.content.winfo_children():
            w.destroy()
        
        # Header
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", pady=(0, 25))
        
        # RIGHT elements first so they always get space
        if self.tiene_permiso('crear_eventos'):
            ctk.CTkButton(header, text=f"➕ {t('events.new_event')}", command=self.crear_evento,
                         height=50, width=180, font=("Arial", 15, "bold"),
                         fg_color=COLORS["success"]).pack(side="right")

        # Estado licencia PAMPA (visible para todos)
        self.mostrar_estado_licencia(header)

        ctk.CTkLabel(header, text=t("events.title"), font=("Arial", 34, "bold")).pack(side="left")

        # Obtener eventos
        eventos = db.obtener_eventos_usuario(self.usuario_actual['id'])

        if not eventos:
            ctk.CTkLabel(self.content,
                        text=t("events.no_events"),
                        font=("Arial", 17), text_color=COLORS["text_light"],
                        justify="center").pack(expand=True, pady=100)
            return
        
        # Listar eventos
        for evento in eventos:
            self.crear_card_evento(evento)
    
    def mostrar_estado_licencia(self, parent):
        """Mostrar estado de licencia PAMPA con indicador visual claro"""
        try:
            # Verificar si estamos en modo demo
            if self.es_modo_demo():
                frame_lic = ctk.CTkFrame(parent, fg_color="#1e3a5f", corner_radius=8)
                frame_lic.pack(side="right", padx=10)

                inner = ctk.CTkFrame(frame_lic, fg_color="transparent")
                inner.pack(padx=15, pady=8)

                ctk.CTkLabel(inner, text=f"🎭 {t('demo.mode_label')}",
                            font=("Arial", 12, "bold"), text_color="#60a5fa").pack()
                ctk.CTkLabel(inner, text=t("demo.no_active_license"),
                            font=("Arial", 10), text_color="#93c5fd").pack()
                return

            # Obtener estado de licencia desde caché
            license_key = self.cargar_license_key()

            if not license_key:
                # Sin licencia configurada
                frame_lic = ctk.CTkFrame(parent, fg_color="#4a1d1d", corner_radius=8)
                frame_lic.pack(side="right", padx=10)

                inner = ctk.CTkFrame(frame_lic, fg_color="transparent")
                inner.pack(padx=15, pady=8)

                ctk.CTkLabel(inner, text=f"❌ {t('config.no_license')}",
                            font=("Arial", 12, "bold"), text_color=COLORS["danger"]).pack()
                ctk.CTkLabel(inner, text=t("config.configure_license"),
                            font=("Arial", 10), text_color="#fca5a5").pack()
                return

            # Validar licencia (usa caché si está disponible)
            result = self.pampa.validate_license(license_key, force_online=False)

            if not result:
                return

            dias = result.get('days_remaining')
            horas = None
            expires_at_str = result.get('expires_at')
            if dias is None:
                # Calcular desde expires_at si el servidor no lo envió
                if expires_at_str:
                    try:
                        diff = datetime.fromisoformat(expires_at_str) - datetime.now()
                        dias = max(0, diff.days)
                        horas = max(0, int(diff.total_seconds() / 3600))
                    except:
                        dias = 0
                        horas = 0
                else:
                    dias = 0
                    horas = 0
            else:
                # Calcular horas desde expires_at
                if expires_at_str:
                    try:
                        diff = datetime.fromisoformat(expires_at_str) - datetime.now()
                        horas = max(0, int(diff.total_seconds() / 3600))
                    except:
                        horas = dias * 24
                else:
                    horas = dias * 24
            status = result.get('status', 'unknown')

            # Determinar estado visual
            if not result.get('valid'):
                # Licencia inválida o vencida
                if status == 'expired':
                    bg_color = "#4a1d1d"
                    icono = "🔴"
                    texto_estado = t("license_status.expired")
                    texto_sub = t("license_status.renew_license")
                    color_texto = COLORS["danger"]
                    color_sub = "#fca5a5"
                else:
                    bg_color = "#4a1d1d"
                    icono = "⛔"
                    texto_estado = t("license_status.invalid")
                    texto_sub = result.get('message', t("license_status.contact_support"))[:25]
                    color_texto = COLORS["danger"]
                    color_sub = "#fca5a5"
            elif dias == 0 and horas is not None and horas > 0:
                # Menos de 1 día - mostrar horas
                bg_color = "#4a1d1d"
                icono = "🔴"
                texto_estado = f"VENCE EN {horas} HORA{'S' if horas != 1 else ''}"
                texto_sub = t("license_status.renew_urgent")
                color_texto = COLORS["danger"]
                color_sub = "#fca5a5"
            elif dias <= 3:
                # Crítico - vence en 3 días o menos
                bg_color = "#4a1d1d"
                icono = "🔴"
                texto_estado = t("license_status.expires_in", days=dias, plural='S' if dias != 1 else '')
                texto_sub = t("license_status.renew_urgent")
                color_texto = COLORS["danger"]
                color_sub = "#fca5a5"
            elif dias <= 7:
                # Advertencia - vence en una semana
                bg_color = "#4a3f1d"
                icono = "🟠"
                texto_estado = t("license_status.expires_in", days=dias, plural='S' if dias != 1 else '')
                texto_sub = t("license_status.consider_renew")
                color_texto = COLORS["warning"]
                color_sub = "#fde68a"
            elif dias <= 30:
                # Próximo a vencer
                bg_color = "#1d3a4a"
                icono = "🟡"
                texto_estado = t("license_status.expires_in", days=dias, plural='S' if dias != 1 else '')
                texto_sub = t("license_status.valid")
                color_texto = "#fbbf24"
                color_sub = "#bfdbfe"
            else:
                # Todo bien
                bg_color = "#1d4a2a"
                icono = "🟢"
                texto_estado = t("license_status.valid")
                texto_sub = t("license_status.valid_days", days=dias)
                color_texto = COLORS["success"]
                color_sub = "#86efac"

            # Crear frame visual
            frame_lic = ctk.CTkFrame(parent, fg_color=bg_color, corner_radius=8)
            frame_lic.pack(side="right", padx=10)

            inner = ctk.CTkFrame(frame_lic, fg_color="transparent")
            inner.pack(padx=15, pady=8)

            ctk.CTkLabel(inner, text=f"{icono} {texto_estado}",
                        font=("Arial", 12, "bold"), text_color=color_texto).pack()
            ctk.CTkLabel(inner, text=texto_sub,
                        font=("Arial", 10), text_color=color_sub).pack()

        except Exception as e:
            print(f"[ERROR] mostrar_estado_licencia: {e}")
            pass
    
    def crear_card_evento(self, evento):
        """Card de evento"""
        card = ctk.CTkFrame(self.content, fg_color=COLORS["card"], corner_radius=12)
        card.pack(fill="x", pady=10)
        
        # Top - info
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=25, pady=20)
        
        # Nombre
        ctk.CTkLabel(top, text=evento['nombre'], font=("Arial", 22, "bold")).pack(side="left")
        
        # Fecha
        ctk.CTkLabel(top, text=f"📅 {evento['fecha_evento']}", 
                    font=("Arial", 14)).pack(side="left", padx=25)
        
        # Estado
        estado_colors = {
            "creado": COLORS["text_light"],
            "activo": COLORS["success"],
            "pausado": COLORS["warning"],
            "finalizado": COLORS["danger"]
        }
        estado_texto = evento['estado'].upper()
        ctk.CTkLabel(top, text=estado_texto,
                    text_color=estado_colors.get(evento['estado'], "white"),
                    font=("Arial", 13, "bold")).pack(side="left")

        # Stats de invitados - SIEMPRE VISIBLE (en todos los estados)
        invitados = db.obtener_invitados_evento(evento['id'])
        total = len(invitados)
        acreditados = len([i for i in invitados if i.get('presente')])

        if total > 0:
            porcentaje = int((acreditados / total) * 100) if total > 0 else 0

            stats_frame = ctk.CTkFrame(card, fg_color=COLORS["bg"], corner_radius=8)
            stats_frame.pack(fill="x", padx=25, pady=(0, 15))

            stats_inner = ctk.CTkFrame(stats_frame, fg_color="transparent")
            stats_inner.pack(padx=15, pady=12)

            ctk.CTkLabel(stats_inner, text="👥 Invitados:",
                        font=("Arial", 13, "bold")).pack(side="left")

            ctk.CTkLabel(stats_inner, text=f"{total}",
                        font=("Arial", 13)).pack(side="left", padx=5)

            ctk.CTkLabel(stats_inner, text="•",
                        font=("Arial", 13), text_color=COLORS["text_light"]).pack(side="left", padx=10)

            ctk.CTkLabel(stats_inner, text="✅ Acreditados:",
                        font=("Arial", 13, "bold")).pack(side="left")

            ctk.CTkLabel(stats_inner, text=f"{acreditados}",
                        font=("Arial", 13), text_color=COLORS["success"]).pack(side="left", padx=5)

            ctk.CTkLabel(stats_inner, text="•",
                        font=("Arial", 13), text_color=COLORS["text_light"]).pack(side="left", padx=10)

            ctk.CTkLabel(stats_inner, text=f"{porcentaje}%",
                        font=("Arial", 14, "bold"),
                        text_color=COLORS["primary"]).pack(side="left")
        else:
            # Sin invitados todavía
            stats_frame = ctk.CTkFrame(card, fg_color=COLORS["bg"], corner_radius=8)
            stats_frame.pack(fill="x", padx=25, pady=(0, 15))

            stats_inner = ctk.CTkFrame(stats_frame, fg_color="transparent")
            stats_inner.pack(padx=15, pady=12)

            ctk.CTkLabel(stats_inner, text="ℹ️ Sin invitados todavía",
                        font=("Arial", 13),
                        text_color=COLORS["text_light"]).pack(side="left")

            ctk.CTkLabel(stats_inner, text="•",
                        font=("Arial", 13), text_color=COLORS["text_light"]).pack(side="left", padx=10)

            ctk.CTkLabel(stats_inner, text="Importa un Excel o agrega manualmente",
                        font=("Arial", 12),
                        text_color=COLORS["text_light"]).pack(side="left")

        # Todos los botones en una sola fila
        btn_row = ctk.CTkFrame(card, fg_color="transparent")

        if evento['estado'] == 'creado':
            if self.tiene_permiso('iniciar_eventos'):
                ctk.CTkButton(btn_row, text="▶️ Iniciar", width=120, height=42,
                             font=("Arial", 13),
                             command=lambda e=evento: self.iniciar_evento(e)).pack(side="left", padx=4)
            if self.tiene_permiso('eliminar_eventos'):
                ctk.CTkButton(btn_row, text="🗑️ Borrar", width=120, height=42,
                             font=("Arial", 13), fg_color=COLORS["danger"],
                             command=lambda e=evento: self.eliminar_evento(e)).pack(side="left", padx=4)

        elif evento['estado'] == 'activo':
            if self.tiene_permiso('iniciar_eventos'):
                ctk.CTkButton(btn_row, text="⏸️ Pausar", width=120, height=42,
                             font=("Arial", 13),
                             command=lambda e=evento: self.pausar_evento(e)).pack(side="left", padx=4)
            if self.tiene_permiso('finalizar_eventos'):
                ctk.CTkButton(btn_row, text="⏹️ Finalizar", width=120, height=42,
                             font=("Arial", 13), fg_color=COLORS["danger"],
                             command=lambda e=evento: self.finalizar_evento(e)).pack(side="left", padx=4)

        elif evento['estado'] == 'pausado':
            if self.tiene_permiso('iniciar_eventos'):
                ctk.CTkButton(btn_row, text="▶️ Reanudar", width=130, height=42,
                             font=("Arial", 13),
                             command=lambda e=evento: self.reanudar_evento(e)).pack(side="left", padx=4)
            if self.tiene_permiso('finalizar_eventos'):
                ctk.CTkButton(btn_row, text="⏹️ Finalizar", width=120, height=42,
                             font=("Arial", 13), fg_color=COLORS["danger"],
                             command=lambda e=evento: self.finalizar_evento(e)).pack(side="left", padx=4)
            if self.tiene_permiso('eliminar_eventos'):
                ctk.CTkButton(btn_row, text="🗑️ Eliminar", width=120, height=42,
                             font=("Arial", 13), fg_color="#7f1d1d",
                             command=lambda e=evento: self.eliminar_evento(e)).pack(side="left", padx=4)

        elif evento['estado'] == 'finalizado':
            ctk.CTkButton(btn_row, text="📊 Ver Reporte", width=140, height=42,
                         font=("Arial", 13), fg_color=COLORS["primary"],
                         command=lambda e=evento: self.ver_reporte_evento(e)).pack(side="left", padx=4)
            if self.tiene_permiso('eliminar_eventos'):
                ctk.CTkButton(btn_row, text="🗑️ Eliminar", width=120, height=42,
                             font=("Arial", 13), fg_color="#7f1d1d",
                             command=lambda e=evento: self.eliminar_evento(e)).pack(side="left", padx=4)

        if self.tiene_permiso('ver_invitados'):
            ctk.CTkButton(btn_row, text="👥 Invitados", width=130, height=42,
                         font=("Arial", 13),
                         command=lambda e=evento: self.ver_invitados(e)).pack(side="left", padx=4)

        if evento['estado'] == 'activo' and self.tiene_permiso('hacer_sorteos'):
            ctk.CTkButton(btn_row, text="🎲 Sorteos", width=120, height=42,
                         font=("Arial", 13),
                         command=lambda e=evento: self.ver_sorteos(e)).pack(side="left", padx=4)

        if evento['estado'] == 'activo' and self.tiene_permiso('abrir_kiosco'):
            ctk.CTkButton(btn_row, text="📱 Kiosco", width=120, height=42,
                         font=("Arial", 13),
                         command=lambda e=evento: self.abrir_kiosco(e)).pack(side="left", padx=4)

        if evento['estado'] != 'finalizado' and self.tiene_permiso('crear_eventos') and not self.es_modo_demo():
            ctk.CTkButton(btn_row, text="✏️ Editar", width=110, height=42,
                         font=("Arial", 13),
                         command=lambda e=evento: self.editar_evento(e)).pack(side="left", padx=4)

        btn_row.pack(fill="x", padx=25, pady=(0, 20))
    
    def crear_evento(self):
        """Formulario crear evento"""
        if not self.validar_accion_escritura("crear eventos"):
            return
        
        d = ctk.CTkToplevel(self)
        d.title("Nuevo Evento")
        d.geometry("600x750")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 300
        y = (d.winfo_screenheight() // 2) - 375
        d.geometry(f"600x750+{x}+{y}")
        
        container = ctk.CTkFrame(d, fg_color=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=35, pady=35)
        
        ctk.CTkLabel(container, text="Crear Nuevo Evento", 
                    font=("Arial", 26, "bold")).pack(pady=(0, 30))
        
        # Nombre
        ctk.CTkLabel(container, text="Nombre del Evento *", anchor="w",
                    font=("Arial", 13)).pack(fill="x")
        e_nombre = ctk.CTkEntry(container, height=45, font=("Arial", 14),
                               fg_color=COLORS["card"])
        e_nombre.pack(fill="x", pady=(8, 15))
        
        # Fecha con calendario
        ctk.CTkLabel(container, text="Fecha del Evento *", anchor="w",
                    font=("Arial", 13)).pack(fill="x")
        
        fecha_frame = ctk.CTkFrame(container, fg_color="transparent")
        fecha_frame.pack(fill="x", pady=(8, 15))
        
        e_fecha = ctk.CTkEntry(fecha_frame, height=45, font=("Arial", 14),
                              fg_color=COLORS["card"], width=400)
        e_fecha.pack(side="left", fill="x", expand=True)
        e_fecha.insert(0, datetime.now().strftime("%Y-%m-%d"))
        
        def abrir_calendario():
            cal_window = ctk.CTkToplevel(d)
            cal_window.title("Seleccionar Fecha")
            cal_window.geometry("350x400")
            cal_window.transient(d)
            cal_window.grab_set()
            
            # Centrar
            cal_window.update_idletasks()
            x = d.winfo_x() + (d.winfo_width() // 2) - 175
            y = d.winfo_y() + (d.winfo_height() // 2) - 200
            cal_window.geometry(f"350x400+{x}+{y}")
            
            from tkcalendar import Calendar
            
            cal = Calendar(cal_window, selectmode='day',
                          year=datetime.now().year,
                          month=datetime.now().month,
                          day=datetime.now().day,
                          date_pattern='yyyy-mm-dd')
            cal.pack(pady=20, padx=20, fill="both", expand=True)
            
            def seleccionar():
                e_fecha.delete(0, 'end')
                e_fecha.insert(0, cal.get_date())
                cal_window.destroy()
            
            ctk.CTkButton(cal_window, text="Seleccionar", command=seleccionar,
                         height=45, font=("Arial", 14)).pack(pady=15)
        
        ctk.CTkButton(fecha_frame, text="📅", command=abrir_calendario,
                     width=60, height=45, font=("Arial", 18)).pack(side="left", padx=5)
        
        # Hora inicio
        ctk.CTkLabel(container, text="Hora de Inicio (HH:MM) *", anchor="w",
                    font=("Arial", 13)).pack(fill="x")
        e_hora = ctk.CTkEntry(container, height=45, font=("Arial", 14),
                             fg_color=COLORS["card"])
        e_hora.pack(fill="x", pady=(8, 15))
        e_hora.insert(0, "20:00")
        
        # Hora límite
        ctk.CTkLabel(container, text="Hora Límite Acreditación (HH:MM) - Opcional", anchor="w",
                    font=("Arial", 13)).pack(fill="x")
        e_limite = ctk.CTkEntry(container, height=45, font=("Arial", 14),
                               fg_color=COLORS["card"])
        e_limite.pack(fill="x", pady=(8, 15))
        
        # Video Loop
        ctk.CTkLabel(container, text="Video Loop (opcional)", anchor="w",
                    font=("Arial", 13)).pack(fill="x")
        
        video_frame = ctk.CTkFrame(container, fg_color="transparent")
        video_frame.pack(fill="x", pady=(8, 30))
        
        e_video = ctk.CTkEntry(video_frame, height=45, font=("Arial", 14),
                              fg_color=COLORS["card"], placeholder_text="Sin video")
        e_video.pack(side="left", fill="x", expand=True)
        
        def seleccionar_video():
            filepath = filedialog.askopenfilename(
                title="Seleccionar Video Loop",
                filetypes=[("Videos", "*.mp4 *.avi *.mov *.mkv"), ("Todos", "*.*")]
            )
            if filepath:
                e_video.delete(0, 'end')
                e_video.insert(0, filepath)
        
        ctk.CTkButton(video_frame, text="📁", command=seleccionar_video,
                     width=60, height=45, font=("Arial", 18)).pack(side="left", padx=5)
        
        def guardar():
            nombre = e_nombre.get().strip()
            fecha = e_fecha.get().strip()
            hora = e_hora.get().strip()
            limite = e_limite.get().strip() if e_limite.get().strip() else None
            video_loop = e_video.get().strip() if e_video.get().strip() else None
            
            if not nombre or not fecha or not hora:
                self.mostrar_mensaje("Error", "Nombre, fecha y hora de inicio son obligatorios", "error")
                return
            
            resultado = db.crear_evento(
                usuario_id=self.usuario_actual['id'],
                nombre=nombre,
                fecha_evento=fecha,
                hora_inicio=hora,
                hora_limite=limite,
                video_loop=video_loop
            )
            
            if resultado["success"]:
                d.destroy()
                self.mostrar_mensaje("Éxito", f"Evento '{nombre}' creado correctamente", "success")
                self.mostrar_eventos()
            else:
                self.mostrar_mensaje("Error", resultado.get("error", "Error al crear evento"), "error")
        
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=15)
        
        ctk.CTkButton(btn_frame, text="Crear Evento", command=guardar, height=55,
                     font=("Arial", 15, "bold"), fg_color=COLORS["success"]).pack(fill="x", pady=(0, 8))
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=d.destroy, height=50,
                     fg_color="transparent", border_width=2, 
                     border_color=COLORS["border"]).pack(fill="x")
    
    def iniciar_evento(self, evento):
        """Iniciar evento - verificar mesas antes"""
        if not self.validar_accion_escritura("iniciar eventos"):
            return
        
        # Verificar invitados sin mesa
        sin_mesa = db.verificar_invitados_sin_mesa(evento['id'])
        
        if sin_mesa:
            # Mostrar error con lista
            nombres = "\n".join([f"• {inv['apellido']} {inv['nombre']}" for inv in sin_mesa[:10]])
            if len(sin_mesa) > 10:
                nombres += f"\n... y {len(sin_mesa) - 10} más"
            
            self.mostrar_mensaje("No se puede iniciar", 
                                f"Faltan asignar mesas a los siguientes invitados:\n\n{nombres}\n\nAsigne mesas antes de iniciar.",
                                "warning")
            return
        
        db.cambiar_estado_evento(evento['id'], "activo", self.usuario_actual['id'])
        self.mostrar_eventos()
    
    def pausar_evento(self, evento):
        """Pausar evento"""
        if not self.validar_accion_escritura("pausar eventos"):
            return
        
        db.cambiar_estado_evento(evento['id'], "pausado", self.usuario_actual['id'])
        self.mostrar_eventos()
    
    def reanudar_evento(self, evento):
        """Reanudar evento pausado"""
        db.cambiar_estado_evento(evento['id'], "activo", self.usuario_actual['id'])
        self.mostrar_eventos()
    
    def finalizar_evento(self, evento):
        """Finalizar evento con opción de exportar"""
        if not self.validar_accion_escritura("finalizar eventos"):
            return
        
        d = ctk.CTkToplevel(self)
        d.title("Finalizar Evento")
        d.geometry("500x350")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 250
        y = (d.winfo_screenheight() // 2) - 175
        d.geometry(f"500x350+{x}+{y}")
        
        ctk.CTkLabel(d, text="⚠️", font=("Arial", 60)).pack(pady=(35, 15))
        ctk.CTkLabel(d, text="¿Finalizar Evento?", font=("Arial", 22, "bold")).pack(pady=8)
        ctk.CTkLabel(d, text="Esta acción no se puede deshacer.\nEl evento quedará en modo solo lectura.",
                    font=("Arial", 13), text_color=COLORS["text_light"],
                    justify="center").pack(pady=20)
        
        def confirmar():
            db.cambiar_estado_evento(evento['id'], "finalizado", self.usuario_actual['id'])
            d.destroy()
            self.mostrar_eventos()
            # Abrir reporte automáticamente al finalizar
            self.after(300, lambda: self.ver_reporte_evento(evento))
        
        btn_frame = ctk.CTkFrame(d, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        ctk.CTkButton(btn_frame, text="Sí, Finalizar", command=confirmar, width=160, height=50,
                     fg_color=COLORS["danger"], hover_color="#c53030",
                     font=("Arial", 14, "bold")).pack(side="left", padx=8)
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=d.destroy, width=160, height=50,
                     fg_color="transparent", border_width=2, 
                     border_color=COLORS["border"]).pack(side="left", padx=8)
    
    def ver_reporte_evento(self, evento):
        """Abrir ventana de reporte post-evento"""
        from modules.reporte_evento import ReporteEvento
        try:
            ReporteEvento(self, evento)
        except Exception as e:
            self.mostrar_mensaje("Error", f"No se pudo abrir el reporte:\n{str(e)}", "error")

    def editar_evento(self, evento):
        """Formulario editar evento"""
        if not self.validar_accion_escritura("editar eventos"):
            return
        
        d = ctk.CTkToplevel(self)
        d.title("Editar Evento")
        d.geometry("600x650")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 300
        y = (d.winfo_screenheight() // 2) - 325
        d.geometry(f"600x650+{x}+{y}")
        
        scroll = ctk.CTkScrollableFrame(d, fg_color=COLORS["bg"])
        scroll.pack(fill="both", expand=True, padx=30, pady=30)
        
        ctk.CTkLabel(scroll, text="Editar Evento", 
                    font=("Arial", 26, "bold")).pack(pady=(0, 25))
        
        # Nombre
        ctk.CTkLabel(scroll, text="Nombre del Evento *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_nombre = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_nombre.pack(fill="x", pady=(8, 12))
        e_nombre.insert(0, evento['nombre'])
        
        # Fecha
        ctk.CTkLabel(scroll, text="Fecha del Evento *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_fecha = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_fecha.pack(fill="x", pady=(8, 12))
        e_fecha.insert(0, evento['fecha_evento'])
        
        # Hora inicio
        ctk.CTkLabel(scroll, text="Hora de Inicio (HH:MM) *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_hora = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_hora.pack(fill="x", pady=(8, 12))
        if evento.get('hora_inicio'):
            e_hora.insert(0, evento['hora_inicio'])
        
        # Hora límite
        ctk.CTkLabel(scroll, text="Hora Límite Acreditación (HH:MM) - Opcional", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_limite = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_limite.pack(fill="x", pady=(8, 12))
        if evento.get('hora_limite_acreditacion'):
            e_limite.insert(0, evento['hora_limite_acreditacion'])
        
        # Video Loop
        ctk.CTkLabel(scroll, text="Video Loop (opcional)", anchor="w", font=("Arial", 13)).pack(fill="x")
        
        video_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        video_frame.pack(fill="x", pady=(8, 25))
        
        e_video = ctk.CTkEntry(video_frame, height=45, font=("Arial", 14),
                              fg_color=COLORS["card"], placeholder_text="Sin video")
        e_video.pack(side="left", fill="x", expand=True)
        if evento.get('video_loop'):
            e_video.insert(0, evento['video_loop'])
        
        def seleccionar_video():
            filepath = filedialog.askopenfilename(
                title="Seleccionar Video Loop",
                filetypes=[("Videos", "*.mp4 *.avi *.mov *.mkv"), ("Todos", "*.*")]
            )
            if filepath:
                e_video.delete(0, 'end')
                e_video.insert(0, filepath)
        
        ctk.CTkButton(video_frame, text="📁", command=seleccionar_video,
                     width=60, height=45, font=("Arial", 18)).pack(side="left", padx=5)
        
        # ── Al acreditar ────────────────────────────────────────────
        ctk.CTkFrame(scroll, height=2, fg_color=COLORS["border"]).pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(scroll, text="Al acreditar un invitado", anchor="w",
                     font=("Arial", 13, "bold")).pack(fill="x")
        ctk.CTkLabel(scroll,
                     text="Podés activar uno, ambos o ninguno.",
                     anchor="w", font=("Arial", 11),
                     text_color=COLORS["text_light"]).pack(fill="x", pady=(2, 10))

        # ── Opción 1: Loop de Mesa ──
        usar_video_mesa_var = ctk.BooleanVar(value=bool(evento.get('usar_video_mesa', 1)))
        ctk.CTkCheckBox(scroll,
                        text="🎬  Loop de Mesa  (reproduce el video asignado a la mesa)",
                        variable=usar_video_mesa_var,
                        font=("Arial", 13)).pack(anchor="w", pady=(0, 4))

        ctk.CTkButton(scroll, text="   Configurar videos por mesa",
                      command=lambda: self.configurar_videos_mesa(evento),
                      height=36, font=("Arial", 12),
                      fg_color=COLORS["border"],
                      text_color=COLORS["text_light"],
                      anchor="w").pack(fill="x", padx=(24, 0), pady=(0, 10))

        # ── Opción 2: Splash de Mesa ──
        mostrar_bienvenida_var = ctk.BooleanVar(value=bool(evento.get('mostrar_bienvenida', 1)))
        ctk.CTkCheckBox(scroll,
                        text="🟢  Splash de Mesa  (muestra nombre + mesa en pantalla)",
                        variable=mostrar_bienvenida_var,
                        font=("Arial", 13)).pack(anchor="w", pady=(0, 4))

        mostrar_mesa_var = ctk.BooleanVar(value=bool(evento.get('mostrar_mesa', 1)))
        ctk.CTkCheckBox(scroll, text="Incluir número de mesa en el splash",
                        variable=mostrar_mesa_var,
                        font=("Arial", 12),
                        text_color=COLORS["text_light"]).pack(anchor="w", padx=(24, 0), pady=(0, 8))
        
        # Separador
        ctk.CTkFrame(scroll, height=2, fg_color=COLORS["border"]).pack(fill="x", pady=15)
        
        # CONFIGURACIÓN FIJA: 1 kiosco horizontal (no editable)
        num_kioscos = ctk.IntVar(value=1)
        orientacion = ctk.StringVar(value='horizontal')
        
        def guardar():
            nombre = e_nombre.get().strip()
            fecha = e_fecha.get().strip()
            hora = e_hora.get().strip()
            
            if not nombre or not fecha or not hora:
                self.mostrar_mensaje("Error", "Nombre, fecha y hora son obligatorios", "error")
                return
            
            # Actualizar evento
            db.connect()
            try:
                db.cursor.execute("""
                    UPDATE eventos
                    SET nombre = ?, fecha_evento = ?, hora_inicio = ?,
                        hora_limite_acreditacion = ?, video_loop = ?, mostrar_mesa = ?,
                        mostrar_bienvenida = ?, usar_video_mesa = ?
                    WHERE id = ?
                """, (nombre, fecha, hora,
                      e_limite.get().strip() if e_limite.get().strip() else None,
                      e_video.get().strip() if e_video.get().strip() else None,
                      1 if mostrar_mesa_var.get() else 0,
                      1 if mostrar_bienvenida_var.get() else 0,
                      1 if usar_video_mesa_var.get() else 0,
                      evento['id']))
                
                db.connection.commit()
                d.destroy()
                self.mostrar_mensaje("Éxito", f"Evento '{nombre}' actualizado", "success")
                self.mostrar_eventos()
            except Exception as e:
                self.mostrar_mensaje("Error", f"Error al actualizar: {str(e)}", "error")
            finally:
                db.disconnect()
        
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=15)
        
        ctk.CTkButton(btn_frame, text="Guardar Cambios", command=guardar, height=50,
                     font=("Arial", 15, "bold"), fg_color=COLORS["primary"]).pack(fill="x", pady=(0, 8))
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=d.destroy, height=48,
                     fg_color="transparent", border_width=2, 
                     border_color=COLORS["border"]).pack(fill="x")
    
    def configurar_videos_mesa(self, evento):
        """Configurar videos por mesa - UI completa"""
        if not self.validar_accion_escritura("editar videos"):
            return

        d = ctk.CTkToplevel(self)
        d.title("Videos por Mesa")
        d.geometry("900x700")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 450
        y = (d.winfo_screenheight() // 2) - 350
        d.geometry(f"900x700+{x}+{y}")
        
        main = ctk.CTkFrame(d, fg_color=COLORS["bg"])
        main.pack(fill="both", expand=True, padx=30, pady=30)
        
        # Header
        ctk.CTkLabel(main, text=f"🎬 Videos por Mesa", 
                    font=("Arial", 26, "bold")).pack(pady=(0, 5))
        
        ctk.CTkLabel(main, text=f"Evento: {evento['nombre']}", 
                    font=("Arial", 14), text_color=COLORS["text_light"]).pack(pady=(0, 20))
        
        # Info
        info_frame = ctk.CTkFrame(main, fg_color=COLORS["card"], corner_radius=8)
        info_frame.pack(fill="x", pady=(0, 20))
        
        info_inner = ctk.CTkFrame(info_frame, fg_color="transparent")
        info_inner.pack(padx=15, pady=12)
        
        ctk.CTkLabel(info_inner, text="💡 Cada invitado verá el video de su mesa al acreditarse", 
                    font=("Arial", 12), text_color=COLORS["text_light"]).pack()
        ctk.CTkLabel(info_inner, text="Si un invitado tiene video personalizado, ese tiene prioridad", 
                    font=("Arial", 11), text_color=COLORS["text_light"]).pack()
        
        # Obtener mesas del evento
        invitados = db.obtener_invitados_evento(evento['id'])
        mesas_evento = sorted(set(inv['mesa'] for inv in invitados if inv.get('mesa')))
        
        if not mesas_evento:
            ctk.CTkLabel(main, text="⚠️ No hay invitados con mesas asignadas en este evento", 
                        font=("Arial", 15), text_color=COLORS["warning"]).pack(pady=40)
            
            ctk.CTkLabel(main, text="Primero agrega invitados y asígna les mesas", 
                        font=("Arial", 13), text_color=COLORS["text_light"]).pack()
            
            ctk.CTkButton(main, text="Cerrar", command=d.destroy,
                         height=50, width=200).pack(pady=30)
            return
        
        # Obtener videos actuales
        videos_actuales = db.obtener_videos_mesa(evento['id'])
        
        # Stats
        stats_text = f"📊 Mesas detectadas: {len(mesas_evento)} • "
        stats_text += f"Videos configurados: {len(videos_actuales)}"
        
        ctk.CTkLabel(main, text=stats_text, 
                    font=("Arial", 13, "bold"), text_color=COLORS["primary"]).pack(pady=(0, 15))
        
        # Frame scrollable para mesas
        scroll = ctk.CTkScrollableFrame(main, fg_color=COLORS["bg"], height=350)
        scroll.pack(fill="both", expand=True, pady=(0, 15))
        
        # Diccionario para almacenar paths
        video_vars = {}
        
        # Crear entrada por cada mesa
        for mesa in mesas_evento:
            # Contar invitados de esta mesa
            invitados_mesa = len([i for i in invitados if i.get('mesa') == mesa])
            
            mesa_frame = ctk.CTkFrame(scroll, fg_color=COLORS["card"], corner_radius=8)
            mesa_frame.pack(fill="x", pady=6)
            
            inner = ctk.CTkFrame(mesa_frame, fg_color="transparent")
            inner.pack(fill="x", padx=15, pady=12)
            
            # Label con info de mesa
            label_text = f"Mesa {mesa} ({invitados_mesa} invitado{'s' if invitados_mesa != 1 else ''})"
            ctk.CTkLabel(inner, text=label_text, 
                        font=("Arial", 14, "bold"), width=150, anchor="w").pack(side="left")
            
            # Entry para path
            video_vars[mesa] = ctk.StringVar(value=videos_actuales.get(mesa, ""))
            
            entry = ctk.CTkEntry(inner, textvariable=video_vars[mesa],
                                height=40, font=("Arial", 12),
                                placeholder_text="Sin video asignado",
                                fg_color=COLORS["bg"])
            entry.pack(side="left", fill="x", expand=True, padx=10)
            
            # Botones
            btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
            btn_frame.pack(side="left")
            
            def seleccionar(m=mesa):
                filepath = filedialog.askopenfilename(
                    title=f"Video para Mesa {m}",
                    filetypes=[("Videos", "*.mp4 *.avi *.mov *.mkv"), ("Todos", "*.*")]
                )
                if filepath:
                    video_vars[m].set(filepath)
            
            ctk.CTkButton(btn_frame, text="📁 Seleccionar", command=seleccionar,
                         width=120, height=45, font=("Arial", 13, "bold"),
                         fg_color=COLORS["primary"]).pack(side="left", padx=5)
            
            def limpiar(m=mesa):
                video_vars[m].set("")
            
            ctk.CTkButton(btn_frame, text="🗑️ Borrar", command=limpiar,
                         width=100, height=45, fg_color=COLORS["danger"],
                         font=("Arial", 13, "bold")).pack(side="left", padx=5)
        
        def guardar_todos():
            # Recopilar videos
            videos_mesa = {}
            for mesa, var in video_vars.items():
                path = var.get().strip()
                if path:
                    videos_mesa[mesa] = path
            
            # Guardar en BD
            resultado = db.guardar_videos_mesa(evento['id'], videos_mesa)
            
            if resultado['success']:
                d.destroy()
                self.mostrar_mensaje("Éxito", 
                                   f"Videos configurados para {len(videos_mesa)} mesas", 
                                   "success")
            else:
                self.mostrar_mensaje("Error", f"Error: {resultado['error']}", "error")
        
        # Botones finales
        btn_final = ctk.CTkFrame(main, fg_color="transparent")
        btn_final.pack(fill="x", pady=(10, 0))
        
        ctk.CTkButton(btn_final, text="💾 Guardar Configuración",
                     command=guardar_todos,
                     height=55, font=("Arial", 16, "bold"),
                     fg_color=COLORS["success"]).pack(fill="x", pady=(0, 10))
        
        ctk.CTkButton(btn_final, text="Cancelar", command=d.destroy,
                     height=50, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"]).pack(fill="x")
    
    def eliminar_evento(self, evento):
        """Eliminar evento"""
        if not self.validar_accion_escritura("eliminar eventos"):
            return
        
        d = ctk.CTkToplevel(self)
        d.title("Eliminar Evento")
        d.geometry("450x280")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 225
        y = (d.winfo_screenheight() // 2) - 140
        d.geometry(f"450x280+{x}+{y}")
        
        ctk.CTkLabel(d, text="🗑️", font=("Arial", 55)).pack(pady=(30, 15))
        ctk.CTkLabel(d, text="¿Eliminar Evento?", font=("Arial", 20, "bold")).pack(pady=8)
        ctk.CTkLabel(d, text="Se eliminarán todos los invitados,\nacreditaciones y sorteos.",
                    font=("Arial", 13), text_color=COLORS["text_light"],
                    justify="center").pack(pady=18)
        
        def confirmar():
            resultado = db.eliminar_evento(evento['id'])
            d.destroy()
            if resultado["success"]:
                self.mostrar_mensaje("Éxito", "Evento eliminado", "success")
                self.mostrar_eventos()
            else:
                self.mostrar_mensaje("Error", resultado.get("error"), "error")
        
        btn_frame = ctk.CTkFrame(d, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        ctk.CTkButton(btn_frame, text="Eliminar", command=confirmar, width=150, height=48,
                     fg_color=COLORS["danger"]).pack(side="left", padx=6)
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=d.destroy, width=150, height=48,
                     fg_color="transparent", border_width=2,
                     border_color=COLORS["border"]).pack(side="left", padx=6)
    
    # ============================================
    # INVITADOS
    # ============================================
    
    def ver_invitados(self, evento):
        """Ver invitados del evento"""
        self.evento_activo = evento
        
        for w in self.content.winfo_children():
            w.destroy()
        
        # Header con botón atrás
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", pady=(0, 25))
        
        ctk.CTkButton(header, text="← Atrás", command=self.mostrar_eventos,
                     width=110, height=45, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"],
                     font=("Arial", 14)).pack(side="left")

        # Botones RIGHT primero para que siempre tengan espacio
        if self.tiene_permiso('agregar_invitados') and not self.es_modo_demo():
            btn_group = ctk.CTkFrame(header, fg_color="transparent")
            btn_group.pack(side="right")

            ctk.CTkButton(btn_group, text="➕ Agregar", command=self.agregar_invitado,
                         height=45, width=140, fg_color=COLORS["success"],
                         font=("Arial", 14)).pack(side="left", padx=5)

            if self.tiene_permiso('importar_excel'):
                ctk.CTkButton(btn_group, text="📤 Importar Excel", command=self.importar_excel,
                             height=45, width=160, font=("Arial", 14)).pack(side="left", padx=5)

            ctk.CTkButton(btn_group, text="🎨 Invitaciones", command=self.generar_invitaciones_dialog,
                         height=45, width=160, fg_color=COLORS["primary"],
                         font=("Arial", 14)).pack(side="left", padx=5)

        ctk.CTkLabel(header, text=f"Invitados: {evento['nombre']}",
                    font=("Arial", 30, "bold")).pack(side="left", padx=25)
        
        # Obtener invitados
        invitados_todos = db.obtener_invitados_evento(evento['id'])
        
        # BÚSQUEDA Y FILTROS
        search_frame = ctk.CTkFrame(self.content, fg_color=COLORS["card"], corner_radius=10)
        search_frame.pack(fill="x", pady=(0, 15))
        
        search_inner = ctk.CTkFrame(search_frame, fg_color="transparent")
        search_inner.pack(fill="x", padx=20, pady=15)
        
        # Barra de búsqueda
        search_container = ctk.CTkFrame(search_inner, fg_color="transparent")
        search_container.pack(side="left", fill="x", expand=True)
        
        ctk.CTkLabel(search_container, text="🔍", font=("Arial", 18)).pack(side="left", padx=(0, 8))
        
        search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(search_container, textvariable=search_var,
                                    placeholder_text="Buscar por nombre o apellido...",
                                    height=40, font=("Arial", 14))
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, 15))
        
        # Filtros
        filtro_mesa_var = ctk.StringVar(value="todas")
        filtro_presente_var = ctk.StringVar(value="todos")
        
        # Filtro por mesa
        ctk.CTkLabel(search_inner, text="Mesa:", font=("Arial", 13)).pack(side="left", padx=(15, 5))
        
        mesas_unicas = sorted(set([str(i.get('mesa', '')) for i in invitados_todos if i.get('mesa')]))
        mesas_opciones = ["Todas"] + mesas_unicas
        
        filtro_mesa = ctk.CTkOptionMenu(search_inner, values=mesas_opciones,
                                        variable=filtro_mesa_var,
                                        width=100, height=40,
                                        font=("Arial", 13))
        filtro_mesa.pack(side="left", padx=5)
        filtro_mesa.set("Todas")
        
        # Filtro por estado
        ctk.CTkLabel(search_inner, text="Estado:", font=("Arial", 13)).pack(side="left", padx=(15, 5))
        
        filtro_presente = ctk.CTkOptionMenu(search_inner, 
                                           values=["Todos", "Acreditados", "Sin acreditar"],
                                           variable=filtro_presente_var,
                                           width=140, height=40,
                                           font=("Arial", 13))
        filtro_presente.pack(side="left", padx=5)
        filtro_presente.set("Todos")
        
        # Frame para lista de invitados (se actualizará con búsqueda)
        lista_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        lista_frame.pack(fill="both", expand=True)
        
        # Stats (se actualizarán con búsqueda)
        stats_frame = ctk.CTkFrame(self.content, fg_color=COLORS["card"], corner_radius=10)
        stats_frame.pack(fill="x", pady=(0, 20), before=lista_frame)
        
        stats_label = ctk.CTkLabel(stats_frame, text="", font=("Arial", 15))
        stats_label.pack(padx=25, pady=18)
        
        # Función para actualizar lista
        def actualizar_lista():
            # Limpiar lista actual
            for w in lista_frame.winfo_children():
                w.destroy()
            
            # Obtener valores de búsqueda y filtros
            busqueda = search_var.get().lower().strip()
            mesa_seleccionada = filtro_mesa_var.get()
            estado_seleccionado = filtro_presente_var.get()
            
            # Filtrar invitados
            invitados_filtrados = invitados_todos.copy()
            
            # Filtro por búsqueda (múltiples palabras, orden flexible)
            if busqueda:
                # Separar términos de búsqueda
                terminos = busqueda.split()

                def coincide_invitado(inv):
                    # Concatenar nombre y apellido para búsqueda flexible
                    texto_completo = f"{inv['nombre'].lower()} {inv['apellido'].lower()}"
                    # Cada término debe aparecer en alguna parte del nombre completo
                    return all(termino in texto_completo for termino in terminos)

                invitados_filtrados = [i for i in invitados_filtrados if coincide_invitado(i)]
            
            # Filtro por mesa
            if mesa_seleccionada != "Todas":
                invitados_filtrados = [
                    i for i in invitados_filtrados
                    if str(i.get('mesa', '')) == mesa_seleccionada
                ]
            
            # Filtro por estado
            if estado_seleccionado == "Acreditados":
                invitados_filtrados = [i for i in invitados_filtrados if i.get('presente')]
            elif estado_seleccionado == "Sin acreditar":
                invitados_filtrados = [i for i in invitados_filtrados if not i.get('presente')]
            
            # Actualizar stats
            total_filtrados = len(invitados_filtrados)
            presentes_filtrados = len([i for i in invitados_filtrados if i.get('presente')])
            
            stats_text = f"📊 Mostrando: {total_filtrados} invitados"
            if presentes_filtrados > 0:
                stats_text += f"  |  ✅ Acreditados: {presentes_filtrados}"
            if busqueda or mesa_seleccionada != "Todas" or estado_seleccionado != "Todos":
                stats_text += f"  |  Total general: {len(invitados_todos)}"
            
            stats_label.configure(text=stats_text)
            
            # Mostrar invitados filtrados
            if not invitados_filtrados:
                ctk.CTkLabel(lista_frame, 
                            text="No se encontraron invitados con esos criterios.",
                            font=("Arial", 16), text_color=COLORS["text_light"]).pack(expand=True, pady=50)
            else:
                for inv in invitados_filtrados:
                    self.crear_card_invitado(inv, lista_frame)
        
        # Conectar búsqueda y filtros
        search_var.trace_add('write', lambda *args: actualizar_lista())
        filtro_mesa_var.trace_add('write', lambda *args: actualizar_lista())
        filtro_presente_var.trace_add('write', lambda *args: actualizar_lista())
        
        # Mostrar inicial
        actualizar_lista()
    
    def crear_card_invitado(self, inv, parent=None):
        """Card de invitado"""
        if parent is None:
            parent = self.content
            
        card = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=8)
        card.pack(fill="x", pady=4)
        
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=14)
        
        nombre_completo = f"{inv['apellido']}, {inv['nombre']}"
        ctk.CTkLabel(inner, text=nombre_completo, font=("Arial", 16, "bold")).pack(side="left")
        
        if inv.get('mesa'):
            ctk.CTkLabel(inner, text=f"Mesa: {inv['mesa']}", font=("Arial", 13),
                        fg_color=COLORS["primary"], corner_radius=6,
                        width=80, height=28).pack(side="left", padx=12)
        
        if inv.get('observaciones'):
            ctk.CTkLabel(inner, text=f"📝 {inv['observaciones'][:30]}", 
                        font=("Arial", 11), text_color=COLORS["text_light"]).pack(side="left", padx=10)
        
        if inv.get('presente'):
            ctk.CTkLabel(inner, text="✅ Presente", text_color=COLORS["success"],
                        font=("Arial", 13, "bold")).pack(side="left", padx=12)
        
        # Botones de acción (ocultos en modo demo)
        if self.tiene_permiso('editar_invitados') and not self.es_modo_demo():
            ctk.CTkButton(inner, text="📧", command=lambda: self.generar_invitacion_individual(inv),
                         width=40, height=32, font=("Arial", 14),
                         fg_color="#10b981",
                         hover_color="#059669").pack(side="right", padx=2)

            ctk.CTkButton(inner, text="✏️", command=lambda: self.editar_invitado(inv),
                         width=40, height=32, font=("Arial", 14),
                         fg_color=COLORS["primary"]).pack(side="right", padx=2)

        if self.tiene_permiso('eliminar_invitados') and not self.es_modo_demo():
            ctk.CTkButton(inner, text="🗑️", command=lambda: self.eliminar_invitado(inv),
                         width=40, height=32, font=("Arial", 14),
                         fg_color=COLORS["danger"]).pack(side="right", padx=2)
        
        # QR Code
        ctk.CTkLabel(inner, text=f"QR: {inv.get('qr_code', 'N/A')}", font=("Arial", 10),
                    text_color=COLORS["text_light"]).pack(side="right")
    
    def agregar_invitado(self):
        """Formulario agregar invitado"""
        if not self.validar_accion_escritura("agregar invitados"):
            return
        
        d = ctk.CTkToplevel(self)
        d.title("Agregar Invitado")
        d.geometry("600x700")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 300
        y = (d.winfo_screenheight() // 2) - 350
        d.geometry(f"600x700+{x}+{y}")
        
        scroll = ctk.CTkScrollableFrame(d, fg_color=COLORS["bg"])
        scroll.pack(fill="both", expand=True, padx=30, pady=30)
        
        ctk.CTkLabel(scroll, text="Agregar Invitado", 
                    font=("Arial", 26, "bold")).pack(pady=(0, 25))
        
        # Nombre
        ctk.CTkLabel(scroll, text="Nombre *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_nombre = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_nombre.pack(fill="x", pady=(8, 12))
        
        # Apellido
        ctk.CTkLabel(scroll, text="Apellido *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_apellido = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_apellido.pack(fill="x", pady=(8, 12))
        
        # Mesa
        ctk.CTkLabel(scroll, text="Mesa *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_mesa = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_mesa.pack(fill="x", pady=(8, 12))
        
        # Observaciones
        ctk.CTkLabel(scroll, text="Observaciones", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_obs = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_obs.pack(fill="x", pady=(8, 12))
        
        # Video personalizado
        ctk.CTkLabel(scroll, text="Video Personalizado (opcional)", anchor="w", 
                    font=("Arial", 13)).pack(fill="x")
        
        video_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        video_frame.pack(fill="x", pady=(8, 25))
        
        e_video = ctk.CTkEntry(video_frame, height=45, font=("Arial", 14), 
                              fg_color=COLORS["card"], placeholder_text="Sin video")
        e_video.pack(side="left", fill="x", expand=True)
        
        def seleccionar_video():
            filepath = filedialog.askopenfilename(
                title="Seleccionar Video",
                filetypes=[("Videos", "*.mp4 *.avi *.mov *.mkv"), ("Todos", "*.*")]
            )
            if filepath:
                e_video.delete(0, 'end')
                e_video.insert(0, filepath)
        
        ctk.CTkButton(video_frame, text="📁", command=seleccionar_video,
                     width=60, height=45, font=("Arial", 18)).pack(side="left", padx=5)
        
        def guardar():
            nombre = e_nombre.get().strip()
            apellido = e_apellido.get().strip()
            mesa = e_mesa.get().strip()
            
            if not nombre or not apellido or not mesa:
                self.mostrar_mensaje("Error", "Nombre, apellido y mesa son obligatorios", "error")
                return
            
            if not mesa.isdigit():
                self.mostrar_mensaje("Error", "Mesa debe ser un número", "error")
                return
            
            resultado = db.agregar_invitado(
                evento_id=self.evento_activo['id'],
                nombre=nombre,
                apellido=apellido,
                mesa=int(mesa),
                observaciones=e_obs.get().strip() if e_obs.get().strip() else None,
                video_personalizado=e_video.get().strip() if e_video.get().strip() else None
            )
            
            if resultado["success"]:
                d.destroy()
                self.mostrar_mensaje("Éxito", f"Invitado '{nombre} {apellido}' agregado correctamente", "success")
                self.ver_invitados(self.evento_activo)
            else:
                self.mostrar_mensaje("Error", resultado.get("error", "Error al agregar"), "error")
        
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=15)
        
        ctk.CTkButton(btn_frame, text="Guardar", command=guardar, height=50,
                     font=("Arial", 15, "bold"), fg_color=COLORS["success"]).pack(fill="x", pady=(0, 8))
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=d.destroy, height=48,
                     fg_color="transparent", border_width=2, 
                     border_color=COLORS["border"]).pack(fill="x")
    
    def editar_invitado(self, invitado):
        """Formulario editar invitado"""
        if not self.validar_accion_escritura("editar invitados"):
            return
        
        d = ctk.CTkToplevel(self)
        d.title("Editar Invitado")
        d.geometry("600x700")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 300
        y = (d.winfo_screenheight() // 2) - 350
        d.geometry(f"600x700+{x}+{y}")
        
        scroll = ctk.CTkScrollableFrame(d, fg_color=COLORS["bg"])
        scroll.pack(fill="both", expand=True, padx=30, pady=30)
        
        ctk.CTkLabel(scroll, text="Editar Invitado", 
                    font=("Arial", 26, "bold")).pack(pady=(0, 25))
        
        # Nombre
        ctk.CTkLabel(scroll, text="Nombre *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_nombre = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_nombre.pack(fill="x", pady=(8, 12))
        e_nombre.insert(0, invitado['nombre'])
        
        # Apellido
        ctk.CTkLabel(scroll, text="Apellido *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_apellido = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_apellido.pack(fill="x", pady=(8, 12))
        e_apellido.insert(0, invitado['apellido'])
        
        # Mesa
        ctk.CTkLabel(scroll, text="Mesa *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_mesa = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_mesa.pack(fill="x", pady=(8, 12))
        if invitado.get('mesa'):
            e_mesa.insert(0, str(invitado['mesa']))
        
        # Observaciones
        ctk.CTkLabel(scroll, text="Observaciones", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_obs = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_obs.pack(fill="x", pady=(8, 12))
        if invitado.get('observaciones'):
            e_obs.insert(0, invitado['observaciones'])
        
        # Video personalizado
        ctk.CTkLabel(scroll, text="Video Personalizado (opcional)", anchor="w", 
                    font=("Arial", 13)).pack(fill="x")
        
        video_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        video_frame.pack(fill="x", pady=(8, 25))
        
        e_video = ctk.CTkEntry(video_frame, height=45, font=("Arial", 14), 
                              fg_color=COLORS["card"], placeholder_text="Sin video")
        e_video.pack(side="left", fill="x", expand=True)
        if invitado.get('video_personalizado'):
            e_video.insert(0, invitado['video_personalizado'])
        
        def seleccionar_video():
            filepath = filedialog.askopenfilename(
                title="Seleccionar Video",
                filetypes=[("Videos", "*.mp4 *.avi *.mov *.mkv"), ("Todos", "*.*")]
            )
            if filepath:
                e_video.delete(0, 'end')
                e_video.insert(0, filepath)
        
        ctk.CTkButton(video_frame, text="📁", command=seleccionar_video,
                     width=60, height=45, font=("Arial", 18)).pack(side="left", padx=5)
        
        def guardar():
            nombre = e_nombre.get().strip()
            apellido = e_apellido.get().strip()
            mesa = e_mesa.get().strip()
            
            if not nombre or not apellido or not mesa:
                self.mostrar_mensaje("Error", "Nombre, apellido y mesa son obligatorios", "error")
                return
            
            if not mesa.isdigit():
                self.mostrar_mensaje("Error", "Mesa debe ser un número", "error")
                return
            
            # Actualizar invitado
            db.connect()
            try:
                db.cursor.execute("""
                    UPDATE invitados 
                    SET nombre = ?, apellido = ?, mesa = ?, observaciones = ?, video_personalizado = ?
                    WHERE id = ?
                """, (nombre, apellido, int(mesa), 
                      e_obs.get().strip() if e_obs.get().strip() else None,
                      e_video.get().strip() if e_video.get().strip() else None,
                      invitado['id']))
                
                db.connection.commit()
                d.destroy()
                self.mostrar_mensaje("Éxito", f"Invitado '{nombre} {apellido}' actualizado", "success")
                self.ver_invitados(self.evento_activo)
            except Exception as e:
                self.mostrar_mensaje("Error", f"Error al actualizar: {str(e)}", "error")
            finally:
                db.disconnect()
        
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=15)
        
        ctk.CTkButton(btn_frame, text="Guardar Cambios", command=guardar, height=50,
                     font=("Arial", 15, "bold"), fg_color=COLORS["primary"]).pack(fill="x", pady=(0, 8))
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=d.destroy, height=48,
                     fg_color="transparent", border_width=2, 
                     border_color=COLORS["border"]).pack(fill="x")
    
    def eliminar_invitado(self, invitado):
        """Eliminar un invitado individual"""
        if not self.validar_accion_escritura("eliminar invitados"):
            return
        
        # Diálogo de confirmación
        d = ctk.CTkToplevel(self)
        d.title("Confirmar Eliminación")
        d.geometry("500x300")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 250
        y = (d.winfo_screenheight() // 2) - 150
        d.geometry(f"500x300+{x}+{y}")
        
        container = ctk.CTkFrame(d, fg_color=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=30, pady=30)
        
        # Icono de advertencia
        ctk.CTkLabel(container, text="⚠️", font=("Arial", 60)).pack(pady=(0, 15))
        
        ctk.CTkLabel(container, text="¿Eliminar invitado?", 
                    font=("Arial", 22, "bold")).pack(pady=(0, 10))
        
        nombre_completo = f"{invitado['nombre']} {invitado['apellido']}"
        ctk.CTkLabel(container, text=nombre_completo, 
                    font=("Arial", 16), text_color=COLORS["text_light"]).pack(pady=(0, 5))
        
        if invitado.get('mesa'):
            ctk.CTkLabel(container, text=f"Mesa: {invitado['mesa']}", 
                        font=("Arial", 14), text_color=COLORS["text_light"]).pack(pady=(0, 20))
        
        ctk.CTkLabel(container, text="Esta acción no se puede deshacer", 
                    font=("Arial", 12), text_color=COLORS["warning"]).pack(pady=(0, 20))
        
        def confirmar_eliminacion():
            db.connect()
            try:
                db.cursor.execute("DELETE FROM invitados WHERE id = ?", (invitado['id'],))
                db.connection.commit()
                d.destroy()
                self.mostrar_mensaje("Éxito", f"Invitado '{nombre_completo}' eliminado", "success")
                self.ver_invitados(self.evento_activo)
            except Exception as e:
                self.mostrar_mensaje("Error", f"Error al eliminar: {str(e)}", "error")
            finally:
                db.disconnect()
        
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(10, 0))
        
        ctk.CTkButton(btn_frame, text="❌ Sí, eliminar", command=confirmar_eliminacion,
                     height=50, font=("Arial", 15, "bold"),
                     fg_color=COLORS["danger"], hover_color="#b91c1c").pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=d.destroy,
                     height=50, font=("Arial", 15),
                     fg_color="transparent", border_width=2,
                     border_color=COLORS["border"]).pack(side="left", fill="x", expand=True, padx=(5, 0))
    
    def importar_excel(self):
        """Importar invitados desde Excel"""
        if not self.validar_accion_escritura("importar invitados"):
            return
        
        d = ctk.CTkToplevel(self)
        d.title("Importar desde Excel")
        d.geometry("600x400")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 300
        y = (d.winfo_screenheight() // 2) - 200
        d.geometry(f"600x400+{x}+{y}")
        
        container = ctk.CTkFrame(d, fg_color=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=35, pady=35)
        
        ctk.CTkLabel(container, text="📤 Importar Invitados desde Excel", 
                    font=("Arial", 24, "bold")).pack(pady=(0, 25))
        
        ctk.CTkLabel(container, text="El archivo Excel debe tener las columnas:",
                    font=("Arial", 14)).pack(pady=8)
        
        ctk.CTkLabel(container, text="Nombre, Apellido, Mesa, Observaciones",
                    font=("Arial", 13, "bold"), text_color=COLORS["primary"]).pack(pady=(0, 25))
        
        ctk.CTkLabel(container, text="• Mesa es obligatoria y debe ser un número\n• Observaciones es opcional",
                    font=("Arial", 12), text_color=COLORS["text_light"],
                    justify="left").pack(pady=10)
        
        def descargar_plantilla():
            filepath = filedialog.asksaveasfilename(
                title="Guardar Plantilla",
                defaultextension=".xlsx",
                filetypes=[("Excel", "*.xlsx")],
                initialfile="PLANTILLA_INVITADOS_WELCOMEX.xlsx"
            )
            
            if filepath:
                import shutil
                import os
                plantilla_origen = os.path.join(BASE_DIR, "PLANTILLA_INVITADOS_WELCOMEX.xlsx")
                
                if os.path.exists(plantilla_origen):
                    shutil.copy(plantilla_origen, filepath)
                    self.mostrar_mensaje("Éxito", "Plantilla descargada correctamente", "success")
                else:
                    self.mostrar_mensaje("Error", "Plantilla no encontrada", "error")
        
        ctk.CTkButton(container, text="📥 Descargar Plantilla", command=descargar_plantilla,
                     height=50, font=("Arial", 14), width=400,
                     fg_color=COLORS["warning"]).pack(pady=15)
        
        def seleccionar():
            filepath = filedialog.askopenfilename(
                title="Seleccionar archivo Excel",
                filetypes=[("Excel", "*.xlsx *.xls"), ("Todos", "*.*")]
            )
            
            if not filepath:
                return
            
            d.destroy()
            
            try:
                from modules.csv_importer import CSVImporter
                importer = CSVImporter(self.evento_activo['id'])
                resultado = importer.importar_archivo(filepath)
                
                if resultado["success"]:
                    mensaje = f"Importación completada!\n\nTotal: {resultado['total']}\nExitosos: {resultado['exitosos']}"
                    
                    if resultado.get('saltados'):
                        mensaje += f"\nSaltados: {len(resultado['saltados'])}"
                    
                    if resultado.get('errores'):
                        mensaje += f"\n\nErrores:\n"
                        for err in resultado['errores'][:5]:
                            mensaje += f"• {err}\n"
                        if len(resultado['errores']) > 5:
                            mensaje += f"... y {len(resultado['errores']) - 5} más"
                    
                    self.mostrar_mensaje("Importación Completada", mensaje, "success" if not resultado.get('errores') else "warning")
                    self.ver_invitados(self.evento_activo)
                else:
                    self.mostrar_mensaje("Error", resultado.get("error", "Error al importar"), "error")
            except Exception as e:
                self.mostrar_mensaje("Error", f"Error al importar: {str(e)}", "error")
        
        ctk.CTkButton(container, text="📂 Seleccionar Archivo Excel", command=seleccionar,
                     height=55, font=("Arial", 16, "bold"), width=400,
                     fg_color=COLORS["primary"]).pack(pady=20)
        
        ctk.CTkButton(container, text="Cancelar", command=d.destroy, height=50,
                     fg_color="transparent", border_width=2, 
                     border_color=COLORS["border"], width=400).pack(pady=10)
    
    # ============================================
    # SORTEOS
    # ============================================
    
    def ver_sorteos(self, evento):
        """Ver sorteos y ganadores"""
        self.evento_activo = evento

        for w in self.content.winfo_children():
            w.destroy()

        # Header
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", pady=(0, 25))

        ctk.CTkButton(header, text=t("sorteo.back"), command=self.mostrar_eventos,
                     width=110, height=45, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"],
                     font=("Arial", 14)).pack(side="left")

        ctk.CTkButton(header, text=f"🎰 {t('sorteo.start_raffle')}", command=self.realizar_sorteo,
                     height=50, width=200, fg_color=COLORS["success"],
                     font=("Arial", 15, "bold")).pack(side="right")

        ctk.CTkLabel(header, text=f"🎲 {t('sorteo.title')}",
                    font=("Arial", 30, "bold")).pack(side="left", padx=25)

        # Obtener ganadores
        ganadores = db.obtener_ganadores(evento['id'])

        ctk.CTkLabel(self.content, text=t("sorteo.historical", count=len(ganadores)),
                    font=("Arial", 18, "bold")).pack(anchor="w", pady=(0, 20))

        if ganadores:
            for ganador in ganadores:
                card = ctk.CTkFrame(self.content, fg_color=COLORS["card"], corner_radius=8)
                card.pack(fill="x", pady=4)

                inner = ctk.CTkFrame(card, fg_color="transparent")
                inner.pack(fill="x", padx=20, pady=14)

                ctk.CTkLabel(inner, text="🏆", font=("Arial", 24)).pack(side="left", padx=8)
                ctk.CTkLabel(inner, text=f"{ganador['apellido']}, {ganador['nombre']}",
                            font=("Arial", 16, "bold")).pack(side="left", padx=12)

                if ganador.get('mesa'):
                    ctk.CTkLabel(inner, text=f"Mesa: {ganador['mesa']}",
                                font=("Arial", 13)).pack(side="left")
        else:
            ctk.CTkLabel(self.content, text=t("sorteo.no_winners_yet"),
                        font=("Arial", 17), text_color=COLORS["text_light"],
                        justify="center").pack(expand=True, pady=80)
    
    def realizar_sorteo(self):
        """Diálogo para configurar sorteo"""
        if not self.validar_accion_escritura("realizar sorteos"):
            return

        participantes = db.obtener_invitados_presentes(self.evento_activo['id'])

        if not participantes:
            self.mostrar_mensaje(t("common.error"), t("sorteo.no_participants"), "error")
            return

        # Diálogo de configuración
        d = ctk.CTkToplevel(self)
        d.title(t("sorteo.config_title"))
        d.geometry("600x550")
        d.transient(self)
        d.grab_set()

        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 300
        y = (d.winfo_screenheight() // 2) - 275
        d.geometry(f"600x550+{x}+{y}")

        container = ctk.CTkFrame(d, fg_color=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=40, pady=40)

        ctk.CTkLabel(container, text=f"🎰 {t('sorteo.config_title')}",
                    font=("Arial", 28, "bold")).pack(pady=(0, 30))

        # Tipo de sorteo
        ctk.CTkLabel(container, text=t("sorteo.type_label"), anchor="w",
                    font=("Arial", 15, "bold")).pack(fill="x", pady=(0, 10))

        tipo_var = ctk.StringVar(value="general")

        ctk.CTkRadioButton(container, text=f"🌟 {t('sorteo.type_general')}",
                          variable=tipo_var, value="general",
                          font=("Arial", 14)).pack(anchor="w", pady=8)

        ctk.CTkRadioButton(container, text=f"🪑 {t('sorteo.type_per_table')}",
                          variable=tipo_var, value="por_mesa",
                          font=("Arial", 14)).pack(anchor="w", pady=8)

        # Número de ganadores
        ctk.CTkLabel(container, text=t("sorteo.num_winners"), anchor="w",
                    font=("Arial", 15, "bold")).pack(fill="x", pady=(20, 10))

        ganadores_frame = ctk.CTkFrame(container, fg_color="transparent")
        ganadores_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(ganadores_frame, text=t("sorteo.quantity"), font=("Arial", 13)).pack(side="left")

        spin_ganadores = ctk.CTkEntry(ganadores_frame, width=80, height=40,
                                       font=("Arial", 16), justify="center")
        spin_ganadores.pack(side="left", padx=10)
        spin_ganadores.insert(0, "1")

        ctk.CTkLabel(ganadores_frame, text=t("sorteo.quantity_range"),
                    font=("Arial", 12), text_color=COLORS["text_light"]).pack(side="left")

        # Excluir ganadores anteriores
        var_excluir = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(container, text=t("sorteo.exclude_previous"),
                       variable=var_excluir, font=("Arial", 13)).pack(anchor="w", pady=20)

        # Info
        info_label = ctk.CTkLabel(container, text=t("sorteo.eligible", count=len(participantes)),
                                 font=("Arial", 13), text_color=COLORS["primary"])
        info_label.pack(pady=10)

        def ejecutar_sorteo():
            tipo = tipo_var.get()

            try:
                cantidad = int(spin_ganadores.get())
                if cantidad < 1 or cantidad > 20:
                    raise ValueError()
            except (ValueError, TypeError):
                self.mostrar_mensaje(t("common.error"),
                    "Cantidad debe ser un número entre 1 y 20", "error")
                return

            excluir = var_excluir.get()
            d.destroy()

            if tipo == "general":
                self.sorteo_general(cantidad, excluir)
            else:
                self.sorteo_por_mesa(excluir)

        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=20)

        ctk.CTkButton(btn_frame, text=f"🎲 {t('sorteo.start_raffle')}", command=ejecutar_sorteo,
                     height=55, font=("Arial", 16, "bold"),
                     fg_color=COLORS["success"]).pack(fill="x", pady=(0, 10))

        ctk.CTkButton(btn_frame, text=t("common.cancel"), command=d.destroy,
                     height=50, fg_color="transparent", border_width=2,
                     border_color=COLORS["border"]).pack(fill="x")
    
    def sorteo_general(self, cantidad, excluir_previos):
        """Sorteo general entre todos"""
        import random

        participantes = db.obtener_invitados_presentes(self.evento_activo['id'])

        # Excluir ganadores previos si está activado
        if excluir_previos:
            ganadores_previos = db.obtener_ganadores(self.evento_activo['id'])
            ids_previos = [g['invitado_id'] for g in ganadores_previos]
            participantes = [p for p in participantes if p['id'] not in ids_previos]

        if len(participantes) < cantidad:
            self.mostrar_mensaje(t("common.error"),
                                t("sorteo.not_enough", count=len(participantes), needed=cantidad),
                                "error")
            return

        # Sortear
        ganadores = random.sample(participantes, cantidad)

        # Registrar en DB
        for ganador in ganadores:
            db.registrar_ganador(self.evento_activo['id'], ganador['id'], "general", ganador.get('mesa'))

        # Mostrar con animación (funciona para 1 o múltiples ganadores)
        def on_complete():
            self.after(100, lambda: self.ver_sorteos(self.evento_activo))

        SorteoAnimacion(self, participantes, ganadores, on_complete=on_complete)
    
    def sorteo_por_mesa(self, excluir_previos):
        """Sorteo de 1 ganador por cada mesa"""
        import random

        participantes = db.obtener_invitados_presentes(self.evento_activo['id'])

        # Excluir ganadores previos si está activado
        if excluir_previos:
            ganadores_previos = db.obtener_ganadores(self.evento_activo['id'])
            ids_previos = [g['invitado_id'] for g in ganadores_previos]
            participantes = [p for p in participantes if p['id'] not in ids_previos]

        # Agrupar por mesa
        mesas = {}
        for p in participantes:
            mesa = p.get('mesa')
            if mesa:
                if mesa not in mesas:
                    mesas[mesa] = []
                mesas[mesa].append(p)

        if not mesas:
            self.mostrar_mensaje(t("common.error"), t("sorteo.no_tables"), "error")
            return

        # Sortear 1 por mesa
        ganadores_dict = {}
        for mesa, personas in mesas.items():
            ganador = random.choice(personas)
            ganadores_dict[mesa] = ganador
            db.registrar_ganador(self.evento_activo['id'], ganador['id'], "por_mesa", mesa)

        # Mostrar con animación secuencial por mesa
        def on_complete():
            self.after(100, lambda: self.ver_sorteos(self.evento_activo))

        SorteoPorMesaAnimacion(self, mesas, ganadores_dict, on_complete=on_complete)
    
    
    # ============================================
    # KIOSCO
    # ============================================
    
    def abrir_kiosco(self, evento):
        """Abrir kiosco + panel de operador"""
        from modules.kiosco_ui import KioscoWindow
        from modules.operator_panel import OperatorPanel

        orientacion = 'horizontal'

        try:
            kiosco = KioscoWindow(self, evento, orientacion, kiosco_id=1)

            # Panel de operador (ventana secundaria, siempre al frente)
            try:
                OperatorPanel(self, evento, kiosco_window=kiosco)
            except Exception as pe:
                print(f"[OperatorPanel] No se pudo abrir: {pe}")

            kiosco.mainloop()
        except Exception as e:
            print(f"Error abriendo kiosco: {e}")
            import traceback
            traceback.print_exc()
            self.mostrar_mensaje("Error", f"Error al abrir kiosco:\n{str(e)}", "error")
    
    def mostrar_kiosco_operario(self):
        """Vista de kiosco para operario"""
        for w in self.content.winfo_children():
            w.destroy()
        
        ctk.CTkLabel(self.content, text="📱 Modo Kiosco", 
                    font=("Arial", 34, "bold")).pack(pady=(50, 20))
        
        ctk.CTkLabel(self.content, 
                    text="Selecciona un evento activo para comenzar a escanear",
                    font=("Arial", 16), text_color=COLORS["text_light"]).pack(pady=20)
        
        # Obtener eventos activos del admin
        if self.usuario_actual.get('admin_id'):
            eventos = db.obtener_eventos_usuario(self.usuario_actual['admin_id'])
            eventos_activos = [e for e in eventos if e['estado'] == 'activo']
            
            if eventos_activos:
                for evento in eventos_activos:
                    card = ctk.CTkFrame(self.content, fg_color=COLORS["card"], corner_radius=12)
                    card.pack(fill="x", pady=10, padx=50)
                    
                    inner = ctk.CTkFrame(card, fg_color="transparent")
                    inner.pack(fill="x", padx=25, pady=20)
                    
                    ctk.CTkLabel(inner, text=evento['nombre'], 
                                font=("Arial", 20, "bold")).pack(side="left")
                    
                    ctk.CTkButton(inner, text="🔍 Escanear", 
                                 command=lambda e=evento: self.abrir_kiosco(e),
                                 width=150, height=45, font=("Arial", 14),
                                 fg_color=COLORS["primary"]).pack(side="right")
            else:
                ctk.CTkLabel(self.content, text="No hay eventos activos disponibles",
                            font=("Arial", 16), text_color=COLORS["text_light"]).pack(pady=50)
    
    # ============================================
    # PANEL ADMIN (Super Admin)
    # ============================================
    
    # ============================================
    # PANEL ADMIN (DESHABILITADO - Gestión web futura)
    # ============================================
    
    # ============================================
    # PANEL ADMIN (DESHABILITADO)
    # ============================================
    # Gestión de licencias se hará desde panel web
    # Las funciones mostrar_admin, crear_licencia, ver_licencias
    # y configurar_planes han sido removidas
    
    # GENERADOR DE INVITACIONES
    # ============================================
        """Panel de administración"""
        for w in self.content.winfo_children():
            w.destroy()
        
        # Header
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", pady=(0, 25))
        
        ctk.CTkButton(header, text="← Atrás", command=self.mostrar_eventos,
                     width=110, height=45, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"],
                     font=("Arial", 14)).pack(side="left")
        
        ctk.CTkLabel(header, text="⚙️ Panel de Administrador", 
                    font=("Arial", 30, "bold")).pack(side="left", padx=25)
        
        # Botones principales
        actions = ctk.CTkFrame(self.content, fg_color="transparent")
        actions.pack(fill="x", pady=15)
        
        ctk.CTkButton(actions, text="➕ Crear Licencia", command=self.crear_licencia,
                     width=240, height=70, fg_color=COLORS["success"],
                     font=("Arial", 16, "bold")).pack(side="left", padx=12)
        
        ctk.CTkButton(actions, text="📋 Ver Licencias", command=self.ver_licencias,
                     width=240, height=70, font=("Arial", 16, "bold")).pack(side="left", padx=12)
        
        ctk.CTkButton(actions, text="⚙️ Configurar Planes", command=self.configurar_planes,
                     width=240, height=70, font=("Arial", 16, "bold")).pack(side="left", padx=12)
    
    def crear_licencia(self):
        """Formulario crear licencia"""
        d = ctk.CTkToplevel(self)
        d.title("Crear Licencia")
        d.geometry("650x800")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 325
        y = (d.winfo_screenheight() // 2) - 400
        d.geometry(f"650x800+{x}+{y}")
        
        scroll = ctk.CTkScrollableFrame(d, fg_color=COLORS["bg"])
        scroll.pack(fill="both", expand=True, padx=30, pady=30)
        
        ctk.CTkLabel(scroll, text="➕ Crear Nueva Licencia", 
                    font=("Arial", 28, "bold")).pack(pady=(0, 30))
        
        # Nombre
        ctk.CTkLabel(scroll, text="Nombre *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_nombre = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_nombre.pack(fill="x", pady=(8, 12))
        
        # Apellido
        ctk.CTkLabel(scroll, text="Apellido *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_apellido = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_apellido.pack(fill="x", pady=(8, 12))
        
        # Email
        ctk.CTkLabel(scroll, text="Email *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_email = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_email.pack(fill="x", pady=(8, 12))
        
        # Password
        ctk.CTkLabel(scroll, text="Contraseña *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_pass = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_pass.pack(fill="x", pady=(8, 12))
        
        # Plan
        ctk.CTkLabel(scroll, text="Plan *", anchor="w", font=("Arial", 13)).pack(fill="x")
        combo_plan = ctk.CTkComboBox(scroll, values=["basico", "medio", "premium"], 
                                     height=45, font=("Arial", 14))
        combo_plan.set("premium")
        combo_plan.pack(fill="x", pady=(8, 12))
        
        # Duración
        ctk.CTkLabel(scroll, text="Duración (días) *", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_dias = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_dias.pack(fill="x", pady=(8, 12))
        e_dias.insert(0, "30")
        
        # Precio mensual
        ctk.CTkLabel(scroll, text="Precio Mensual (opcional)", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_precio_mes = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_precio_mes.pack(fill="x", pady=(8, 12))
        
        # Precio anual
        ctk.CTkLabel(scroll, text="Precio Anual (opcional)", anchor="w", font=("Arial", 13)).pack(fill="x")
        e_precio_anio = ctk.CTkEntry(scroll, height=45, font=("Arial", 14), fg_color=COLORS["card"])
        e_precio_anio.pack(fill="x", pady=(8, 25))
        
        def guardar():
            nombre = e_nombre.get().strip()
            apellido = e_apellido.get().strip()
            email = e_email.get().strip()
            password = e_pass.get().strip()
            plan = combo_plan.get()
            dias = e_dias.get().strip()
            
            if not all([nombre, apellido, email, password, dias]):
                self.mostrar_mensaje("Error", "Todos los campos son obligatorios", "error")
                return
            
            if not dias.isdigit():
                self.mostrar_mensaje("Error", "Días debe ser un número", "error")
                return
            
            # Crear usuario
            resultado = db.crear_usuario(email, password, nombre, apellido, 'admin', None)
            
            if not resultado["success"]:
                self.mostrar_mensaje("Error", resultado.get("error"), "error")
                return
            
            # Crear licencia
            precio_mes = float(e_precio_mes.get()) if e_precio_mes.get().strip() else None
            precio_anio = float(e_precio_anio.get()) if e_precio_anio.get().strip() else None
            
            resultado_lic = db.crear_licencia(resultado["id"], plan, int(dias), 
                                             precio_mes, precio_anio)
            
            if not resultado_lic["success"]:
                self.mostrar_mensaje("Error", "Error al crear licencia", "error")
                return
            
            d.destroy()
            self.mostrar_mensaje("Éxito", 
                               f"Licencia creada correctamente\n\nUsuario: {nombre} {apellido}\nEmail: {email}\nContraseña: {password}\nPlan: {plan.upper()}\nDuración: {dias} días",
                               "success")
            
            self.mostrar_admin()
        
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=15)
        
        ctk.CTkButton(btn_frame, text="Crear Licencia", command=guardar, height=55,
                     font=("Arial", 16, "bold"), fg_color=COLORS["success"]).pack(fill="x", pady=(0, 10))
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=d.destroy, height=50,
                     fg_color="transparent", border_width=2, 
                     border_color=COLORS["border"]).pack(fill="x")
    
    def ver_licencias(self):
        """Ver todas las licencias"""
        for w in self.content.winfo_children():
            w.destroy()
        
        # Header
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", pady=(0, 25))
        
        ctk.CTkButton(header, text="← Atrás", command=self.mostrar_admin,
                     width=110, height=45, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"],
                     font=("Arial", 14)).pack(side="left")
        
        ctk.CTkLabel(header, text="📋 Licencias Activas", 
                    font=("Arial", 30, "bold")).pack(side="left", padx=25)
        
        # Obtener licencias
        licencias = db.obtener_licencias()
        
        if not licencias:
            ctk.CTkLabel(self.content, text="No hay licencias creadas",
                        font=("Arial", 17), text_color=COLORS["text_light"]).pack(expand=True, pady=80)
            return
        
        # Listar licencias
        for lic in licencias:
            card = ctk.CTkFrame(self.content, fg_color=COLORS["card"], corner_radius=10)
            card.pack(fill="x", pady=6)
            
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=25, pady=18)
            
            ctk.CTkLabel(inner, text=f"{lic['nombre']} {lic['apellido']}", 
                        font=("Arial", 18, "bold")).pack(side="left")
            
            ctk.CTkLabel(inner, text=lic['email'], font=("Arial", 13),
                        text_color=COLORS["text_light"]).pack(side="left", padx=25)
            
            ctk.CTkLabel(inner, text=f"Plan: {lic['plan'].upper()}", 
                        font=("Arial", 13, "bold"), text_color=COLORS["primary"]).pack(side="left")
            
            # Calcular días restantes
            try:
                from datetime import datetime
                venc = datetime.fromisoformat(lic['fecha_vencimiento'])
                dias_restantes = max(0, (venc - datetime.now()).days)

                color = COLORS["success"] if dias_restantes > 7 else COLORS["warning"] if dias_restantes > 0 else COLORS["danger"]
                ctk.CTkLabel(inner, text=f"Vence: {venc.strftime('%d/%m/%Y')} ({dias_restantes}d)",
                            text_color=color, font=("Arial", 13)).pack(side="right")
            except:
                pass
    
    def configurar_planes(self):
        """Configurar planes y precios"""
        self.mostrar_mensaje("Info", "Función configurar planes próximamente", "info")
    
    # ============================================
    # GENERADOR DE INVITACIONES
    # ============================================
    
    def generar_invitacion_individual(self, invitado):
        """Generar invitación individual - Con soporte para plantilla"""
        if not self.validar_accion_escritura("generar invitaciones"):
            return
        
        d = ctk.CTkToplevel(self)
        d.title(f"Generar Invitación - {invitado['nombre']} {invitado['apellido']}")
        d.geometry("600x550")
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 300
        y = (d.winfo_screenheight() // 2) - 275
        d.geometry(f"600x550+{x}+{y}")
        
        container = ctk.CTkScrollableFrame(d, fg_color=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=25, pady=25)
        
        ctk.CTkLabel(container, text="📧 Generar Invitación", 
                    font=("Arial", 20, "bold")).pack(pady=(0, 8))
        
        ctk.CTkLabel(container, text=f"{invitado['nombre']} {invitado['apellido']}", 
                    font=("Arial", 15), 
                    text_color=COLORS["primary"]).pack(pady=3)
        
        if invitado.get('mesa'):
            ctk.CTkLabel(container, text=f"Mesa {invitado['mesa']}", 
                        font=("Arial", 13),
                        text_color=COLORS["text_light"]).pack(pady=2)
        
        # Opciones
        tipo_var = ctk.StringVar(value="qr")
        
        # Solo QR
        opt1 = ctk.CTkFrame(container, fg_color=COLORS["card"], corner_radius=8)
        opt1.pack(fill="x", pady=8)
        opt1_inner = ctk.CTkFrame(opt1, fg_color="transparent")
        opt1_inner.pack(padx=15, pady=12)
        
        ctk.CTkRadioButton(opt1_inner, text="🔲 Solo código QR", 
                          variable=tipo_var, value="qr",
                          font=("Arial", 14, "bold")).pack(anchor="w")
        ctk.CTkLabel(opt1_inner, text="Solo el código QR",
                    font=("Arial", 11), text_color=COLORS["text_light"]).pack(anchor="w", padx=25, pady=(2,0))
        
        # Plantilla personalizada
        opt2 = ctk.CTkFrame(container, fg_color=COLORS["card"], corner_radius=8)
        opt2.pack(fill="x", pady=8)
        opt2_inner = ctk.CTkFrame(opt2, fg_color="transparent")
        opt2_inner.pack(padx=15, pady=12)
        
        ctk.CTkRadioButton(opt2_inner, text="🎨 Plantilla personalizada + QR", 
                          variable=tipo_var, value="plantilla",
                          font=("Arial", 14, "bold")).pack(anchor="w")
        ctk.CTkLabel(opt2_inner, text="Tu diseño con QR posicionado",
                    font=("Arial", 11), text_color=COLORS["text_light"]).pack(anchor="w", padx=25, pady=(2,0))
        
        # Selector plantilla
        plantilla_frame = ctk.CTkFrame(container, fg_color=COLORS["sidebar"], corner_radius=8)
        plantilla_frame.pack(fill="x", pady=12)
        
        plant_inner = ctk.CTkFrame(plantilla_frame, fg_color="transparent")
        plant_inner.pack(padx=15, pady=12)
        
        ctk.CTkLabel(plant_inner, text="📁 Plantilla:", 
                    font=("Arial", 12, "bold")).pack(anchor="w", pady=(0,6))
        
        plantilla_path = ctk.StringVar(value="")
        
        entry_row = ctk.CTkFrame(plant_inner, fg_color="transparent")
        entry_row.pack(fill="x", pady=4)
        
        ctk.CTkEntry(entry_row, textvariable=plantilla_path, height=36,
                    placeholder_text="Ninguna").pack(side="left", fill="x", expand=True)
        
        def seleccionar_plantilla():
            from tkinter import filedialog
            filepath = filedialog.askopenfilename(
                title="Seleccionar Plantilla",
                filetypes=[("Imágenes", "*.png *.jpg *.jpeg")]
            )
            if filepath:
                plantilla_path.set(filepath)
        
        ctk.CTkButton(entry_row, text="📁", command=seleccionar_plantilla,
                     width=45, height=36, font=("Arial", 14)).pack(side="left", padx=5)
        
        # Editor visual
        qr_x = ctk.IntVar(value=290)
        qr_y = ctk.IntVar(value=1400)
        qr_size = ctk.IntVar(value=500)
        
        def abrir_editor():
            path = plantilla_path.get()
            if not path or not os.path.exists(path):
                self.mostrar_mensaje("Error", "Selecciona primero una plantilla", "error")
                return
            
            from modules.qr_editor_visual import QREditorVisual
            
            def callback(config):
                qr_x.set(config['x'])
                qr_y.set(config['y'])
                qr_size.set(config['size'])
                self.mostrar_mensaje("✅", "Posición guardada", "success")
            
            QREditorVisual(self, path, callback)
        
        ctk.CTkButton(plant_inner, text="🖱️ Editor Visual - Posicionar QR",
                     command=abrir_editor, height=38, font=("Arial", 12, "bold"),
                     fg_color="#10b981").pack(fill="x", pady=(8,0))
        
        # Generar
        def generar():
            from datetime import datetime
            from pathlib import Path
            import qrcode
            from PIL import Image
            
            tipo = tipo_var.get()
            nombre_archivo = f"{invitado['apellido']}_{invitado['nombre']}"
            downloads = Path.home() / "Downloads"
            
            try:
                if tipo == "plantilla":
                    # Con plantilla
                    path = plantilla_path.get()
                    if not path or not os.path.exists(path):
                        self.mostrar_mensaje("Error", "Selecciona una plantilla", "error")
                        return
                    
                    d.destroy()
                    
                    # Usar misma función que masiva
                    config_qr = {'x': qr_x.get(), 'y': qr_y.get(), 'size': qr_size.get()}
                    self.generar_invitaciones_proceso("personalizada", [invitado], 
                                                     plantilla_custom=path, 
                                                     config_qr=config_qr)
                else:
                    # Solo QR
                    d.destroy()
                    output_path = downloads / f"{nombre_archivo}_QR.png"
                    
                    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, 
                                      box_size=10, border=4)
                    qr.add_data(invitado['qr_code'])
                    qr.make(fit=True)
                    qr_img = qr.make_image(fill_color="black", back_color="white")
                    qr_img.save(str(output_path))
                    
                    self.mostrar_mensaje("✅ Generado", 
                                       f"QR generado:\n\n{output_path.name}\n\nEn: Downloads", 
                                       "success")
            except Exception as e:
                self.mostrar_mensaje("Error", f"Error:\n{str(e)}", "error")
        
        # Botones
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(15,0))
        
        ctk.CTkButton(btn_frame, text="✅ Generar", command=generar,
                     height=48, font=("Arial", 14, "bold"),
                     fg_color=COLORS["success"]).pack(fill="x", pady=(0,8))
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=d.destroy,
                     height=43, font=("Arial", 13),
                     fg_color="transparent", border_width=2,
                     border_color=COLORS["border"]).pack(fill="x")
    
    def generar_invitaciones_dialog(self):
        """Generador SIMPLIFICADO - Solo QR o Plantilla+QR"""
        if not self.validar_accion_escritura("generar invitaciones"):
            return
        
        # Obtener invitados
        invitados = db.obtener_invitados_evento(self.evento_activo['id'])
        if not invitados:
            self.mostrar_mensaje("Info", "No hay invitados en este evento", "warning")
            return
        
        d = ctk.CTkToplevel(self)
        d.title("Generar Invitaciones")
        d.geometry("650x650")  # Aumentado de 550 a 650
        d.transient(self)
        d.grab_set()
        
        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() // 2) - 325
        y = (d.winfo_screenheight() // 2) - 325  # Ajustado
        d.geometry(f"650x650+{x}+{y}")
        
        # Frame principal (no scrollable)
        main_frame = ctk.CTkFrame(d, fg_color=COLORS["bg"])
        main_frame.pack(fill="both", expand=True, padx=25, pady=25)
        
        # Área scrollable para contenido
        container = ctk.CTkScrollableFrame(main_frame, fg_color=COLORS["bg"], height=480)
        container.pack(fill="both", expand=True, pady=(0, 15))
        
        ctk.CTkLabel(container, text="🎨 Generar Invitaciones", 
                    font=("Arial", 24, "bold")).pack(pady=(0, 15))
        
        ctk.CTkLabel(container, text=f"📊 {len(invitados)} invitados", 
                    font=("Arial", 13), text_color=COLORS["text_light"]).pack(pady=(0, 25))
        
        # Tipo
        tipo_var = ctk.StringVar(value="qr")
        
        # Opción 1: Solo QR
        opt1_frame = ctk.CTkFrame(container, fg_color=COLORS["card"], corner_radius=8)
        opt1_frame.pack(fill="x", pady=8)
        
        opt1_inner = ctk.CTkFrame(opt1_frame, fg_color="transparent")
        opt1_inner.pack(fill="x", padx=15, pady=12)
        
        ctk.CTkRadioButton(opt1_inner, text="🔲 Solo códigos QR", 
                          variable=tipo_var, value="qr",
                          font=("Arial", 15, "bold")).pack(anchor="w")
        
        ctk.CTkLabel(opt1_inner, text="Genera únicamente el código QR de cada invitado",
                    font=("Arial", 12), text_color=COLORS["text_light"]).pack(anchor="w", padx=25, pady=(3, 0))
        
        # Opción 2: Plantilla
        opt2_frame = ctk.CTkFrame(container, fg_color=COLORS["card"], corner_radius=8)
        opt2_frame.pack(fill="x", pady=8)
        
        opt2_inner = ctk.CTkFrame(opt2_frame, fg_color="transparent")
        opt2_inner.pack(fill="x", padx=15, pady=12)
        
        ctk.CTkRadioButton(opt2_inner, text="🎨 Plantilla personalizada + QR", 
                          variable=tipo_var, value="personalizada",
                          font=("Arial", 15, "bold")).pack(anchor="w")
        
        ctk.CTkLabel(opt2_inner, text="Sube tu diseño y posiciona el QR con el editor visual",
                    font=("Arial", 12), text_color=COLORS["text_light"]).pack(anchor="w", padx=25, pady=(3, 0))
        
        # Frame plantilla
        plantilla_frame = ctk.CTkFrame(container, fg_color=COLORS["sidebar"], corner_radius=8)
        plantilla_frame.pack(fill="x", pady=(15, 8))
        
        plantilla_inner = ctk.CTkFrame(plantilla_frame, fg_color="transparent")
        plantilla_inner.pack(padx=15, pady=15)
        
        ctk.CTkLabel(plantilla_inner, text="📁 Plantilla (requerida si eliges 'Plantilla personalizada'):", 
                    font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 8))
        
        plantilla_path = ctk.StringVar(value="")
        
        entry_row = ctk.CTkFrame(plantilla_inner, fg_color="transparent")
        entry_row.pack(fill="x", pady=5)
        
        ctk.CTkEntry(entry_row, textvariable=plantilla_path,
                    height=38, font=("Arial", 11),
                    placeholder_text="Ninguna").pack(side="left", fill="x", expand=True)
        
        def seleccionar_plantilla():
            from tkinter import filedialog
            filepath = filedialog.askopenfilename(
                title="Seleccionar Plantilla",
                filetypes=[("Imágenes", "*.png *.jpg *.jpeg")]
            )
            if filepath:
                plantilla_path.set(filepath)
        
        ctk.CTkButton(entry_row, text="📁", command=seleccionar_plantilla,
                     width=50, height=38, font=("Arial", 16)).pack(side="left", padx=5)
        
        # Editor visual
        qr_x = ctk.IntVar(value=290)
        qr_y = ctk.IntVar(value=1400)
        qr_size = ctk.IntVar(value=500)
        
        def abrir_editor():
            path = plantilla_path.get()
            if not path or not os.path.exists(path):
                self.mostrar_mensaje("Error", "Selecciona primero una plantilla", "error")
                return
            
            from modules.qr_editor_visual import QREditorVisual
            
            def callback(config):
                qr_x.set(config['x'])
                qr_y.set(config['y'])
                qr_size.set(config['size'])
                self.mostrar_mensaje("✅", "Posición guardada", "success")
            
            QREditorVisual(self, path, callback)
        
        ctk.CTkButton(plantilla_inner, text="🖱️ Editor Visual - Posicionar QR",
                     command=abrir_editor,
                     height=42, font=("Arial", 13, "bold"),
                     fg_color="#10b981",
                     hover_color="#059669").pack(fill="x", pady=(10, 0))
        
        # Botón generar
        def generar():
            tipo = tipo_var.get()
            
            # Validar
            if tipo == "personalizada":
                path = plantilla_path.get()
                if not path or not os.path.exists(path):
                    self.mostrar_mensaje("Error", "Selecciona una plantilla", "error")
                    return
                
                d.destroy()
                
                config_qr = {
                    'x': qr_x.get(),
                    'y': qr_y.get(),
                    'size': qr_size.get()
                }
                
                self.generar_invitaciones_proceso("personalizada", invitados, 
                                                 plantilla_custom=path, 
                                                 config_qr=config_qr)
            else:
                # Solo QR
                d.destroy()
                self.generar_invitaciones_proceso("qr", invitados)
        
        # Botones FUERA del scroll (en main_frame)
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 0))
        
        ctk.CTkButton(btn_frame, text="✅ Generar Invitaciones",
                     command=generar,
                     height=50, font=("Arial", 15, "bold"),
                     fg_color=COLORS["success"],
                     hover_color="#16a34a").pack(fill="x", pady=(0, 8))
        
        ctk.CTkButton(btn_frame, text="Cancelar",
                     command=d.destroy,
                     height=45, font=("Arial", 13),
                     fg_color="transparent",
                     border_width=2,
                     border_color=COLORS["border"]).pack(fill="x")
    
    def generar_invitaciones_proceso(self, tipo, invitados, plantilla_custom=None, config_qr=None):
        """Generar invitaciones con barra de progreso"""
        from datetime import datetime
        from pathlib import Path
        import qrcode
        from PIL import Image, ImageDraw, ImageFont
        import zipfile
        import tempfile
        
        # Crear ventana de progreso
        progress_window = ctk.CTkToplevel(self)
        progress_window.title("Generando Invitaciones")
        progress_window.geometry("500x250")
        progress_window.transient(self)
        progress_window.grab_set()
        
        # Centrar
        progress_window.update_idletasks()
        x = (progress_window.winfo_screenwidth() // 2) - 250
        y = (progress_window.winfo_screenheight() // 2) - 125
        progress_window.geometry(f"500x250+{x}+{y}")
        
        container = ctk.CTkFrame(progress_window, fg_color=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=30, pady=30)
        
        ctk.CTkLabel(container, text="🎨 Generando Invitaciones", 
                    font=("Arial", 20, "bold")).pack(pady=(0, 20))
        
        status_label = ctk.CTkLabel(container, text="Preparando...", 
                                   font=("Arial", 14))
        status_label.pack(pady=10)
        
        progress_bar = ctk.CTkProgressBar(container, width=400)
        progress_bar.pack(pady=20)
        progress_bar.set(0)
        
        progress_text = ctk.CTkLabel(container, text="0%", 
                                     font=("Arial", 12), text_color=COLORS["text_light"])
        progress_text.pack()
        
        # Función de generación
        def generar_invitacion(invitado, output_path):
            """Genera una invitación con QR"""
            try:
                width = 1080
                height = 1920
                
                # Si hay plantilla personalizada, usarla
                if plantilla_custom and os.path.exists(plantilla_custom):
                    try:
                        plantilla_original = Image.open(plantilla_custom).convert('RGB')
                        
                        # Mantener aspect ratio
                        plantilla_ratio = plantilla_original.width / plantilla_original.height
                        target_ratio = width / height
                        
                        if plantilla_ratio != target_ratio:
                            # Necesita ajuste
                            if plantilla_ratio > target_ratio:
                                # Plantilla más ancha - ajustar por alto
                                new_height = height
                                new_width = int(height * plantilla_ratio)
                            else:
                                # Plantilla más alta - ajustar por ancho
                                new_width = width
                                new_height = int(width / plantilla_ratio)
                            
                            # Redimensionar manteniendo ratio
                            plantilla_resized = plantilla_original.resize((new_width, new_height), 
                                                                         Image.Resampling.LANCZOS)
                            
                            # Crear canvas del tamaño objetivo
                            img = Image.new('RGB', (width, height), "#000000")
                            
                            # Centrar plantilla en canvas
                            x_offset = (width - new_width) // 2
                            y_offset = (height - new_height) // 2
                            img.paste(plantilla_resized, (x_offset, y_offset))
                            
                            print(f"[INVITACION] Plantilla ajustada: {plantilla_original.size} → {(new_width, new_height)} centrada en {(width, height)}")
                        else:
                            # Aspect ratio correcto - solo redimensionar
                            img = plantilla_original.resize((width, height), Image.Resampling.LANCZOS)
                        
                        print(f"[INVITACION] Plantilla cargada: {plantilla_custom}")
                        tiene_plantilla = True
                    except Exception as e:
                        print(f"[ERROR] Cargando plantilla: {e}")
                        # Si falla, usar diseño por defecto
                        img = Image.new('RGB', (width, height), "#1a1a2e")
                        tiene_plantilla = False
                else:
                    img = Image.new('RGB', (width, height), "#1a1a2e")
                    tiene_plantilla = False
                
                draw = ImageDraw.Draw(img)
                
                # Si NO hay plantilla custom, agregar diseño completo
                if not tiene_plantilla:
                    try:
                        font_titulo = ImageFont.truetype("arial.ttf", 80)
                        font_evento = ImageFont.truetype("arial.ttf", 60)
                        font_normal = ImageFont.truetype("arial.ttf", 40)
                        font_mesa = ImageFont.truetype("arial.ttf", 50)
                    except:
                        font_titulo = ImageFont.load_default()
                        font_evento = ImageFont.load_default()
                        font_normal = ImageFont.load_default()
                        font_mesa = ImageFont.load_default()
                    
                    # Header azul
                    draw.rectangle([(0, 0), (width, 200)], fill="#3b82f6")
                    
                    # Nombre evento
                    texto = self.evento_activo['nombre']
                    bbox = draw.textbbox((0, 0), texto, font=font_evento)
                    x = (width - (bbox[2] - bbox[0])) // 2
                    draw.text((x, 60), texto, fill="#ffffff", font=font_evento)
                    
                    # Fecha
                    fecha_texto = f"📅 {self.evento_activo.get('fecha_evento', '')}"
                    bbox = draw.textbbox((0, 0), fecha_texto, font=font_normal)
                    x = (width - (bbox[2] - bbox[0])) // 2
                    draw.text((x, 350), fecha_texto, fill="#ffffff", font=font_normal)
                    
                    # "Invitación para:"
                    texto_para = "Invitación para"
                    bbox = draw.textbbox((0, 0), texto_para, font=font_normal)
                    x = (width - (bbox[2] - bbox[0])) // 2
                    draw.text((x, 500), texto_para, fill="#ffffff", font=font_normal)
                    
                    # Nombre invitado
                    nombre = f"{invitado['nombre']} {invitado['apellido']}"
                    bbox = draw.textbbox((0, 0), nombre, font=font_titulo)
                    x = (width - (bbox[2] - bbox[0])) // 2
                    draw.text((x, 600), nombre, fill="#3b82f6", font=font_titulo)
                    
                    # Mesa (solo si no es plantilla custom)
                    if invitado.get('mesa'):
                        mesa_texto = f"Mesa: {invitado['mesa']}"
                        bbox = draw.textbbox((0, 0), mesa_texto, font=font_mesa)
                        x = (width - (bbox[2] - bbox[0])) // 2
                        draw.text((x, 750), mesa_texto, fill="#ffffff", font=font_mesa)
                
                # QR con posición y tamaño configurables
                if config_qr:
                    qr_size_px = config_qr['size']
                    qr_x_pos = config_qr['x']
                    qr_y_pos = config_qr['y']
                else:
                    qr_size_px = 500
                    qr_x_pos = (width - 500) // 2  # Centrado
                    qr_y_pos = 1400 if tiene_plantilla else 900  # Más abajo si es plantilla
                
                qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
                qr.add_data(invitado['qr_code'])
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="black", back_color="white").resize((qr_size_px, qr_size_px))
                img.paste(qr_img, (qr_x_pos, qr_y_pos))
                
                # Instrucción (solo si NO es plantilla personalizada)
                if not tiene_plantilla:
                    instruccion = "Escanea este código en el evento"
                    bbox = draw.textbbox((0, 0), instruccion, font=font_normal)
                    x = (width - (bbox[2] - bbox[0])) // 2
                    draw.text((x, 1450), instruccion, fill="#ffffff", font=font_normal)
                
                # Asegurar que carpeta existe y path es string
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                print(f"[INVITACION] Guardando: {output_path}")
                img.save(str(output_path), quality=95)
                
                if output_path.exists():
                    print(f"[INVITACION] Guardado OK - Tamaño: {output_path.stat().st_size} bytes")
                else:
                    print(f"[ERROR] Archivo no se guardó: {output_path}")
                
            except Exception as e:
                print(f"[ERROR] Generando invitación para {invitado['nombre']}: {e}")
                import traceback
                traceback.print_exc()
        
        def generar_qr_simple(invitado, output_path):
            """Genera solo el QR"""
            try:
                qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
                qr.add_data(invitado['qr_code'])
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="black", back_color="white")
                
                # Asegurar que carpeta existe y path es string
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                print(f"[QR] Guardando: {output_path}")
                qr_img.save(str(output_path))
                
                if output_path.exists():
                    print(f"[QR] Guardado OK - Tamaño: {output_path.stat().st_size} bytes")
                else:
                    print(f"[ERROR] QR no se guardó: {output_path}")
                    
            except Exception as e:
                print(f"[ERROR] Generando QR para {invitado['nombre']}: {e}")
                import traceback
                traceback.print_exc()
        
        def proceso():
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                nombre_evento = self.evento_activo['nombre'].replace(' ', '_')
                
                # Crear carpeta temporal
                temp_dir = Path(tempfile.mkdtemp())
                
                total = len(invitados)
                for i, invitado in enumerate(invitados, 1):
                    # Nombre de archivo: Solo Apellido_Nombre (sin mesa)
                    nombre_archivo = f"{invitado['apellido']}_{invitado['nombre']}"
                    
                    # Actualizar progreso
                    progreso = i / total
                    progress_bar.set(progreso)
                    progress_text.configure(text=f"{int(progreso * 100)}%")
                    status_label.configure(text=f"Generando: {invitado['apellido']}, {invitado['nombre']}")
                    progress_window.update()
                    
                    if tipo == "personalizada":
                        # Plantilla personalizada + QR
                        inv_dir = temp_dir / "invitaciones"
                        inv_dir.mkdir(exist_ok=True)
                        generar_invitacion(invitado, inv_dir / f"{nombre_archivo}.png")
                    elif tipo == "qr":
                        # Solo QR
                        qr_dir = temp_dir / "qr_codes"
                        qr_dir.mkdir(exist_ok=True)
                        generar_qr_simple(invitado, qr_dir / f"{nombre_archivo}_QR.png")
                
                # Crear ZIP
                status_label.configure(text="Creando archivo ZIP...")
                progress_window.update()
                
                # DEBUG: Verificar archivos creados
                archivos_creados = list(temp_dir.rglob("*.png"))
                print(f"\n[DEBUG] Archivos creados en temp:")
                for f in archivos_creados:
                    print(f"  - {f.name} ({f.stat().st_size} bytes)")
                
                if not archivos_creados:
                    print("[ERROR] No se crearon archivos PNG!")
                    progress_window.destroy()
                    self.mostrar_mensaje("Error", 
                                       "No se generaron archivos.\n"
                                       "Revisa la consola para más detalles.", 
                                       "error")
                    return
                
                zip_filename = f"Invitaciones_{nombre_evento}_{timestamp}.zip"
                zip_path = Path.home() / "Downloads" / zip_filename
                
                print(f"\n[DEBUG] Creando ZIP: {zip_path}")
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in archivos_creados:
                        arcname = file_path.relative_to(temp_dir)
                        print(f"[DEBUG] Agregando al ZIP: {arcname}")
                        zipf.write(file_path, arcname)
                
                print(f"[DEBUG] ZIP creado - Tamaño: {zip_path.stat().st_size} bytes")
                
                # Verificar contenido ZIP
                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    contenido = zipf.namelist()
                    print(f"[DEBUG] Contenido ZIP: {len(contenido)} archivos")
                    for name in contenido[:5]:  # Mostrar primeros 5
                        print(f"  - {name}")
                
                # Limpiar temporal
                import shutil
                shutil.rmtree(temp_dir)
                
                progress_window.destroy()
                
                # Mensaje de éxito
                self.mostrar_mensaje("✅ Completado", 
                                   f"Invitaciones generadas exitosamente!\n\n"
                                   f"📁 Archivo: {zip_filename}\n"
                                   f"📍 Ubicación: {zip_path.parent}\n\n"
                                   f"Total: {len(invitados)} invitaciones\n"
                                   f"Archivos en ZIP: {len(contenido)}",
                                   "success")
                
            except Exception as e:
                progress_window.destroy()
                self.mostrar_mensaje("Error", f"Error al generar invitaciones:\n{str(e)}", "error")
        
        # Iniciar generación después de mostrar ventana
        progress_window.after(100, proceso)
    
    def generar_invitaciones(self, plantilla, config, tipo):
        """Generar invitaciones y crear ZIP"""
        import tempfile
        import zipfile
        
        try:
            # Obtener invitados
            invitados = db.obtener_invitados_evento(self.evento_activo['id'])
            
            if tipo == "sin_acreditar":
                invitados = [i for i in invitados if not i.get('presente')]
            
            if not invitados:
                self.mostrar_mensaje("Info", "No hay invitados para generar", "warning")
                return
            
            # Crear directorio temporal
            temp_dir = tempfile.mkdtemp()
            
            # Generar invitaciones
            from modules.invitacion_generator import InvitacionGenerator
            generator = InvitacionGenerator()
            
            archivos = generator.generar_todas(
                invitados, 
                self.evento_activo, 
                temp_dir, 
                config, 
                plantilla
            )
            
            if not archivos:
                self.mostrar_mensaje("Error", "No se pudieron generar las invitaciones", "error")
                return
            
            # Crear ZIP
            zip_path = filedialog.asksaveasfilename(
                title="Guardar Invitaciones",
                defaultextension=".zip",
                filetypes=[("ZIP", "*.zip")],
                initialfile=f"Invitaciones_{self.evento_activo['nombre']}.zip"
            )
            
            if not zip_path:
                return
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for archivo in archivos:
                    zipf.write(archivo, os.path.basename(archivo))
            
            # Limpiar archivos temporales
            import shutil
            shutil.rmtree(temp_dir)
            
            self.mostrar_mensaje("Éxito", 
                                f"✅ {len(archivos)} invitaciones generadas\n\nArchivo: {os.path.basename(zip_path)}",
                                "success")
            
        except Exception as e:
            self.mostrar_mensaje("Error", f"Error al generar invitaciones:\n\n{str(e)}", "error")


    # ============================================
    # SISTEMA DE LICENCIAS PAMPA
    # ============================================

    def verificar_licencia_startup(self) -> str:
        """
        Verifica licencia o trial demo al iniciar
        Returns: "valid" | "demo_active" | "expired" | "none" | "requires_connection" | "hardware_replaced"
        """
        from config.settings import APP_VERSION

        # 1. Verificar licencia PAMPA
        license_key = self.cargar_license_key()

        if license_key:
            print(f"[WelcomeX] Validando licencia con PAMPA...")

            result = self.pampa.validate_license(license_key, app_version=APP_VERSION)

            if result['valid']:
                print(f"[WelcomeX] ✅ Licencia válida - {result['message']}")

                # Mostrar info offline si está en modo offline
                hours_offline = result.get('hours_offline')
                if hours_offline and hours_offline > 0:
                    hours_remaining = result.get('hours_remaining', 0)
                    print(f"[WelcomeX] Modo offline: {hours_offline:.0f}h usadas, {hours_remaining:.0f}h restantes")

                # Verificar alertas de vencimiento
                alert = self.pampa.check_expiration_alerts(license_key)
                if alert:
                    self.after(1000, lambda: self.mostrar_alerta_vencimiento(alert))

                return "valid"
            else:
                status = result.get('status', '')

                # Límite offline superado
                if status == 'offline_limit':
                    print(f"[WelcomeX] ❌ Límite offline superado")
                    return "requires_connection"

                # Hardware no coincide (token copiado o licencia activada en otra PC)
                if status in ('hardware_mismatch', 'hardware_replaced'):
                    print(f"[WelcomeX] ❌ Licencia activada en otro equipo")
                    return "hardware_replaced"

                # Error de conexión sin token válido
                if status == 'connection_error':
                    # Verificar si hay token local todavía utilizable
                    validation_info = self.pampa.get_validation_info()
                    if validation_info.get("requires_connection", True):
                        print(f"[WelcomeX] ❌ Requiere conexión a internet")
                        return "requires_connection"

                print(f"[WelcomeX] ❌ Licencia inválida: {result['message']}")
                return "expired"

        # 2. Si no hay licencia, verificar trial demo
        print("[WelcomeX] Sin licencia, verificando trial demo...")
        if self.verificar_trial_demo():
            dias_restantes = self.obtener_dias_trial_restantes()
            print(f"[WelcomeX] ✅ Trial demo activo ({dias_restantes} días restantes)")
            return "demo_active"

        print("[WelcomeX] Sin licencia ni trial activo")
        return "none"

    def cargar_license_key(self) -> str:
        """Carga la clave de licencia de la BD"""
        db.connect()
        try:
            db.cursor.execute("SELECT valor FROM configuracion WHERE clave = 'license_key'")
            row = db.cursor.fetchone()
            return row['valor'] if row else None
        except:
            return None
        finally:
            db.disconnect()

    def guardar_license_key(self, license_key: str):
        """Guarda la clave de licencia en la BD"""
        db.connect()
        try:
            db.cursor.execute("""
                INSERT INTO configuracion (clave, valor)
                VALUES (?, ?)
                ON CONFLICT(clave) DO UPDATE SET valor = ?
            """, ('license_key', license_key, license_key))
            db.connection.commit()
        finally:
            db.disconnect()

    def mostrar_activacion_licencia(self):
        """Pantalla de activación de licencia"""
        self.limpiar_ventana()

        container = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        container.pack(expand=True, fill="both")

        frame = ctk.CTkFrame(container, fg_color=COLORS["card"], corner_radius=15)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(padx=60, pady=50)

        ctk.CTkLabel(inner, text="🔐 Activación de Licencia",
                    font=("Arial", 32, "bold")).pack(pady=(0, 10))

        ctk.CTkLabel(inner, text="Ingresa tu clave de licencia para activar WelcomeX",
                    font=("Arial", 14), text_color=COLORS["text_light"]).pack(pady=(0, 30))

        # Entry para la clave
        entry_key = ctk.CTkEntry(inner, width=450, height=50,
                                font=("Arial", 14),
                                placeholder_text="XXXXX-XXXXX-XXXXX-XXXXX")
        entry_key.pack(pady=(0, 20))

        # Label para mensajes
        msg_label = ctk.CTkLabel(inner, text="", font=("Arial", 12), wraplength=400)
        msg_label.pack(pady=(0, 10))

        def activar():
            license_key = entry_key.get().strip()

            if not license_key:
                msg_label.configure(text="❌ Ingresa una clave de licencia", text_color=COLORS["danger"])
                return

            msg_label.configure(text="🔄 Validando con PAMPA...", text_color=COLORS["warning"])
            self.update()

            # Validar con PAMPA
            result = self.pampa.validate_license(license_key, force_online=True)

            if result['valid']:
                # Guardar licencia
                self.guardar_license_key(license_key)

                dias = result.get('days_remaining') or 0
                expira_str = result.get('expires_at', '')
                try:
                    expira_fmt = datetime.fromisoformat(expira_str).strftime('%d/%m/%Y %H:%M') + ' hs'
                except:
                    expira_fmt = f"{dias} días"
                msg_label.configure(
                    text=f"✅ Licencia activada! Vence el {expira_fmt}",
                    text_color=COLORS["success"]
                )

                # Reiniciar app después de 1 segundo
                self.after(1500, self.reiniciar_app)
            else:
                msg_label.configure(
                    text=f"❌ {result['status']}: {result['message']}",
                    text_color=COLORS["danger"],
                    wraplength=400
                )

        ctk.CTkButton(inner, text="Activar Licencia", command=activar,
                     height=50, width=250, font=("Arial", 16, "bold"),
                     fg_color=COLORS["success"]).pack(pady=(10, 20))

        ctk.CTkLabel(inner, text="¿No tienes licencia? Contacta ventas@pampaguazu.com",
                    font=("Arial", 11), text_color=COLORS["text_light"]).pack()

    def reiniciar_app(self):
        """Reinicia la app después de activar licencia"""
        self.limpiar_ventana()
        self.mostrar_login()

    def mostrar_alerta_vencimiento(self, mensaje: str):
        """Muestra alerta cuando la licencia está por vencer"""
        d = ctk.CTkToplevel(self)
        d.title("Alerta de Licencia")
        d.geometry("550x280")
        d.transient(self)
        d.grab_set()

        # Centrar
        d.update_idletasks()
        x = (d.winfo_screenwidth() - 550) // 2
        y = (d.winfo_screenheight() - 280) // 2
        d.geometry(f"+{x}+{y}")

        frame = ctk.CTkFrame(d, fg_color=COLORS["card"])
        frame.pack(expand=True, fill="both", padx=30, pady=30)

        ctk.CTkLabel(frame, text="⚠️ Atención", font=("Arial", 26, "bold"),
                    text_color=COLORS["warning"]).pack(pady=(0, 20))

        ctk.CTkLabel(frame, text=mensaje, font=("Arial", 14),
                    wraplength=450).pack(pady=(0, 25))

        ctk.CTkButton(frame, text="Entendido", command=d.destroy,
                     height=45, width=180, font=("Arial", 14)).pack()

    def mostrar_requiere_conexion(self):
        """Pantalla cuando se requiere conexión a internet para validación mensual"""
        self.limpiar_ventana()

        container = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        container.pack(expand=True, fill="both")

        frame = ctk.CTkFrame(container, fg_color=COLORS["card"], corner_radius=15)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(padx=60, pady=50)

        ctk.CTkLabel(inner, text="🌐", font=("Arial", 60)).pack(pady=(0, 15))

        ctk.CTkLabel(inner, text=t("connection.title"),
                    font=("Arial", 28, "bold")).pack(pady=(0, 10))

        ctk.CTkLabel(inner,
                    text=t("connection.description"),
                    font=("Arial", 14), text_color=COLORS["text_light"],
                    justify="center", wraplength=450).pack(pady=(0, 30))

        # Info box
        info_frame = ctk.CTkFrame(inner, fg_color=COLORS["warning"] + "20", corner_radius=10)
        info_frame.pack(fill="x", pady=(0, 25))
        info_inner = ctk.CTkFrame(info_frame, fg_color="transparent")
        info_inner.pack(padx=20, pady=15)

        ctk.CTkLabel(info_inner,
                    text=f"ℹ️ {t('connection.info')}",
                    font=("Arial", 12), text_color=COLORS["warning"],
                    justify="center").pack()

        def reintentar():
            self.limpiar_ventana()
            # Re-verificar licencia
            license_status = self.verificar_licencia_startup()
            if license_status == "valid":
                self.mostrar_login()
            elif license_status == "demo_active":
                self.mostrar_login_demo()
            elif license_status == "requires_connection":
                self.mostrar_requiere_conexion()
            else:
                self.mostrar_opciones_inicio()

        ctk.CTkButton(inner, text=f"🔄 {t('connection.retry')}", command=reintentar,
                     height=50, width=280, font=("Arial", 16, "bold"),
                     fg_color=COLORS["primary"]).pack(pady=(0, 15))

        ctk.CTkButton(inner, text=t("connection.exit"), command=self.destroy,
                     height=45, width=200, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"],
                     font=("Arial", 14)).pack()

    def mostrar_hardware_reemplazado(self):
        """Pantalla cuando la licencia fue activada en otro equipo"""
        self.limpiar_ventana()

        container = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        container.pack(expand=True, fill="both")

        frame = ctk.CTkFrame(container, fg_color=COLORS["card"], corner_radius=15)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(padx=60, pady=50)

        ctk.CTkLabel(inner, text="💻", font=("Arial", 60)).pack(pady=(0, 15))

        ctk.CTkLabel(inner, text="Licencia activa en otro equipo",
                    font=("Arial", 28, "bold")).pack(pady=(0, 10))

        ctk.CTkLabel(inner,
                    text="Esta licencia fue activada en otra computadora.\n"
                         "Solo se permite 1 equipo activo por licencia.\n\n"
                         "Si deseas usar la licencia en este equipo,\n"
                         "primero libérala desde el otro equipo.",
                    font=("Arial", 14), text_color=COLORS["text_light"],
                    justify="center", wraplength=450).pack(pady=(0, 30))

        def reintentar():
            self.limpiar_ventana()
            license_status = self.verificar_licencia_startup()
            if license_status == "valid":
                self.mostrar_login()
            elif license_status == "hardware_replaced":
                self.mostrar_hardware_reemplazado()
            elif license_status == "requires_connection":
                self.mostrar_requiere_conexion()
            else:
                self.mostrar_opciones_inicio()

        ctk.CTkButton(inner, text="🔄 Reintentar", command=reintentar,
                     height=50, width=280, font=("Arial", 16, "bold"),
                     fg_color=COLORS["primary"]).pack(pady=(0, 15))

        ctk.CTkButton(inner, text="Salir", command=self.destroy,
                     height=45, width=200, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"],
                     font=("Arial", 14)).pack()

    def _iniciar_validacion_silenciosa(self):
        """Inicia el timer de validación silenciosa cada 10 minutos"""
        if self.es_modo_demo():
            return  # No validar en modo demo

        license_key = self.cargar_license_key()
        if not license_key:
            return

        def validar_silencioso():
            try:
                result = self.pampa.silent_refresh(license_key)
                if not result.get('valid') and result.get('status') not in ('offline', 'refresh_error'):
                    # Licencia invalidada: reemplazada, revocada, vencida
                    status = result.get('status', '')
                    print(f"[WelcomeX] Validación silenciosa falló: {status}")
                    if status == 'hardware_replaced':
                        self.mostrar_hardware_reemplazado()
                    elif status == 'revoked':
                        self.mostrar_requiere_conexion()
                    elif status == 'expired':
                        self.mostrar_requiere_conexion()
                else:
                    print("[WelcomeX] Validación silenciosa OK")
            except Exception as e:
                print(f"[WelcomeX] Error en validación silenciosa: {e}")

            # Reprogramar para 10 minutos después (600000 ms)
            self.after(600000, validar_silencioso)

        # Primera validación silenciosa en 1 minuto (60000 ms)
        self.after(60000, validar_silencioso)

    def _toggle_self_release(self, switch):
        """Activa/desactiva la opción de autoliberación"""
        valor = switch.get()
        db.connect()
        try:
            db.cursor.execute("""
                INSERT INTO configuracion (clave, valor)
                VALUES (?, ?)
                ON CONFLICT(clave) DO UPDATE SET valor = ?
            """, ('allow_self_release', valor, valor))
            db.connection.commit()
        except:
            pass
        db.disconnect()

    def _liberar_licencia(self):
        """Liberar la licencia de este equipo"""
        from config.settings import APP_VERSION

        # Confirmación
        dialog = ctk.CTkToplevel(self)
        dialog.title("Liberar Licencia")
        dialog.geometry("500x300")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        x = (dialog.winfo_screenwidth() - 500) // 2
        y = (dialog.winfo_screenheight() - 300) // 2
        dialog.geometry(f"+{x}+{y}")

        frame = ctk.CTkFrame(dialog, fg_color=COLORS["card"])
        frame.pack(expand=True, fill="both", padx=20, pady=20)

        ctk.CTkLabel(frame, text="⚠️ Liberar Licencia",
                    font=("Arial", 22, "bold"), text_color=COLORS["warning"]).pack(pady=(10, 15))

        ctk.CTkLabel(frame,
                    text="¿Estás seguro de liberar la licencia en este equipo?\n\n"
                         "Este equipo no podrá usar la licencia sin reactivación.\n"
                         "Podrás activarla en otro equipo.",
                    font=("Arial", 13), text_color=COLORS["text_light"],
                    justify="center", wraplength=400).pack(pady=(0, 20))

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack()

        def confirmar():
            license_key = self.cargar_license_key()
            if not license_key:
                dialog.destroy()
                return

            result = self.pampa.release_license(license_key, app_version=APP_VERSION)

            if result.get('success'):
                # Borrar license_key del config local
                db.connect()
                try:
                    db.cursor.execute("DELETE FROM configuracion WHERE clave = 'license_key'")
                    db.connection.commit()
                except:
                    pass
                db.disconnect()

                dialog.destroy()

                # Mostrar confirmación y volver a opciones de inicio
                from tkinter import messagebox
                messagebox.showinfo("Licencia Liberada",
                                   "La licencia fue liberada correctamente.\n"
                                   "Puedes activarla en otro equipo.")
                self.mostrar_opciones_inicio()
            else:
                from tkinter import messagebox
                messagebox.showerror("Error",
                                    result.get('message', 'Error al liberar la licencia'))

        ctk.CTkButton(btn_frame, text="Liberar", command=confirmar,
                     width=150, height=45, fg_color=COLORS["danger"],
                     hover_color="#c53030", font=("Arial", 14, "bold")).pack(side="left", padx=10)

        ctk.CTkButton(btn_frame, text="Cancelar", command=dialog.destroy,
                     width=150, height=45, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"],
                     font=("Arial", 14)).pack(side="left", padx=10)

    def mostrar_info_validacion_mensual(self):
        """Muestra info discreta sobre la próxima validación si faltan pocos días"""
        validation_info = self.pampa.get_validation_info()
        days_until = validation_info.get("days_until_required", 30)

        # Solo mostrar si faltan 7 días o menos
        if days_until > 7:
            return

        # Crear label discreto en la parte inferior
        try:
            if hasattr(self, 'sidebar') and self.sidebar.winfo_exists():
                info_text = f"🌐 Próxima validación online: {days_until} día(s)"
                if days_until <= 3:
                    color = COLORS["warning"]
                else:
                    color = COLORS["text_light"]

                validation_label = ctk.CTkLabel(
                    self.sidebar,
                    text=info_text,
                    font=("Arial", 10),
                    text_color=color
                )
                validation_label.pack(side="bottom", pady=(0, 10))
        except:
            pass  # Silenciar errores si no hay sidebar

    # ============================================
    # TRIAL DEMO (7 DÍAS)
    # ============================================

    def verificar_trial_demo(self) -> bool:
        """Verifica si el trial demo está activo (no vencido)"""
        # Verificar archivo persistente primero (sobrevive borrado de DB)
        data = self._demo_registrada_persistente()
        if data:
            try:
                fecha_inicio = datetime.fromisoformat(data['started'])
                return (datetime.now() - fecha_inicio).days < 7
            except:
                return False

        # Verificar con machine_id en DB
        if not db.demo_expirada(self.machine_id):
            clave = f"demo_started_{self.machine_id}"
            fecha_str = db.get_config(clave)
            if fecha_str:
                return True

        # Legacy: verificar con clave vieja
        db.connect()
        try:
            db.cursor.execute("SELECT valor FROM configuracion WHERE clave = 'demo_trial_inicio'")
            row = db.cursor.fetchone()

            if not row:
                return False

            fecha_inicio = datetime.fromisoformat(row['valor'])
            dias_transcurridos = (datetime.now() - fecha_inicio).days

            return dias_transcurridos < 7
        except:
            return False
        finally:
            db.disconnect()

    def obtener_dias_trial_restantes(self) -> int:
        """Obtiene los días restantes del trial demo (chequea DB + archivo persistente)"""
        # Primero verificar archivo persistente (más confiable, sobrevive borrado de DB)
        data = self._demo_registrada_persistente()
        if data:
            try:
                fecha_inicio = datetime.fromisoformat(data['started'])
                dias_restantes = 7 - (datetime.now() - fecha_inicio).days
                return max(0, dias_restantes)
            except:
                pass

        # Fallback: verificar en DB con machine_id
        dias_db = db.demo_dias_restantes(self.machine_id)
        if dias_db < 7:
            return dias_db

        # Legacy: verificar con clave vieja demo_trial_inicio
        db.connect()
        try:
            db.cursor.execute("SELECT valor FROM configuracion WHERE clave = 'demo_trial_inicio'")
            row = db.cursor.fetchone()

            if not row:
                return 7

            fecha_inicio = datetime.fromisoformat(row['valor'])
            dias_transcurridos = (datetime.now() - fecha_inicio).days
            dias_restantes = 7 - dias_transcurridos

            return max(0, dias_restantes)
        except:
            return 0
        finally:
            db.disconnect()

    def iniciar_trial_demo(self):
        """Inicia el trial demo guardando la fecha actual con machine_id"""
        # Verificar si ya expiró para esta máquina
        if db.demo_expirada(self.machine_id) or self._demo_expirada_persistente():
            self.mostrar_mensaje(
                t("demo.demo_expired_title"),
                t("demo.demo_expired_msg"),
                "warning"
            )
            return

        # Registrar en DB con machine_id
        db.registrar_demo_activada(self.machine_id)

        # Registrar archivo persistente (sobrevive borrado de DB)
        if not self._demo_registrada_persistente():
            self._guardar_demo_persistente()

        # Legacy: también guardar con clave vieja para compatibilidad
        db.connect()
        try:
            fecha_inicio = datetime.now().isoformat()
            db.cursor.execute("""
                INSERT OR REPLACE INTO configuracion (clave, valor)
                VALUES ('demo_trial_inicio', ?)
            """, (fecha_inicio,))
            db.connection.commit()
            print(f"[WelcomeX] ✅ Trial demo iniciado: {fecha_inicio} (machine: {self.machine_id[:8]}...)")
        except Exception as e:
            print(f"[WelcomeX] ❌ Error al iniciar trial: {e}")
        finally:
            db.disconnect()

    def mostrar_opciones_inicio(self):
        """Pantalla inicial con opciones: Activar Licencia o Probar Demo"""
        self.limpiar_ventana()

        container = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        container.pack(expand=True, fill="both")

        frame = ctk.CTkFrame(container, fg_color=COLORS["card"], corner_radius=15)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(padx=60, pady=50)

        # Selector de idioma
        self.mostrar_selector_idioma(inner)

        # Título
        ctk.CTkLabel(inner, text=f"🎉 {t('demo.welcome')}",
                    font=("Arial", 32, "bold")).pack(pady=(15, 10))

        ctk.CTkLabel(inner, text=t("app.subtitle"),
                    font=("Arial", 16), text_color=COLORS["text_light"]).pack(pady=(0, 40))

        # Opción 1: Activar Licencia
        btn_licencia = ctk.CTkButton(
            inner,
            text=f"🔐 {t('demo.activate_license')}",
            command=self.mostrar_activacion_licencia,
            height=60,
            width=350,
            font=("Arial", 16, "bold"),
            fg_color=COLORS["success"]
        )
        btn_licencia.pack(pady=10)

        ctk.CTkLabel(inner, text=t("demo.activate_license_desc"),
                    font=("Arial", 11), text_color=COLORS["text_light"]).pack(pady=(0, 30))

        # Opción 2: Probar Demo
        btn_demo = ctk.CTkButton(
            inner,
            text=f"🎮 {t('demo.try_demo')}",
            command=self.iniciar_demo_trial,
            height=60,
            width=350,
            font=("Arial", 16, "bold"),
            fg_color=COLORS["primary"]
        )
        btn_demo.pack(pady=10)

        ctk.CTkLabel(inner, text=t("demo.try_demo_desc"),
                    font=("Arial", 11), text_color=COLORS["text_light"]).pack()

    def iniciar_demo_trial(self):
        """Inicia el trial demo y muestra login demo"""
        # Verificar si ya expiró antes de continuar
        if db.demo_expirada(self.machine_id) or self._demo_expirada_persistente():
            self.mostrar_mensaje(
                t("demo.demo_expired_title"),
                t("demo.demo_expired_msg"),
                "warning"
            )
            return
        self.iniciar_trial_demo()
        self.mostrar_login_demo()

    def mostrar_login_demo(self):
        """Muestra login directo con usuario demo y mensaje de trial"""
        dias_restantes = self.obtener_dias_trial_restantes()

        self.limpiar_ventana()

        container = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        container.pack(expand=True, fill="both")

        # Banner de trial
        banner = ctk.CTkFrame(container, fg_color=COLORS["warning"], height=60)
        banner.pack(fill="x", side="top")

        ctk.CTkLabel(
            banner,
            text=f"🎮 {t('demo.banner', days=dias_restantes)}",
            font=("Arial", 14, "bold"),
            text_color="white"
        ).pack(pady=15)

        # Login automático con usuario demo
        frame = ctk.CTkFrame(container, fg_color=COLORS["card"], corner_radius=15)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(padx=60, pady=50)

        ctk.CTkLabel(inner, text=f"🎮 {t('demo.demo_title')}",
                    font=("Arial", 32, "bold")).pack(pady=(0, 10))

        ctk.CTkLabel(inner, text=t("demo.limited_access", days=dias_restantes),
                    font=("Arial", 14), text_color=COLORS["text_light"]).pack(pady=(0, 30))

        # Botón para entrar al demo
        def entrar_demo():
            # Buscar usuario demo
            db.connect()
            try:
                db.cursor.execute("""
                    SELECT * FROM usuarios
                    WHERE email = 'demo@welcomex.com'
                """)
                usuario = db.cursor.fetchone()

                if not usuario:
                    self.mostrar_mensaje("Error", "Usuario demo no encontrado", "error")
                    return

                self.usuario_actual = dict(usuario)
                self.usuario_actual['es_demo'] = True  # Marcar como demo
                self.mostrar_principal()
            except Exception as e:
                self.mostrar_mensaje("Error", f"Error al acceder al demo: {e}", "error")
            finally:
                db.disconnect()

        ctk.CTkButton(
            inner,
            text=t("demo.enter_demo"),
            command=entrar_demo,
            height=50,
            width=250,
            font=("Arial", 16, "bold"),
            fg_color=COLORS["success"]
        ).pack(pady=10)

        # Opción para activar licencia
        ctk.CTkButton(
            inner,
            text=t("demo.activate_full"),
            command=self.mostrar_activacion_licencia,
            height=45,
            width=250,
            font=("Arial", 14),
            fg_color=COLORS["warning"]
        ).pack(pady=(20, 0))

# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    import os
    from modules.splash_screen import SplashScreen
    
    # Crear ventana temporal invisible para el splash
    root = ctk.CTk()
    root.withdraw()  # Ocultar ventana principal
    
    # Path del video splash (usar RESOURCE_DIR para compatibilidad con .exe)
    video_path = os.path.join(RESOURCE_DIR, "assets", "splash_intro.mp4")
    
    def iniciar_app():
        """Callback para iniciar app después del splash"""
        root.destroy()  # Destruir ventana temporal
        app = WelcomeXApp()
        app.mainloop()
    
    # Verificar si existe el video
    if os.path.exists(video_path):
        # Mostrar splash screen
        splash = SplashScreen(root, video_path, iniciar_app)
        root.mainloop()
    else:
        # Si no hay video, iniciar directo
        print("[INFO] Video splash no encontrado, iniciando directo...")
        iniciar_app()

