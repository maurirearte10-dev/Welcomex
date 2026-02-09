"""
Splash Screen con video de introducción y transición suave
"""
import customtkinter as ctk
import cv2
from PIL import Image, ImageTk, ImageEnhance
import os

class SplashScreen(ctk.CTkToplevel):
    def __init__(self, parent, video_path, callback):
        super().__init__(parent)
        
        self.callback = callback
        self.video_path = video_path
        
        # Configuración ventana
        self.title("")
        self.overrideredirect(True)  # Sin bordes
        
        # Obtener tamaño pantalla
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Centrar ventana (tamaño video)
        width = 800
        height = 600
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.configure(fg_color="#000000")
        
        # Frame principal
        self.main_frame = ctk.CTkFrame(self, fg_color="#000000")
        self.main_frame.pack(fill="both", expand=True)
        
        # Label para video
        self.video_label = ctk.CTkLabel(self.main_frame, text="")
        self.video_label.pack(fill="both", expand=True)
        
        # NO permitir cerrar con click (más sutil)
        # self.video_label.bind("<Button-1>", lambda e: self.cerrar())
        
        # Variables
        self.video_activo = True
        self.cap = None
        self.en_fade_out = False
        self.fade_alpha = 1.0
        
        # Iniciar video después de que la ventana esté lista
        self.after(100, self.iniciar_video)
    
    def iniciar_video(self):
        """Iniciar reproducción del video"""
        if not os.path.exists(self.video_path):
            print(f"[SPLASH] Video no encontrado: {self.video_path}")
            self.cerrar()
            return
        
        try:
            self.cap = cv2.VideoCapture(self.video_path)
            
            if not self.cap.isOpened():
                print("[SPLASH] No se pudo abrir video")
                self.cerrar()
                return
            
            # Obtener FPS del video
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            if self.fps == 0:
                self.fps = 30
            
            self.delay = int(1000 / self.fps)
            
            # Obtener dimensiones del video
            self.video_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.video_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # Ajustar ventana al tamaño del video
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            
            # Escalar si es muy grande
            if self.video_width > screen_width * 0.8:
                scale = (screen_width * 0.8) / self.video_width
                self.video_width = int(self.video_width * scale)
                self.video_height = int(self.video_height * scale)
            
            if self.video_height > screen_height * 0.8:
                scale = (screen_height * 0.8) / self.video_height
                self.video_width = int(self.video_width * scale)
                self.video_height = int(self.video_height * scale)
            
            # Reposicionar ventana
            x = (screen_width - self.video_width) // 2
            y = (screen_height - self.video_height) // 2
            self.geometry(f"{self.video_width}x{self.video_height}+{x}+{y}")
            
            print(f"[SPLASH] Video iniciado: {self.video_width}x{self.video_height} @ {self.fps}fps")
            
            # Comenzar reproducción
            self.reproducir_frame()
            
        except Exception as e:
            print(f"[SPLASH] Error al iniciar video: {e}")
            self.cerrar()
    
    def reproducir_frame(self):
        """Reproducir siguiente frame del video"""
        if not self.video_activo or not self.cap:
            return
        
        try:
            ret, frame = self.cap.read()
            
            if not ret:
                # Video terminó, iniciar fade out
                if not self.en_fade_out:
                    print("[SPLASH] Video terminado, iniciando fade out...")
                    self.en_fade_out = True
                    self.iniciar_fade_out()
                return
            
            # Convertir BGR a RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Redimensionar al tamaño de la ventana
            frame = cv2.resize(frame, (self.video_width, self.video_height))
            
            # Convertir a imagen PIL
            image = Image.fromarray(frame)
            photo = ImageTk.PhotoImage(image)
            
            # Mostrar en label
            self.video_label.configure(image=photo)
            self.video_label.image = photo
            
            # Siguiente frame
            self.after(self.delay, self.reproducir_frame)
            
        except Exception as e:
            print(f"[SPLASH] Error reproduciendo frame: {e}")
            self.cerrar()
    
    def iniciar_fade_out(self):
        """Iniciar animación de fade out a negro"""
        self.fade_alpha = 1.0
        self.animar_fade_out()
    
    def animar_fade_out(self):
        """Animar fade out progresivo"""
        if self.fade_alpha > 0:
            # Crear frame negro con alpha
            black_frame = Image.new('RGB', (self.video_width, self.video_height), (0, 0, 0))
            
            # Aplicar transparencia inversa (más opaco cada vez)
            # fade_alpha 1.0 → negro 0% (transparente)
            # fade_alpha 0.0 → negro 100% (opaco)
            brightness = self.fade_alpha
            enhancer = ImageEnhance.Brightness(black_frame)
            faded = enhancer.enhance(1 - brightness)
            
            # Mostrar
            photo = ImageTk.PhotoImage(black_frame)
            self.video_label.configure(image=photo)
            self.video_label.image = photo
            
            # Reducir alpha
            self.fade_alpha -= 0.05  # 20 pasos = ~300ms a 60fps
            
            # Siguiente frame de fade
            self.after(15, self.animar_fade_out)
        else:
            # Fade completado, mantener negro 200ms
            self.after(200, self.cerrar)
    
    def cerrar(self):
        """Cerrar splash screen"""
        self.video_activo = False
        
        if self.cap:
            self.cap.release()
        
        self.destroy()
        
        # Llamar callback para mostrar ventana principal
        if self.callback:
            self.callback()
