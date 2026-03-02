import customtkinter as ctk
import os
from datetime import datetime
from pynput import keyboard

# Intentar importar VLC para video con audio
try:
    import vlc
    VLC_AVAILABLE = True
    print("[VIDEO] VLC disponible - videos con audio ✅")
except:
    VLC_AVAILABLE = False
    print("[VIDEO] VLC no disponible - intentando con OpenCV")

def _get_secondary_monitor():
    """Devuelve (x, y, w, h) del monitor secundario; si hay solo uno, devuelve el primario."""
    try:
        import ctypes
        from ctypes import wintypes
        monitors = []
        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.POINTER(wintypes.RECT), ctypes.c_double
        )
        def _cb(hMonitor, hdcMonitor, lprcMonitor, dwData):
            r = lprcMonitor.contents
            monitors.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
            return True
        ctypes.windll.user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_cb), 0)
        if len(monitors) > 1:
            secondary = [m for m in monitors if not (m[0] == 0 and m[1] == 0)]
            if secondary:
                return secondary[0]
        return monitors[0] if monitors else (0, 0, 1920, 1080)
    except Exception:
        return (0, 0, 1920, 1080)


COLORS = {
    "bg": "#0f172a",
    "primary": "#3b82f6",
    "success": "#10b981",
    "error": "#ef4444",
    "warning": "#f59e0b",
    "text": "#f8fafc",
    "text_light": "#94a3b8"
}

class KioscoWindow(ctk.CTkToplevel):
    def __init__(self, parent, evento, orientacion="horizontal", kiosco_id=1):
        super().__init__(parent)
        
        self.evento = evento
        self.orientacion = orientacion
        self.kiosco_id = kiosco_id  # ID único del kiosco
        
        # Cargar configuración de pistola
        self.pistola_config = self.cargar_config_pistola()
        
        # Sync manager para sincronización entre kioscos
        from modules.sync_manager import SyncManager
        self.sync_manager = SyncManager()
        
        # Frame actual del video (para sincronización)
        self.frame_actual = 0
        self.total_frames = 0
        
        # Título con ID
        self.title(f"Kiosco {kiosco_id}")

        # Icono de la ventana
        try:
            from config.settings import RESOURCE_DIR
            icon_path = os.path.join(RESOURCE_DIR, "assets", "icon.ico")
            self.iconbitmap(icon_path)
        except Exception as e:
            print(f"[KIOSCO] No se pudo cargar el icono: {e}")
        
        # Obtener resolución de pantalla
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Geometría inicial (será reemplazada por fullscreen)
        if orientacion == "vertical":
            self.geometry(f"{screen_height}x{screen_width}")  # Rotado
        else:
            self.geometry(f"{screen_width}x{screen_height}")  # Normal
        
        # Posicionar en monitor secundario (si existe) antes de fullscreen
        if os.name == 'nt':
            try:
                mon_x, mon_y, mon_w, mon_h = _get_secondary_monitor()
                self.geometry(f"{mon_w}x{mon_h}+{mon_x}+{mon_y}")
            except Exception:
                self.geometry(f"+0+0")
        else:
            self.geometry(f"+0+0")
        
        # Actualizar para que tome los valores
        self.update_idletasks()
        
        # Pantalla completa REAL - Sin bordes, sin barra de tareas
        self.attributes('-fullscreen', True)
        self.attributes('-topmost', True)  # Siempre al frente
        
        # En Windows, asegurar que cubra todo
        try:
            self.state('zoomed')  # Maximizar primero
            self.attributes('-fullscreen', True)  # Luego fullscreen
        except:
            pass
        
        self.configure(fg_color="#000000")
        
        # Estado
        self.video_activo = False
        self.qr_buffer = ""
        self.ultimo_timestamp = None
        self.velocidad_teclas = []
        self.keyboard_listener = None

        # Modo escritura: cuando el panel del operador tiene el foco en el buscador
        self.typing_mode = False
        self.operator_panel_ref = None

        # Último invitado acreditado (para repetir con F5 o re-scan)
        self.ultimo_invitado_acreditado = None
        self.ultimo_video_acreditado = None

        # Timer para auto-ocultar panel de control
        self._hide_panel_timer = None

        # VLC player para video con audio
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None
        self._video_temporal_activo = False
        
        # Iniciar listener global SIEMPRE con suppress=True
        # suppress=True evita que Windows entregue la tecla al window activo,
        # eliminando cualquier riesgo de doble procesamiento.
        try:
            self.keyboard_listener = keyboard.Listener(
                on_press=self.on_key_press_global,
                suppress=True
            )
            self.keyboard_listener.start()
            print(f"[KIOSCO {kiosco_id}] ✅ Listener global activado (suppress=True)")
        except Exception as e:
            print(f"[KIOSCO {kiosco_id}] ⚠️ Error iniciando listener: {e}")

        # F11 y Escape se manejan en on_key_press_global (suppress=True bloquea tkinter bindings)
        
        # FIX: Variable para prevenir recursión
        self._fix_in_progress = False
        
        # FIX: Bindings para prevenir bugs de rendering (sin recursión)
        self.bind('<FocusIn>', self.on_window_focus_safe)
        
        # Frame principal (negro)
        self.main_frame = ctk.CTkFrame(self, fg_color="#000000")
        self.main_frame.pack(fill="both", expand=True)
        
        # Label para video
        self.video_label = ctk.CTkLabel(self.main_frame, text="")
        self.video_label.place(x=0, y=0, relwidth=1, relheight=1)

        # Panel de control: tk.Frame dentro de main_frame para garantizar
        # que aparezca por encima de VLC (que embebe su HWND en video_label).
        # Un Toplevel separado con -topmost no puede superar a una ventana
        # fullscreen+topmost en Windows 11. El Frame sí, con lift().
        self._panel_win = None    # legacy (no usado)
        self._ctrl_frame = None   # Frame real del panel
        self._ctrl_buttons = []   # Lista de tk.Button para animación
        self._fade_id = None      # ID del after() de animación activo
        self._panel_visible = False  # Estado lógico (True = visible o mostrándose)

        # Detectar mouse en esquina inferior derecha mediante polling.
        # VLC embebe su propio window handle sobre video_label e intercepta
        # todos los eventos de mouse, haciendo que <Motion> nunca se dispare.
        # El polling con winfo_pointerx/y() funciona independientemente de VLC.
        self.after(200, self._poll_mouse_corner)

        # Verificar si hay video
        self.video_path = evento.get('video_loop')
        
        # Mostrar info del kiosco
        if self.pistola_config:
            print(f"[KIOSCO {kiosco_id}] Pistola configurada: '{self.pistola_config['pistola_id']}'")
        else:
            print(f"[KIOSCO {kiosco_id}] Sin configuración de pistola (acepta todos los QRs)")
        
        if self.video_path and os.path.exists(self.video_path):
            print(f"[KIOSCO {kiosco_id}] Iniciando video: {self.video_path}")
            self.after(100, self.iniciar_video)
        else:
            print(f"[KIOSCO {kiosco_id}] Sin video, mostrando mensaje")
            self.mostrar_mensaje_inicial()
    
    def cargar_config_pistola(self):
        """Cargar configuración de pistola para este kiosco"""
        # SIMPLIFICADO: Aceptar todos los QRs sin validar prefijos
        print(f"[KIOSCO {self.kiosco_id}] Modo simple: Acepta todos los QRs")
        return None
    
    def iniciar_video(self):
        """Iniciar video loop con VLC (audio incluido) - Loop nativo fluido"""
        if not VLC_AVAILABLE:
            print(f"[KIOSCO {self.kiosco_id}] VLC no disponible, intentando OpenCV...")
            self.iniciar_video_opencv()
            return

        try:
            print(f"[KIOSCO {self.kiosco_id}] Iniciando video con VLC: {self.video_path}")

            # Crear instancia VLC con opciones optimizadas para loop fluido
            self.vlc_instance = vlc.Instance([
                '--no-xlib',
                '--quiet',
                '--no-video-title-show',  # No mostrar nombre del archivo
                '--input-repeat=65535',   # Repetir muchas veces (pseudo-infinito)
            ])
            self.vlc_player = self.vlc_instance.media_player_new()

            # Crear media con opciones de loop
            self.vlc_media = self.vlc_instance.media_new(self.video_path)
            # Agregar opción de repetición al media también
            self.vlc_media.add_option('input-repeat=65535')
            self.vlc_player.set_media(self.vlc_media)

            # Obtener handle del frame para renderizar
            if os.name == 'nt':  # Windows
                self.vlc_player.set_hwnd(self.video_label.winfo_id())
            else:  # Linux/Mac
                self.vlc_player.set_xwindow(self.video_label.winfo_id())

            # Reproducir
            self.vlc_player.play()
            self.video_activo = True

            print(f"[KIOSCO {self.kiosco_id}] ✅ Video iniciado con loop nativo fluido")

            # Monitorear solo por si acaso (backup, cada 5 segundos)
            self.after(5000, self.check_video_loop)

        except Exception as e:
            print(f"[KIOSCO {self.kiosco_id}] Error VLC: {e}")
            print(f"[KIOSCO {self.kiosco_id}] Fallback a OpenCV...")
            self.iniciar_video_opencv()

    def check_video_loop(self):
        """Verificar estado del video (backup por si falla el loop nativo)"""
        # No interferir mientras hay un video temporal reproduciéndose
        if self._video_temporal_activo:
            self.after(3000, self.check_video_loop)
            return
        # Verificar que ventana y player existen
        if not self.video_activo or not self.vlc_player:
            return

        # Verificar que la ventana no fue destruida
        try:
            self.winfo_exists()
        except:
            return

        try:
            state = self.vlc_player.get_state()

            # Solo reiniciar si realmente terminó (el loop nativo debería evitar esto)
            if state == vlc.State.Ended:
                print(f"[KIOSCO {self.kiosco_id}] Video terminó, reiniciando suave...")
                # Reinicio más suave: set_position al inicio en vez de stop/play
                self.vlc_player.set_position(0)
                self.vlc_player.play()
            elif state == vlc.State.Error:
                print(f"[KIOSCO {self.kiosco_id}] Error en video, reintentando...")
                self.vlc_player.stop()
                self.after(100, lambda: self.vlc_player.play())

            # Seguir monitoreando cada 3 segundos (menos frecuente)
            if self.video_activo:
                self.after(3000, self.check_video_loop)
        except:
            pass
    
    def iniciar_video_opencv(self):
        """Fallback: Iniciar video con OpenCV (sin audio)"""
        try:
            import cv2
            from PIL import Image, ImageTk
            
            self.video_activo = True
            self.cap = cv2.VideoCapture(self.video_path)
            
            if not self.cap.isOpened():
                print(f"[KIOSCO {self.kiosco_id}] No se pudo abrir video")
                self.mostrar_mensaje_inicial()
                return
            
            # Obtener FPS del video
            self.video_fps = self.cap.get(cv2.CAP_PROP_FPS)
            if self.video_fps == 0 or self.video_fps > 120:
                self.video_fps = 30  # Default si no se detecta
            
            # Calcular delay en ms
            self.frame_delay = int(1000 / self.video_fps)
            
            # Obtener total de frames para sincronización
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            print(f"[KIOSCO {self.kiosco_id}] Video OpenCV: {self.total_frames} frames @ {self.video_fps} FPS")
            print(f"[KIOSCO {self.kiosco_id}] ⚠️ Sin audio (OpenCV)")
            
            # Intentar sincronizar con otros kioscos
            frame_objetivo = self.sync_manager.obtener_frame_objetivo(
                self.kiosco_id, 
                self.total_frames
            )
            
            if frame_objetivo is not None:
                print(f"[KIOSCO {self.kiosco_id}] Sincronizando con frame {frame_objetivo}")
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_objetivo)
                self.frame_actual = frame_objetivo
            else:
                self.frame_actual = 0
            
            self.reproducir_frame()
            
        except ImportError:
            print(f"[KIOSCO {self.kiosco_id}] OpenCV no instalado")
            self.mostrar_mensaje_inicial()
    
    def reproducir_frame(self):
        """Reproducir frame del video"""
        if not self.video_activo:
            return
        
        try:
            import cv2
            from PIL import Image, ImageTk
            
            ret, frame = self.cap.read()
            
            if not ret:
                # Loop
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            
            if ret:
                # Convertir BGR a RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Redimensionar
                w = self.winfo_width()
                h = self.winfo_height()
                
                if w > 1 and h > 1:
                    frame = cv2.resize(frame, (w, h))
                
                # Mostrar
                img = Image.fromarray(frame)
                imgtk = ImageTk.PhotoImage(image=img)
                
                self.video_label.configure(image=imgtk)
                self.video_label.image = imgtk
                
                # Actualizar frame actual
                self.frame_actual = (self.frame_actual + 1) % self.total_frames
                
                # Registrar posición cada 30 frames (~1 segundo)
                if self.frame_actual % 30 == 0:
                    import time
                    self.sync_manager.registrar_loop_frame(
                        self.kiosco_id,
                        self.frame_actual,
                        time.time()
                    )
            
            # Usar delay calculado según FPS del video
            self.after(self.frame_delay, self.reproducir_frame)
            
        except Exception as e:
            print(f"[ERROR] {e}")
            self.video_activo = False
    
    def mostrar_mensaje_inicial(self):
        """Mostrar mensaje si no hay video"""
        self.video_label.configure(
            text=f"{self.evento['nombre']}\n\n📱\n\nAcerca tu código QR",
            font=("Arial", 48, "bold"),
            text_color="#ffffff"
        )
    
    def capturar_tecla(self, event):
        """Capturar teclas para QR"""
        if event.char.isprintable():
            self.qr_buffer += event.char
            print(f"[TECLA] '{event.char}' → Buffer: '{self.qr_buffer}' ({len(self.qr_buffer)} chars)")
        elif event.keysym == 'Return':
            print(f"\n[ENTER] Buffer final: '{self.qr_buffer}' ({len(self.qr_buffer)} chars)")
            if self.qr_buffer and len(self.qr_buffer) >= 5:
                self.procesar_qr(self.qr_buffer)
                self.qr_buffer = ""
            elif self.qr_buffer:
                print(f"[WARN] QR muy corto, ignorado")
                self.qr_buffer = ""
            else:
                print(f"[WARN] Enter sin contenido, ignorado")
    
    def procesar_qr(self, qr_code):
        """Procesar código QR - VERSIÓN SIMPLIFICADA"""
        print(f"\n{'='*60}")
        print(f"[KIOSCO {self.kiosco_id}] QR RECIBIDO: '{qr_code}'")
        print(f"{'='*60}")
        
        # Limpiar QR y normalizar a mayúsculas (la pistola puede enviar minúsculas si Caps Lock está activado)
        qr_code = qr_code.strip().upper()
        
        if not qr_code or len(qr_code) < 5:
            print(f"[ERROR] QR inválido: muy corto o vacío")
            self._beep("error")
            self.mostrar_overlay("❌ QR INVÁLIDO", "#ef4444", 2000)
            return

        print(f"[BÚSQUEDA] Buscando en BD: '{qr_code}'")

        # Importar database
        from modules.database import db

        # Buscar invitado por QR
        invitado = db.obtener_invitado_por_qr(qr_code)

        if not invitado:
            print(f"[ERROR] ❌ Invitado NO encontrado en BD")
            print(f"[DEBUG] Código recibido (repr): {repr(qr_code)}")
            self._beep("error")
            self.mostrar_overlay("❌ QR NO REGISTRADO", "#ef4444", 3000)
            return

        # Invitado encontrado
        print(f"[OK] ✅ Invitado: {invitado['nombre']} {invitado['apellido']}")
        print(f"[OK] Mesa: {invitado.get('mesa', 'Sin mesa')}")

        # Verificar que sea del evento correcto
        if invitado['evento_id'] != self.evento['id']:
            print(f"[ERROR] ❌ Evento incorrecto")
            self._beep("error")
            self.mostrar_overlay("❌ QR DE OTRO EVENTO", "#ef4444", 3000)
            return

        # Verificar si ya está presente → advertencia, NO repetir bienvenida
        if invitado.get('presente'):
            nombre = f"{invitado['nombre']} {invitado['apellido']}"
            print(f"[WARN] ⚠️ Ya acreditado — mostrando aviso de duplicado")
            self._beep("repetir")
            self.mostrar_overlay(f"⚠ YA INGRESO\n{nombre}", "#f59e0b", 3000)
            return

        # ACREDITAR
        print(f"[ACCIÓN] Acreditando invitado ID={invitado['id']}...")
        resultado = db.acreditar_invitado(invitado['id'], self.evento['id'], self.kiosco_id)

        if not resultado:
            print(f"[ERROR] ❌ Fallo al acreditar en BD")
            self._beep("error")
            self.mostrar_overlay("❌ ERROR AL ACREDITAR", "#ef4444", 3000)
            return

        print(f"[OK] ✅ Acreditación exitosa")
        self._beep("ok")
        self._mostrar_acreditacion(invitado, repetir=False)
        print(f"[FIN] Proceso completado\n")

    def _beep(self, tipo):
        """Sonido sutil de sistema según el resultado (respeta usar_sonido del evento)"""
        if not self.evento.get('usar_sonido', 1):
            return
        try:
            import winsound
            if tipo == "ok":
                winsound.MessageBeep(winsound.MB_OK)          # ding suave
            elif tipo == "repetir":
                winsound.Beep(880, 120)                        # tono corto (re-scan)
            elif tipo == "error":
                winsound.MessageBeep(winsound.MB_ICONHAND)     # sonido de error Windows
        except Exception:
            pass  # Si falla (no Windows / sin audio), no hace nada

    def _mostrar_acreditacion(self, invitado, repetir=False):
        """Reproduce video y/o muestra overlay de bienvenida"""
        from modules.database import db

        video_personalizado = invitado.get('video_personalizado')
        video_mesa = None

        if not video_personalizado and invitado.get('mesa') and self.evento.get('usar_video_mesa', 1):
            video_mesa = db.obtener_video_por_mesa(self.evento['id'], invitado['mesa'])

        video_a_reproducir = video_personalizado or video_mesa

        # Guardar para repetir con F5
        self.ultimo_invitado_acreditado = invitado
        self.ultimo_video_acreditado = video_a_reproducir

        if video_a_reproducir and os.path.exists(video_a_reproducir):
            print(f"[VIDEO] Reproduciendo: {video_a_reproducir}")
            self.reproducir_video_temporal(invitado, video_a_reproducir)
        else:
            if self.evento.get('mostrar_bienvenida', 1):
                nombre = f"{invitado['nombre']} {invitado['apellido']}"
                mostrar_mesa = self.evento.get('mostrar_mesa', 1)
                if mostrar_mesa and invitado.get('mesa'):
                    self.mostrar_overlay(f"✅ BIENVENIDO\n{nombre}\nMESA {invitado['mesa']}", "#10b981", 3000)
                else:
                    self.mostrar_overlay(f"✅ BIENVENIDO\n{nombre}", "#10b981", 3000)

    # ── Panel de control ocultable ────────────────────────────────────────────

    # ── Detección de esquina ─────────────────────────────────────────────────

    def _poll_mouse_corner(self):
        """Polling cada 150ms — detecta entrada/salida de la esquina inferior derecha.
        Necesario porque VLC intercepta los eventos <Motion> de Tkinter."""
        if not self.winfo_exists():
            return
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            mx = self.winfo_pointerx()
            my = self.winfo_pointery()
            zona = int(min(sw, sh) * 0.12)  # ~130px en 1080p
            in_zone = (mx > sw - zona) and (my > sh - zona)

            if in_zone:
                # Cancelar cualquier hide pendiente
                if self._hide_panel_timer:
                    self.after_cancel(self._hide_panel_timer)
                    self._hide_panel_timer = None
                if not self._panel_visible:
                    self._show_ctrl_panel()
            else:
                # Mouse fuera de zona → programar fade-out si panel visible
                if self._panel_visible and not self._hide_panel_timer:
                    self._hide_panel_timer = self.after(400, self._hide_ctrl_panel)
        except Exception:
            pass
        self.after(150, self._poll_mouse_corner)

    def _on_mouse_motion(self, event):
        """Fallback binding (no funciona con VLC activo)."""
        pass

    # ── Creación del panel ───────────────────────────────────────────────────

    def _create_ctrl_frame(self):
        """Crea el Frame de control dentro de main_frame (lazy init).
        place+lift dentro del mismo contenedor supera el z-order de VLC."""
        import tkinter as tk
        frame = tk.Frame(self.main_frame, bg="#000000", bd=0)
        # Colores iniciales invisibles (se animan con fade-in)
        _bs = dict(bg="#000000", fg="#000000", bd=0, relief="flat",
                   font=("Segoe UI", 26), cursor="hand2",
                   padx=16, pady=12,
                   activebackground="#000000", activeforeground="#ffffff")
        b1 = tk.Button(frame, text="↺", command=self.repetir_ultima_acreditacion, **_bs)
        b2 = tk.Button(frame, text="⊟", command=self.minimizar_kiosco,            **_bs)
        b3 = tk.Button(frame, text="✕", command=self.destroy,                     **_bs)
        b1.pack(fill="x")
        b2.pack(fill="x")
        b3.pack(fill="x")
        self._ctrl_buttons = [b1, b2, b3]
        self._ctrl_frame = frame

    # ── Animación fade ───────────────────────────────────────────────────────

    @staticmethod
    def _lerp_color(c1, c2, t):
        """Interpolación lineal entre dos colores hex."""
        r1,g1,b1 = int(c1[1:3],16), int(c1[3:5],16), int(c1[5:7],16)
        r2,g2,b2 = int(c2[1:3],16), int(c2[3:5],16), int(c2[5:7],16)
        r = max(0, min(255, int(r1 + (r2-r1)*t)))
        g = max(0, min(255, int(g1 + (g2-g1)*t)))
        b = max(0, min(255, int(b1 + (b2-b1)*t)))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _animate_fade(self, direction, step=0):
        """Anima el fade del panel. direction='in' o 'out'. 10 pasos × 20ms = 200ms."""
        self._fade_id = None
        total = 10
        if step > total:
            if direction == 'out':
                if self._ctrl_frame:
                    self._ctrl_frame.place_forget()
                self._panel_visible = False
            return

        t = step / total if direction == 'in' else 1.0 - step / total
        bg_panel = self._lerp_color("#000000", "#0d0d2b", t)
        fg_btn   = self._lerp_color("#000000", "#d0d0ff", t)
        bg_hover = self._lerp_color("#000000", "#2a2a55", t)

        try:
            if self._ctrl_frame:
                self._ctrl_frame.config(bg=bg_panel)
            for btn in self._ctrl_buttons:
                btn.config(bg=bg_panel, fg=fg_btn, activebackground=bg_hover)
        except Exception:
            return

        self._fade_id = self.after(20, lambda: self._animate_fade(direction, step + 1))

    # ── Mostrar / ocultar ────────────────────────────────────────────────────

    def _show_ctrl_panel(self):
        if self._ctrl_frame is None:
            self._create_ctrl_frame()

        # Si ya está visible, solo cancela timer de hide
        if self._panel_visible:
            if self._hide_panel_timer:
                self.after_cancel(self._hide_panel_timer)
                self._hide_panel_timer = None
            return

        # Interrumpir fade-out si estaba en progreso
        if self._fade_id:
            self.after_cancel(self._fade_id)
            self._fade_id = None
        if self._hide_panel_timer:
            self.after_cancel(self._hide_panel_timer)
            self._hide_panel_timer = None

        self._panel_visible = True

        # Partir desde colores invisibles
        try:
            self._ctrl_frame.config(bg="#000000")
            for btn in self._ctrl_buttons:
                btn.config(bg="#000000", fg="#000000", activebackground="#000000")
        except Exception:
            pass

        # Colocar y subir por encima de VLC
        self._ctrl_frame.place(in_=self.main_frame,
                               relx=1.0, rely=1.0, anchor="se",
                               x=-12, y=-12)
        self._ctrl_frame.lift()

        # Iniciar fade-in
        self._animate_fade('in')

    def _hide_ctrl_panel(self):
        self._hide_panel_timer = None
        if not self._panel_visible or self._ctrl_frame is None:
            return

        # Interrumpir fade-in si estaba en progreso
        if self._fade_id:
            self.after_cancel(self._fade_id)
            self._fade_id = None

        # Iniciar fade-out (al terminar llama place_forget y pone _panel_visible=False)
        self._animate_fade('out')

    def _panel_mouse_leave(self, event):
        """Por si acaso el mouse sale del frame directamente."""
        if self._hide_panel_timer:
            self.after_cancel(self._hide_panel_timer)
        self._hide_panel_timer = self.after(400, self._hide_ctrl_panel)

    # ── Acciones ─────────────────────────────────────────────────────────────

    def minimizar_kiosco(self):
        """Minimiza el kiosco a la barra de tareas"""
        self.attributes('-fullscreen', False)
        self.iconify()
        # Al restaurar, volver a fullscreen
        self.bind('<Map>', self._restaurar_fullscreen)

    def _restaurar_fullscreen(self, event=None):
        self.unbind('<Map>')
        self.after(150, lambda: self.attributes('-fullscreen', True))

    def _reabrir_panel_operador(self):
        """F2 — reabre el panel del operador si fue cerrado, o lo trae al frente"""
        from modules.operator_panel import OperatorPanel
        try:
            if self.operator_panel_ref and self.operator_panel_ref.winfo_exists():
                self.operator_panel_ref.deiconify()
                self.operator_panel_ref.lift()
                return
        except Exception:
            pass
        # Panel cerrado o inválido — recrear
        try:
            panel = OperatorPanel(self.master, self.evento, kiosco_window=self)
            self.operator_panel_ref = panel
            print(f"[KIOSCO] Panel operador reabierto con F2")
        except Exception as e:
            print(f"[KIOSCO] Error reabriendo panel: {e}")

    def repetir_ultima_acreditacion(self):
        """F5 — repite el video/overlay del último invitado acreditado"""
        if not self.ultimo_invitado_acreditado:
            return
        print(f"[F5] Repitiendo acreditación: {self.ultimo_invitado_acreditado['nombre']}")
        self._beep("repetir")
        self._mostrar_acreditacion(self.ultimo_invitado_acreditado, repetir=True)
    
    def reproducir_video_temporal(self, invitado, video_path):
        """Reproducir video personalizado/mesa con VLC (audio incluido)"""
        print(f"[KIOSCO] Iniciando video temporal: {video_path}")

        # Restaurar ventana si está minimizada para que VLC pueda renderizar en ella
        try:
            if self.wm_state() == 'iconic':
                self.deiconify()
                self.lift()
                self.update_idletasks()
        except Exception:
            pass

        # Guardar estado del video principal
        self.video_principal_activo_backup = self.video_activo
        self.invitado_temp = invitado

        # PAUSAR video loop principal (VLC)
        if hasattr(self, 'vlc_player') and self.vlc_player:
            try:
                self.vlc_player.pause()
                print(f"[KIOSCO] Video principal pausado")
            except:
                pass
        self.video_activo = False

        # Usar VLC para video temporal si está disponible
        if VLC_AVAILABLE:
            self._reproducir_video_temporal_vlc(video_path)
        else:
            self._reproducir_video_temporal_opencv(video_path)

    def _reproducir_video_temporal_vlc(self, video_path):
        """Reproducir video temporal reutilizando el mismo vlc_player (sin abrir ventana nueva)"""
        try:
            if not self.vlc_player or not self.vlc_instance:
                raise Exception("vlc_player no disponible")

            # Marcar que estamos en modo temporal para que check_video_loop no interfiera
            self._video_temporal_activo = True

            # Detener el loop actual y cargar el video de mesa SIN repetición
            self.vlc_player.stop()
            temp_media = self.vlc_instance.media_new(video_path)
            temp_media.add_option('input-repeat=0')  # Sobreescribir el repeat=65535 del instance
            self.vlc_player.set_media(temp_media)
            self.vlc_player.play()
            print(f"[KIOSCO] Video temporal VLC iniciado (mismo player, sin ventana nueva)")

            # Monitorear cuando termine
            self.after(500, self._check_video_temporal_end)

        except Exception as e:
            print(f"[ERROR] Error VLC temporal: {e}, usando OpenCV...")
            self._video_temporal_activo = False
            self._reproducir_video_temporal_opencv(video_path)

    def _check_video_temporal_end(self):
        """Verificar si video temporal terminó"""
        try:
            if not self._video_temporal_activo or not self.vlc_player:
                return

            state = self.vlc_player.get_state()

            if state == vlc.State.Ended or state == vlc.State.Stopped or state == vlc.State.Error:
                print(f"[KIOSCO] Video temporal finalizado")
                self._video_temporal_activo = False
                self._mostrar_overlay_bienvenida()
            else:
                self.after(300, self._check_video_temporal_end)
        except Exception as e:
            print(f"[ERROR] Error verificando video temporal: {e}")
            self._video_temporal_activo = False
            self._mostrar_overlay_bienvenida()

    def _mostrar_overlay_bienvenida(self):
        """Mostrar overlay de bienvenida después del video"""
        invitado = self.invitado_temp
        if self.evento.get('mostrar_bienvenida', 1):
            nombre = f"{invitado['nombre']} {invitado['apellido']}"
            mostrar_mesa = self.evento.get('mostrar_mesa', 1)
            if mostrar_mesa and invitado.get('mesa'):
                self.mostrar_overlay(f"✅ BIENVENIDO\n{nombre}\nMESA {invitado['mesa']}", "#10b981", 3000)
            else:
                self.mostrar_overlay(f"✅ BIENVENIDO\n{nombre}", "#10b981", 3000)

        # Reanudar video principal después del overlay (con o sin cartel)
        delay = 3000 if self.evento.get('mostrar_bienvenida', 1) else 0
        self.after(delay, lambda: self.reanudar_video_principal(self.video_principal_activo_backup))

    def _reproducir_video_temporal_opencv(self, video_path):
        """Fallback: Reproducir video temporal con OpenCV (sin audio)"""
        try:
            import cv2
            from PIL import Image, ImageTk

            invitado = self.invitado_temp

            cap_temp = cv2.VideoCapture(video_path)

            if not cap_temp.isOpened():
                print(f"[ERROR] No se pudo abrir video temporal")
                if self.evento.get('mostrar_bienvenida', 1):
                    nombre = f"{invitado['nombre']} {invitado['apellido']}"
                    mesa = f"MESA {invitado['mesa']}" if invitado.get('mesa') else ""
                    self.mostrar_overlay(f"✅ BIENVENIDO\n{nombre}\n{mesa}", "#10b981", 3000)
                self.after(3000 if self.evento.get('mostrar_bienvenida', 1) else 0,
                           lambda: self.reanudar_video_principal(self.video_principal_activo_backup))
                return

            fps = cap_temp.get(cv2.CAP_PROP_FPS) or 30
            total_frames = int(cap_temp.get(cv2.CAP_PROP_FRAME_COUNT))

            print(f"[KIOSCO] Video temporal OpenCV: {total_frames} frames, {fps} FPS")

            frame_count = 0

            def reproducir_frame_temp():
                nonlocal frame_count

                ret, frame = cap_temp.read()

                if not ret or frame_count >= total_frames:
                    print(f"[KIOSCO] Video temporal OpenCV finalizado")
                    cap_temp.release()
                    self._mostrar_overlay_bienvenida()
                    return

                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                w = self.winfo_width()
                h = self.winfo_height()

                if w > 1 and h > 1:
                    frame = cv2.resize(frame, (w, h))

                img = Image.fromarray(frame)
                imgtk = ImageTk.PhotoImage(image=img)

                self.video_label.configure(image=imgtk)
                self.video_label.image = imgtk

                frame_count += 1
                delay = int(1000 / fps)
                self.after(delay, reproducir_frame_temp)

            reproducir_frame_temp()

        except Exception as e:
            print(f"[ERROR] Error en video temporal OpenCV: {e}")
            self.reanudar_video_principal(self.video_principal_activo_backup)
            if self.evento.get('mostrar_bienvenida', 1):
                nombre = f"{invitado['nombre']} {invitado['apellido']}"
                mesa = f"MESA {invitado['mesa']}" if invitado.get('mesa') else ""
                self.mostrar_overlay(f"✅ BIENVENIDO\n{nombre}\n{mesa}", "#10b981", 3000)
    
    def reanudar_video_principal(self, estado_previo):
        """Reanudar video loop principal recargando el media con loop"""
        print(f"[KIOSCO] Reanudando video principal")
        self.video_activo = estado_previo
        if self.video_activo:
            if hasattr(self, 'vlc_player') and self.vlc_player and self.vlc_instance:
                try:
                    # Recargar el media de loop (el video temporal lo reemplazó)
                    self.vlc_media = self.vlc_instance.media_new(self.video_path)
                    self.vlc_media.add_option('input-repeat=65535')
                    self.vlc_player.set_media(self.vlc_media)
                    self.vlc_player.play()
                    print(f"[KIOSCO] Video loop VLC reanudado")
                except Exception as e:
                    print(f"[KIOSCO] Error reanudando VLC: {e}")
            else:
                # Fallback OpenCV
                self.reproducir_frame()
    
    def mostrar_overlay(self, texto, color, duracion):
        """Mostrar overlay temporal - OPTIMIZADO"""
        # Cancelar timer anterior si existe
        if hasattr(self, 'overlay_timer'):
            try:
                self.after_cancel(self.overlay_timer)
            except:
                pass

        # Reutilizar overlay si existe, solo cambiar contenido
        if hasattr(self, 'overlay') and self.overlay.winfo_exists():
            self.overlay.configure(fg_color=color)
            if hasattr(self, 'overlay_label'):
                self.overlay_label.configure(text=texto)
        else:
            # Crear nuevo overlay
            self.overlay = ctk.CTkFrame(self.main_frame,
                                       fg_color=color,
                                       corner_radius=20)
            self.overlay.place(relx=0.5, rely=0.5, anchor="center")

            self.overlay_label = ctk.CTkLabel(self.overlay,
                        text=texto,
                        font=("Arial", 60, "bold"),
                        text_color="#ffffff")
            self.overlay_label.pack(padx=80, pady=60)

        # Forzar actualización inmediata
        self.overlay.update_idletasks()

        # Timer para ocultar
        self.overlay_timer = self.after(duracion, self._ocultar_overlay)

    def _ocultar_overlay(self):
        """Ocultar overlay (helper)"""
        if hasattr(self, 'overlay') and self.overlay.winfo_exists():
            self.overlay.destroy()
    
    def on_key_press_global(self, key):
        """Captura global de teclado - SIEMPRE activa (suppress=True)"""
        try:
            # Teclas especiales
            if key == keyboard.Key.f11:
                self.after(0, self.toggle_fullscreen)
                return
            elif key == keyboard.Key.esc:
                self.after(0, self.cerrar_directo)
                return
            elif key == keyboard.Key.f5:
                self.after(0, self.repetir_ultima_acreditacion)
                return
            elif key == keyboard.Key.f2:
                self.after(0, self._reabrir_panel_operador)
                return

            # Modo escritura: redirigir teclas al buscador del panel operador
            if self.typing_mode and self.operator_panel_ref:
                try:
                    if hasattr(key, 'char') and key.char and key.char.isprintable():
                        current = self.operator_panel_ref.search_var.get()
                        self.operator_panel_ref.search_var.set(current + key.char)
                    elif key == keyboard.Key.backspace:
                        current = self.operator_panel_ref.search_var.get()
                        self.operator_panel_ref.search_var.set(current[:-1])
                except Exception:
                    pass
                return  # No procesar como QR

            # Capturar carácter
            if hasattr(key, 'char') and key.char and key.char.isprintable():
                self.qr_buffer += key.char
                print(f"[📝] '{key.char}' → {self.qr_buffer}")

            # Si es Enter, procesar QR
            elif key == keyboard.Key.enter:
                print(f"\n[⏎ ENTER] Procesando: '{self.qr_buffer}'")
                
                # Solo procesar si hay contenido real
                if self.qr_buffer and len(self.qr_buffer) >= 5:
                    # Procesar en hilo principal de Tkinter
                    self.after(0, lambda qr=self.qr_buffer: self.procesar_qr(qr))
                elif self.qr_buffer:
                    print(f"[⚠️] QR muy corto: '{self.qr_buffer}'")
                # No imprimir nada si buffer vacío (ignorar Enter solo)
                
                # Limpiar buffer
                self.qr_buffer = ""
                
        except Exception as e:
            print(f"[KIOSCO] Error captura global: {e}")
    
    def toggle_fullscreen(self):
        """Toggle fullscreen mejorado"""
        current = self.attributes('-fullscreen')
        new_state = not current
        
        self.attributes('-fullscreen', new_state)
        self.attributes('-topmost', new_state)  # Sincronizar topmost
        
        if new_state:
            # Entrando a fullscreen
            try:
                self.state('zoomed')
                self.attributes('-fullscreen', True)
            except:
                pass
    
    def cerrar_directo(self):
        """Cerrar sin preguntar"""
        print(f"[KIOSCO {self.kiosco_id}] Cerrando...")
        
        # Marcar como inactivo PRIMERO
        self.video_activo = False
        
        # Detener VLC si está activo
        if hasattr(self, 'vlc_player') and self.vlc_player:
            try:
                self.vlc_player.stop()
                self.vlc_player.release()
                self.vlc_player = None
                print(f"[KIOSCO {self.kiosco_id}] VLC detenido")
            except:
                pass
        
        # Limpiar instancia VLC
        if hasattr(self, 'vlc_instance') and self.vlc_instance:
            try:
                self.vlc_instance.release()
                self.vlc_instance = None
            except:
                pass
        
        # Detener listener global
        if hasattr(self, 'keyboard_listener') and self.keyboard_listener:
            try:
                self.keyboard_listener.stop()
                print(f"[KIOSCO {self.kiosco_id}] Listener global detenido")
            except:
                pass
        
        # Detener OpenCV si existe
        if hasattr(self, 'cap'):
            try:
                self.cap.release()
            except:
                pass
        
        # Limpiar sincronización
        if hasattr(self, 'sync_manager'):
            try:
                self.sync_manager.limpiar_kiosco(self.kiosco_id)
            except:
                pass
        
        # Esperar un momento antes de destruir
        self.after(100, self._destruir_seguro)
    
    def _destruir_seguro(self):
        """Destruir ventana de forma segura"""
        try:
            self.destroy()
        except:
            pass
    
    # ============================================
    # FIX: MÉTODO SEGURO PARA PREVENIR BUGS (SIN RECURSIÓN)
    # ============================================
    
    def on_window_focus_safe(self, event):
        """Fix: Detecta cuando ventana gana foco (sin causar recursión)"""
        try:
            # Verificar que ventana existe
            if not self.winfo_exists():
                return
            
            if not self._fix_in_progress:
                self._fix_in_progress = True
                self.after(100, self.fix_rendering_safe)
        except:
            pass
    
    def fix_rendering_safe(self):
        """Fix: Forzar redibujado sin causar recursión"""
        try:
            # Verificar que ventana existe
            if self.winfo_exists():
                self.update_idletasks()
        except:
            pass
        finally:
            self._fix_in_progress = False
