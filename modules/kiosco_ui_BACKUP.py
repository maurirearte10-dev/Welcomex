"""
Kiosco UI - Ventana independiente para escanear QR con video loop
"""

import customtkinter as ctk
from modules.database import db
from config.settings import COLORS
import os

class KioscoWindow(ctk.CTkToplevel):
    def __init__(self, parent, evento, orientacion="horizontal"):
        super().__init__(parent)
        
        self.evento = evento
        self.orientacion = orientacion
        self.title(f"Kiosco - {evento['nombre']}")
        
        # Geometría según orientación
        if orientacion == "vertical":
            # Para TV vertical: ventana HORIZONTAL que se verá vertical al rotar TV
            # 1280 ancho x 720 alto = Se ve vertical cuando TV está parada
            self.geometry("1280x720")  # Horizontal para que TV rotada lo muestre vertical
        else:
            # Ventana horizontal normal
            self.geometry("1920x1080")
        
        self.configure(fg_color=COLORS["bg"])
        
        # Estado
        self.fullscreen = False
        self.animando = False
        self.video_activo = False
        self.video_player = None
        
        # Verificar si hay video
        self.video_path = evento.get('video_loop')
        
        # Bindings
        self.bind('<F11>', lambda e: self.toggle_fullscreen())
        self.bind('<Escape>', lambda e: self.confirmar_cerrar())
        
        self.crear_ui()
        
        # Debug: Verificar video
        print(f"[DEBUG] Video path: {self.video_path}")
        
        # Iniciar video si existe
        if self.video_path:
            if os.path.exists(self.video_path):
                print(f"[DEBUG] Video existe, iniciando...")
                self.after(200, self.iniciar_video)  # Delay para que UI se renderice
            else:
                print(f"[DEBUG] Video NO existe en: {self.video_path}")
                self.after(100, lambda: self.entry_qr.focus())
        else:
            print(f"[DEBUG] No hay video configurado")
            self.after(100, lambda: self.entry_qr.focus())
    
    def iniciar_video(self):
        """Iniciar reproducción de video como fondo"""
        print(f"[DEBUG] Iniciando video como fondo...")
        try:
            import cv2
            from PIL import Image, ImageTk
            
            print(f"[DEBUG] OpenCV importado OK")
            self.video_activo = True
            
            # Crear label para video DETRÁS de todo
            self.video_label = ctk.CTkLabel(self.main, text="")
            self.video_label.place(x=0, y=0, relwidth=1, relheight=1)
            print(f"[DEBUG] Video label creado como fondo")
            
            # Enviar al fondo
            self.video_label.lower()
            
            # Asegurar que el container esté visible encima
            self.container.lift()
            
            # Forzar actualización
            self.update_idletasks()
            
            # Abrir video
            self.cap = cv2.VideoCapture(self.video_path)
            
            if not self.cap.isOpened():
                print(f"[ERROR] No se pudo abrir video: {self.video_path}")
                self.video_activo = False
                if hasattr(self, 'video_label'):
                    self.video_label.destroy()
                return
            
            print(f"[DEBUG] Video abierto correctamente")
            
            # Obtener FPS del video
            self.video_fps = self.cap.get(cv2.CAP_PROP_FPS)
            if self.video_fps == 0:
                self.video_fps = 30
            
            print(f"[DEBUG] FPS del video: {self.video_fps}")
            
            # Reproducir loop
            self.reproducir_frame()
            
            # Focus en el entry
            self.after(500, lambda: self.entry_qr.focus())
            
        except ImportError as e:
            print(f"[ERROR] OpenCV no instalado: {e}")
            self.video_activo = False
            self.after(100, lambda: self.entry_qr.focus())
        except Exception as e:
            print(f"[ERROR] Error inesperado: {e}")
            self.video_activo = False
            self.mostrar_container()
            self.after(100, lambda: self.entry_qr.focus())
    
    def reproducir_frame(self):
        """Reproducir frame de video"""
        if not self.video_activo or not hasattr(self, 'video_label'):
            return
        
        try:
            import cv2
            from PIL import Image, ImageTk
            
            ret, frame = self.cap.read()
            
            if not ret:
                # Reiniciar video (loop)
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            
            if ret:
                # Convertir BGR a RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Obtener tamaño de la ventana
                window_width = self.winfo_width()
                window_height = self.winfo_height()
                
                if window_width > 1 and window_height > 1:
                    # Redimensionar frame para llenar ventana
                    frame = cv2.resize(frame, (window_width, window_height))
                
                # Convertir a ImageTk
                img = Image.fromarray(frame)
                imgtk = ImageTk.PhotoImage(image=img)
                
                # Actualizar label
                self.video_label.configure(image=imgtk)
                self.video_label.image = imgtk  # Mantener referencia
            
            # Siguiente frame (30 FPS)
            self.after(33, self.reproducir_frame)
            
        except Exception as e:
            print(f"[ERROR] Error reproduciendo frame: {e}")
            self.video_activo = False
    
    def detener_video(self):
        """Detener video temporalmente (ya no necesario con video de fondo)"""
        # El video sigue como fondo, solo cambiamos el contenido del container
        pass
    
    def reanudar_video(self):
        """Reanudar video (ya no necesario con video de fondo)"""
        # El video siempre está activo de fondo
        pass
    
    def mostrar_container(self):
        """Mostrar container normal (siempre visible con nuevo diseño)"""
        # Container siempre está visible encima del video
        pass
    
    def toggle_fullscreen(self):
        """Toggle fullscreen"""
        self.fullscreen = not self.fullscreen
        self.attributes('-fullscreen', self.fullscreen)
        if self.fullscreen:
            self.attributes('-topmost', True)
        else:
            self.attributes('-topmost', False)
    
    def confirmar_cerrar(self):
        """Confirmar antes de cerrar"""
        # Detener video
        self.video_activo = False
        if hasattr(self, 'cap'):
            self.cap.release()
        
        # Crear diálogo simple
        dialog = ctk.CTkToplevel(self)
        dialog.title("Cerrar Kiosco")
        dialog.geometry("400x200")
        dialog.transient(self)
        dialog.grab_set()
        
        # Centrar en pantalla
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 200
        y = (dialog.winfo_screenheight() // 2) - 100
        dialog.geometry(f"400x200+{x}+{y}")
        
        ctk.CTkLabel(dialog, text="⚠️", font=("Arial", 40)).pack(pady=20)
        ctk.CTkLabel(dialog, text="¿Cerrar modo kiosco?", 
                    font=("Arial", 18, "bold")).pack(pady=10)
        
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        def cerrar():
            dialog.destroy()
            self.destroy()
        
        def cancelar():
            dialog.destroy()
            # Reanudar video
            if self.video_path and os.path.exists(self.video_path):
                self.reanudar_video()
        
        ctk.CTkButton(btn_frame, text="Sí, Cerrar", command=cerrar,
                     width=150, height=45, fg_color=COLORS["danger"]).pack(side="left", padx=10)
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=cancelar,
                     width=150, height=45, fg_color="transparent",
                     border_width=2, border_color=COLORS["border"]).pack(side="left", padx=10)
    
    def crear_ui(self):
        """Crear interfaz del kiosco - VIDEO PRIMERO"""
        # Frame principal
        self.main = ctk.CTkFrame(self, fg_color="#000000")  # Negro
        self.main.pack(fill="both", expand=True)
        
        # SOLO crear label para video (sin UI encima inicialmente)
        # La UI aparecerá como overlay cuando sea necesario
        
        # Binding para entrada de QR (invisible pero funcional)
        self.bind('<Key>', self.capturar_tecla)
        self.qr_buffer = ""
        
        print("[DEBUG] UI configurada - Modo video prioritario")
        
        # Tamaños según orientación
        if self.orientacion == "vertical":
            # Diseño acostado (base a la derecha cuando TV está vertical)
            titulo_size = 42
            fecha_size = 16
            icono_size = 90
            estado_size = 28
            entry_width = 450
            btn_width = 450
        else:
            titulo_size = 56
            fecha_size = 20
            icono_size = 80
            estado_size = 28
            entry_width = 600
            btn_width = 400
        
        # Logo/Título animado
        self.label_titulo = ctk.CTkLabel(self.container, text=self.evento['nombre'], 
                    font=("Arial", titulo_size, "bold"),
                    text_color=COLORS["primary"])
        self.label_titulo.pack(pady=(50, 20))
        
        # Fecha del evento
        fecha_text = f"📅 {self.evento.get('fecha_evento', '')}"
        ctk.CTkLabel(self.container, text=fecha_text, 
                    font=("Arial", fecha_size),
                    text_color=COLORS["text_light"]).pack(pady=(0, 40))
        
        # Instrucciones con ícono grande
        self.label_icono = ctk.CTkLabel(self.container, text="📱", 
                                       font=("Arial", icono_size))
        self.label_icono.pack(pady=20)
        
        self.label_estado = ctk.CTkLabel(self.container, 
                                         text="Acerca tu código QR al lector",
                                         font=("Arial", estado_size),
                                         text_color=COLORS["text"])
        self.label_estado.pack(pady=20)
        
        # Entry para QR con mejor diseño
        entry_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        entry_frame.pack(pady=30)
        
        self.entry_qr = ctk.CTkEntry(entry_frame, width=entry_width, height=70, 
                                     font=("Arial", 24),
                                     placeholder_text="Código QR...",
                                     fg_color=COLORS["card"],
                                     border_color=COLORS["primary"],
                                     border_width=3,
                                     corner_radius=15)
        self.entry_qr.pack(pady=10)
        self.entry_qr.bind('<Return>', lambda e: self.procesar_qr())
        
        # Botón grande
        self.btn_acreditar = ctk.CTkButton(self.container, text="✓ Acreditar", 
                                          command=self.procesar_qr,
                                          width=btn_width, height=70, 
                                          font=("Arial", 24, "bold"),
                                          fg_color=COLORS["success"],
                                          hover_color="#0d8c5f",
                                          corner_radius=15)
        self.btn_acreditar.pack(pady=20)
        
        # Info adicional
        self.label_info = ctk.CTkLabel(self.container, text="", 
                                      font=("Arial", 22, "bold"))
        self.label_info.pack(pady=30)
        
        # Footer con ayuda
        footer = ctk.CTkFrame(self.main, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=30, pady=20)
        
        if self.orientacion == "vertical":
            # En vertical: todo centrado, uno arriba del otro
            ctk.CTkLabel(footer, text="F11: Pantalla completa  |  ESC: Salir", 
                        font=("Arial", 14), text_color=COLORS["text_light"]).pack(pady=5)
            
            self.label_contador = ctk.CTkLabel(footer, text="Acreditados hoy: 0", 
                        font=("Arial", 16, "bold"), text_color=COLORS["primary"])
            self.label_contador.pack(pady=5)
        else:
            # En horizontal: uno a cada lado
            ctk.CTkLabel(footer, text="F11: Pantalla completa  |  ESC: Salir", 
                        font=("Arial", 14), text_color=COLORS["text_light"]).pack(side="left")
            
            self.label_contador = ctk.CTkLabel(footer, text="Acreditados hoy: 0", 
                        font=("Arial", 14, "bold"), text_color=COLORS["primary"])
            self.label_contador.pack(side="right")
        
        self.contador_hoy = 0
    
    def procesar_qr(self):
        """Procesar código QR escaneado"""
        if self.animando:
            return
        
        qr_code = self.entry_qr.get().strip()
        
        if not qr_code:
            return
        
        self.animando = True
        
        # PAUSAR VIDEO si está activo
        if self.video_activo:
            self.detener_video()
        
        # Deshabilitar entrada
        self.entry_qr.configure(state="disabled")
        self.btn_acreditar.configure(state="disabled")
        
        # Acreditar
        resultado = db.acreditar_invitado(qr_code, self.evento['id'])
        
        if resultado["success"]:
            invitado = resultado["invitado"]
            tipo = resultado["tipo"]
            
            # Incrementar contador
            if tipo == "ingreso":
                self.contador_hoy += 1
                self.label_contador.configure(text=f"Acreditados hoy: {self.contador_hoy}")
            
            # Animación de éxito
            self.animar_exito(invitado, tipo)
        else:
            self.animar_error(resultado.get("error", "Error desconocido"))
        
        # Limpiar entry
        self.entry_qr.delete(0, 'end')
    
    def animar_exito(self, invitado, tipo):
        """Animación de éxito con transición suave"""
        # Cambiar colores
        color = COLORS["success"] if tipo == "ingreso" else COLORS["warning"]
        icono = "✅" if tipo == "ingreso" else "🚪"
        
        # Animar ícono
        self.label_icono.configure(text=icono)
        
        # Cambiar estado
        texto_tipo = "¡BIENVENIDO!" if tipo == "ingreso" else "¡HASTA PRONTO!"
        self.label_estado.configure(text=texto_tipo, text_color=color)
        
        # Mostrar info invitado
        nombre_completo = f"{invitado['apellido']}, {invitado['nombre']}"
        mesa = invitado.get('mesa', 'N/A')
        
        self.label_info.configure(
            text=f"{nombre_completo}\n\nMesa: {mesa}",
            text_color=color
        )
        
        # Animación de pulso en el entry
        self.entry_qr.configure(border_color=color)
        
        # Volver al estado normal después de 3 segundos
        self.after(3000, self.reset_ui)
    
    def animar_error(self, mensaje):
        """Animación de error"""
        # Cambiar a rojo
        self.label_icono.configure(text="❌")
        self.label_estado.configure(text="ERROR", text_color=COLORS["danger"])
        
        # Mostrar mensaje
        self.label_info.configure(
            text=f"{mensaje}",
            text_color=COLORS["danger"]
        )
        
        self.entry_qr.configure(border_color=COLORS["danger"])
        
        # Volver después de 3 segundos
        self.after(3000, self.reset_ui)
    
    def reset_ui(self):
        """Resetear UI a estado inicial con animación"""
        # Restaurar colores
        self.label_icono.configure(text="📱")
        self.label_estado.configure(text="Acerca tu código QR al lector",
                                   text_color=COLORS["text"])
        self.label_info.configure(text="")
        self.entry_qr.configure(border_color=COLORS["primary"])
        
        # Rehabilitar entrada
        self.entry_qr.configure(state="normal")
        self.btn_acreditar.configure(state="normal")
        
        self.animando = False
        
        # REANUDAR VIDEO si existe
        if self.video_path and os.path.exists(self.video_path):
            self.reanudar_video()
        else:
            self.entry_qr.focus()
