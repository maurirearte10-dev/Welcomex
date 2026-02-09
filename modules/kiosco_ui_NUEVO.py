import customtkinter as ctk
import os

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
    def __init__(self, parent, evento, orientacion="horizontal"):
        super().__init__(parent)
        
        self.evento = evento
        self.orientacion = orientacion
        self.title(f"Kiosco - {evento['nombre']}")
        
        # Geometría
        if orientacion == "vertical":
            self.geometry("1280x720")
        else:
            self.geometry("1920x1080")
        
        self.configure(fg_color="#000000")
        
        # Estado
        self.video_activo = False
        self.qr_buffer = ""
        
        # Bindings
        self.bind('<F11>', lambda e: self.toggle_fullscreen())
        self.bind('<Escape>', lambda e: self.confirmar_cerrar())
        self.bind('<Key>', self.capturar_tecla)
        
        # Frame principal (negro)
        self.main_frame = ctk.CTkFrame(self, fg_color="#000000")
        self.main_frame.pack(fill="both", expand=True)
        
        # Label para video
        self.video_label = ctk.CTkLabel(self.main_frame, text="")
        self.video_label.place(x=0, y=0, relwidth=1, relheight=1)
        
        # Verificar si hay video
        self.video_path = evento.get('video_loop')
        
        if self.video_path and os.path.exists(self.video_path):
            print(f"[KIOSCO] Iniciando video: {self.video_path}")
            self.after(100, self.iniciar_video)
        else:
            print(f"[KIOSCO] Sin video, mostrando mensaje")
            self.mostrar_mensaje_inicial()
    
    def iniciar_video(self):
        """Iniciar video loop"""
        try:
            import cv2
            from PIL import Image, ImageTk
            
            self.video_activo = True
            self.cap = cv2.VideoCapture(self.video_path)
            
            if not self.cap.isOpened():
                print(f"[ERROR] No se pudo abrir video")
                self.mostrar_mensaje_inicial()
                return
            
            print(f"[KIOSCO] Video abierto OK")
            self.reproducir_frame()
            
        except ImportError:
            print(f"[ERROR] OpenCV no instalado")
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
            
            self.after(33, self.reproducir_frame)
            
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
        elif event.keysym == 'Return':
            if self.qr_buffer:
                self.procesar_qr(self.qr_buffer)
                self.qr_buffer = ""
    
    def procesar_qr(self, qr_code):
        """Procesar código QR"""
        print(f"[KIOSCO] QR recibido: {qr_code}")
        
        # Importar database
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from modules.database import Database
        
        db = Database()
        invitado = db.obtener_invitado_por_qr(qr_code)
        
        if not invitado:
            self.mostrar_overlay("❌ QR INVÁLIDO", "#ef4444", 2000)
            return
        
        if invitado['evento_id'] != self.evento['id']:
            self.mostrar_overlay("❌ EVENTO INCORRECTO", "#ef4444", 2000)
            return
        
        if invitado['presente']:
            nombre = f"{invitado['nombre']} {invitado['apellido']}"
            mesa = f"Mesa {invitado['mesa']}" if invitado.get('mesa') else ""
            self.mostrar_overlay(f"⚠️ YA ACREDITADO\n{nombre}\n{mesa}", "#f59e0b", 3000)
            return
        
        # Acreditar
        db.acreditar_invitado(invitado['id'], self.evento['id'])
        
        nombre = f"{invitado['nombre']} {invitado['apellido']}"
        mesa = f"MESA {invitado['mesa']}" if invitado.get('mesa') else ""
        self.mostrar_overlay(f"✅ BIENVENIDO\n{nombre}\n{mesa}", "#10b981", 3000)
    
    def mostrar_overlay(self, texto, color, duracion):
        """Mostrar overlay temporal"""
        if hasattr(self, 'overlay'):
            self.overlay.destroy()
        
        self.overlay = ctk.CTkFrame(self.main_frame, 
                                   fg_color=color,
                                   corner_radius=20)
        self.overlay.place(relx=0.5, rely=0.5, anchor="center")
        
        ctk.CTkLabel(self.overlay, 
                    text=texto,
                    font=("Arial", 60, "bold"),
                    text_color="#ffffff").pack(padx=80, pady=60)
        
        self.after(duracion, lambda: self.overlay.destroy() if hasattr(self, 'overlay') else None)
    
    def toggle_fullscreen(self):
        """Toggle fullscreen"""
        current = self.attributes('-fullscreen')
        self.attributes('-fullscreen', not current)
    
    def confirmar_cerrar(self):
        """Confirmar cierre"""
        self.video_activo = False
        if hasattr(self, 'cap'):
            self.cap.release()
        self.destroy()
