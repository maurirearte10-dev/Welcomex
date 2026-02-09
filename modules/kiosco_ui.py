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
        
        # Posicionar en (0,0) antes de fullscreen
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
        
        # VLC player para video con audio
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None
        
        # Iniciar listener global SIEMPRE
        try:
            self.keyboard_listener = keyboard.Listener(
                on_press=self.on_key_press_global,
                suppress=False  # No suprimir teclas
            )
            self.keyboard_listener.start()
            print(f"[KIOSCO {kiosco_id}] ✅ Listener global activado")
        except Exception as e:
            print(f"[KIOSCO {kiosco_id}] ⚠️ Error iniciando listener: {e}")
        
        # Bindings locales (cuando tiene foco)
        self.bind('<F11>', lambda e: self.toggle_fullscreen())
        self.bind('<Escape>', lambda e: self.cerrar_directo())
        self.bind('<Key>', self.capturar_tecla)
        
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
        
        # Limpiar QR
        qr_code = qr_code.strip()
        
        if not qr_code or len(qr_code) < 5:
            print(f"[ERROR] QR inválido: muy corto o vacío")
            self.mostrar_overlay("❌ QR INVÁLIDO", "#ef4444", 2000)
            return
        
        print(f"[BÚSQUEDA] Buscando en BD: '{qr_code}'")
        
        # Importar database
        from modules.database import db
        
        # Buscar invitado por QR
        invitado = db.obtener_invitado_por_qr(qr_code)
        
        if not invitado:
            print(f"[ERROR] ❌ Invitado NO encontrado en BD")
            print(f"[INFO] Verifica que el QR '{qr_code}' exista en tabla invitados")
            self.mostrar_overlay("❌ QR NO REGISTRADO", "#ef4444", 3000)
            return
        
        # Invitado encontrado
        print(f"[OK] ✅ Invitado: {invitado['nombre']} {invitado['apellido']}")
        print(f"[OK] Mesa: {invitado.get('mesa', 'Sin mesa')}")
        print(f"[OK] Evento ID: {invitado['evento_id']}")
        
        # Verificar que sea del evento correcto
        if invitado['evento_id'] != self.evento['id']:
            print(f"[ERROR] ❌ Evento incorrecto")
            print(f"[INFO] QR es de evento {invitado['evento_id']}, kiosco es evento {self.evento['id']}")
            self.mostrar_overlay("❌ QR DE OTRO EVENTO", "#ef4444", 3000)
            return
        
        # Verificar si ya está presente
        if invitado.get('presente'):
            print(f"[WARN] ⚠️ Ya está acreditado")
            nombre = f"{invitado['nombre']} {invitado['apellido']}"
            
            # Verificar configuración mostrar_mesa
            mostrar_mesa = self.evento.get('mostrar_mesa', 1)
            
            if mostrar_mesa and invitado.get('mesa'):
                mesa_texto = f"Mesa {invitado['mesa']}"
                self.mostrar_overlay(f"⚠️ YA ACREDITADO\n{nombre}\n{mesa_texto}", "#f59e0b", 3000)
            else:
                self.mostrar_overlay(f"⚠️ YA ACREDITADO\n{nombre}", "#f59e0b", 3000)
            return
        
        # ACREDITAR
        print(f"[ACCIÓN] Acreditando invitado ID={invitado['id']}...")
        resultado = db.acreditar_invitado(invitado['id'], self.evento['id'], self.kiosco_id)
        
        if not resultado:
            print(f"[ERROR] ❌ Fallo al acreditar en BD")
            self.mostrar_overlay("❌ ERROR AL ACREDITAR", "#ef4444", 3000)
            return
        
        print(f"[OK] ✅ Acreditación exitosa")
        
        # Buscar video
        video_personalizado = invitado.get('video_personalizado')
        video_mesa = None
        
        if not video_personalizado and invitado.get('mesa'):
            print(f"[VIDEO] Buscando video de mesa {invitado['mesa']}...")
            video_mesa = db.obtener_video_por_mesa(self.evento['id'], invitado['mesa'])
            if video_mesa:
                print(f"[VIDEO] Video de mesa encontrado: {video_mesa}")
        
        video_a_reproducir = video_personalizado or video_mesa
        
        if video_a_reproducir and os.path.exists(video_a_reproducir):
            print(f"[VIDEO] Reproduciendo: {video_a_reproducir}")
            self.reproducir_video_temporal(invitado, video_a_reproducir)
        else:
            # Solo overlay
            print(f"[VIDEO] Sin video, solo overlay")
            nombre = f"{invitado['nombre']} {invitado['apellido']}"
            
            # Verificar si debe mostrar mesa (configuración del evento)
            mostrar_mesa = self.evento.get('mostrar_mesa', 1)  # Default: sí mostrar
            
            if mostrar_mesa and invitado.get('mesa'):
                mesa_texto = f"MESA {invitado['mesa']}"
                self.mostrar_overlay(f"✅ BIENVENIDO\n{nombre}\n{mesa_texto}", "#10b981", 3000)
            else:
                self.mostrar_overlay(f"✅ BIENVENIDO\n{nombre}", "#10b981", 3000)
        
        print(f"[FIN] Proceso completado\n")
    
    def reproducir_video_temporal(self, invitado, video_path):
        """Reproducir video personalizado/mesa con VLC (audio incluido)"""
        print(f"[KIOSCO] Iniciando video temporal: {video_path}")

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
        """Reproducir video temporal con VLC (con audio)"""
        try:
            # Crear player temporal
            self.vlc_temp_instance = vlc.Instance(['--no-xlib', '--quiet', '--no-video-title-show'])
            self.vlc_temp_player = self.vlc_temp_instance.media_player_new()

            # Crear media (SIN loop, solo una vez)
            self.vlc_temp_media = self.vlc_temp_instance.media_new(video_path)
            self.vlc_temp_player.set_media(self.vlc_temp_media)

            # Renderizar en el mismo label
            if os.name == 'nt':
                self.vlc_temp_player.set_hwnd(self.video_label.winfo_id())
            else:
                self.vlc_temp_player.set_xwindow(self.video_label.winfo_id())

            # Reproducir
            self.vlc_temp_player.play()
            print(f"[KIOSCO] Video temporal VLC iniciado con audio")

            # Monitorear cuando termine
            self.after(500, self._check_video_temporal_end)

        except Exception as e:
            print(f"[ERROR] Error VLC temporal: {e}, usando OpenCV...")
            self._reproducir_video_temporal_opencv(video_path)

    def _check_video_temporal_end(self):
        """Verificar si video temporal terminó"""
        try:
            if not hasattr(self, 'vlc_temp_player') or not self.vlc_temp_player:
                return

            state = self.vlc_temp_player.get_state()

            if state == vlc.State.Ended or state == vlc.State.Stopped:
                # Video terminó - limpiar
                print(f"[KIOSCO] Video temporal finalizado")
                self.vlc_temp_player.stop()
                self.vlc_temp_player.release()
                self.vlc_temp_player = None
                self.vlc_temp_instance.release()
                self.vlc_temp_instance = None

                # Mostrar overlay con info del invitado
                self._mostrar_overlay_bienvenida()
            else:
                # Seguir monitoreando
                self.after(300, self._check_video_temporal_end)
        except Exception as e:
            print(f"[ERROR] Error verificando video temporal: {e}")
            self._mostrar_overlay_bienvenida()

    def _mostrar_overlay_bienvenida(self):
        """Mostrar overlay de bienvenida después del video"""
        invitado = self.invitado_temp
        nombre = f"{invitado['nombre']} {invitado['apellido']}"

        mostrar_mesa = self.evento.get('mostrar_mesa', 1)

        if mostrar_mesa and invitado.get('mesa'):
            mesa_texto = f"MESA {invitado['mesa']}"
            self.mostrar_overlay(f"✅ BIENVENIDO\n{nombre}\n{mesa_texto}", "#10b981", 3000)
        else:
            self.mostrar_overlay(f"✅ BIENVENIDO\n{nombre}", "#10b981", 3000)

        # Reanudar video principal después del overlay
        self.after(3000, lambda: self.reanudar_video_principal(self.video_principal_activo_backup))

    def _reproducir_video_temporal_opencv(self, video_path):
        """Fallback: Reproducir video temporal con OpenCV (sin audio)"""
        try:
            import cv2
            from PIL import Image, ImageTk

            invitado = self.invitado_temp

            cap_temp = cv2.VideoCapture(video_path)

            if not cap_temp.isOpened():
                print(f"[ERROR] No se pudo abrir video temporal")
                nombre = f"{invitado['nombre']} {invitado['apellido']}"
                mesa = f"MESA {invitado['mesa']}" if invitado.get('mesa') else ""
                self.mostrar_overlay(f"✅ BIENVENIDO\n{nombre}\n{mesa}", "#10b981", 3000)
                self.after(3000, lambda: self.reanudar_video_principal(self.video_principal_activo_backup))
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
            # Mostrar overlay
            nombre = f"{invitado['nombre']} {invitado['apellido']}"
            mesa = f"MESA {invitado['mesa']}" if invitado.get('mesa') else ""
            self.mostrar_overlay(f"✅ BIENVENIDO\n{nombre}\n{mesa}", "#10b981", 3000)
    
    def reanudar_video_principal(self, estado_previo):
        """Reanudar video loop principal"""
        print(f"[KIOSCO] Reanudando video principal")
        self.video_activo = estado_previo
        if self.video_activo:
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
        """Captura global de teclado - SIEMPRE activa"""
        try:
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
