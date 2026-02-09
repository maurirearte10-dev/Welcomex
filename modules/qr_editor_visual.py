"""
Editor Visual de QR - Arrastre con Mouse
"""
import customtkinter as ctk
from tkinter import Canvas
from PIL import Image, ImageTk, ImageDraw
import qrcode
import os

class QREditorVisual(ctk.CTkToplevel):
    def __init__(self, parent, plantilla_path, callback):
        super().__init__(parent)
        
        self.plantilla_path = plantilla_path
        self.callback = callback
        
        self.title("Editor Visual de QR")
        self.geometry("1400x900")
        self.transient(parent)
        self.grab_set()
        
        # Centrar
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 700
        y = (self.winfo_screenheight() // 2) - 450
        self.geometry(f"1400x900+{x}+{y}")
        
        # Configuración QR
        self.qr_x = 290  # Centro horizontal para plantilla 1080px
        self.qr_y = 1400  # Abajo para plantilla 1920px
        self.qr_size = 500
        
        # Estado arrastre
        self.dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        
        # Cargar plantilla
        try:
            plantilla_original = Image.open(plantilla_path).convert('RGB')
            
            # Mantener aspect ratio
            width = 1080
            height = 1920
            plantilla_ratio = plantilla_original.width / plantilla_original.height
            target_ratio = width / height
            
            if plantilla_ratio != target_ratio:
                # Necesita ajuste
                if plantilla_ratio > target_ratio:
                    # Plantilla más ancha
                    new_height = height
                    new_width = int(height * plantilla_ratio)
                else:
                    # Plantilla más alta
                    new_width = width
                    new_height = int(width / plantilla_ratio)
                
                # Redimensionar manteniendo ratio
                plantilla_resized = plantilla_original.resize((new_width, new_height), 
                                                             Image.Resampling.LANCZOS)
                
                # Crear canvas negro
                self.plantilla = Image.new('RGB', (width, height), "#000000")
                
                # Centrar plantilla
                x_offset = (width - new_width) // 2
                y_offset = (height - new_height) // 2
                self.plantilla.paste(plantilla_resized, (x_offset, y_offset))
                
                print(f"[EDITOR] Plantilla ajustada: {plantilla_original.size} → centrada en {(width, height)}")
            else:
                # Aspect ratio correcto
                self.plantilla = plantilla_original.resize((width, height), Image.Resampling.LANCZOS)
                
        except Exception as e:
            print(f"Error cargando plantilla: {e}")
            self.destroy()
            return
        
        self.setup_ui()
        self.actualizar_preview()
    
    def setup_ui(self):
        """Configurar interfaz"""
        # Frame principal
        main = ctk.CTkFrame(self, fg_color="#0f0f0f")
        main.pack(fill="both", expand=True)
        
        # Título
        header = ctk.CTkFrame(main, fg_color="#1a1a2e", height=60)
        header.pack(fill="x", padx=20, pady=(20, 10))
        header.pack_propagate(False)
        
        ctk.CTkLabel(header, text="🖱️ Editor Visual de QR", 
                    font=("Arial", 24, "bold")).pack(side="left", padx=20)
        
        ctk.CTkLabel(header, text="Arrastra el QR con el mouse", 
                    font=("Arial", 13), text_color="#9ca3af").pack(side="left")
        
        # Contenido
        content = ctk.CTkFrame(main, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Izquierda: Canvas
        left = ctk.CTkFrame(content, fg_color="#1a1a2e")
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        ctk.CTkLabel(left, text="Vista Previa (Arrastra el QR)",
                    font=("Arial", 14, "bold")).pack(pady=10)
        
        # Canvas para vista previa
        self.canvas = Canvas(left, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        # Bindings para arrastre
        self.canvas.bind("<Button-1>", self.mouse_down)
        self.canvas.bind("<B1-Motion>", self.mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.mouse_up)
        
        # Derecha: Controles
        right = ctk.CTkFrame(content, fg_color="#1a1a2e", width=350)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        
        ctk.CTkLabel(right, text="⚙️ Configuración",
                    font=("Arial", 18, "bold")).pack(pady=15)
        
        # Tamaño QR
        size_frame = ctk.CTkFrame(right, fg_color="transparent")
        size_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(size_frame, text="Tamaño QR:",
                    font=("Arial", 13), anchor="w").pack(fill="x")
        
        self.size_var = ctk.IntVar(value=self.qr_size)
        
        size_slider = ctk.CTkSlider(size_frame, from_=200, to=800,
                                    variable=self.size_var,
                                    command=self.on_size_change)
        size_slider.pack(fill="x", pady=5)
        
        self.size_label = ctk.CTkLabel(size_frame, text=f"{self.qr_size}px",
                                       font=("Arial", 12, "bold"),
                                       text_color="#3b82f6")
        self.size_label.pack()
        
        # Separador
        ctk.CTkFrame(right, height=2, fg_color="#4b5563").pack(fill="x", padx=20, pady=15)
        
        # Posición actual
        pos_frame = ctk.CTkFrame(right, fg_color="#2b2b3c", corner_radius=8)
        pos_frame.pack(fill="x", padx=20, pady=10)
        
        pos_inner = ctk.CTkFrame(pos_frame, fg_color="transparent")
        pos_inner.pack(padx=15, pady=12)
        
        ctk.CTkLabel(pos_inner, text="📍 Posición Actual",
                    font=("Arial", 14, "bold")).pack(pady=(0, 8))
        
        self.pos_x_label = ctk.CTkLabel(pos_inner, text=f"X: {self.qr_x}px",
                                        font=("Arial", 12))
        self.pos_x_label.pack(anchor="w")
        
        self.pos_y_label = ctk.CTkLabel(pos_inner, text=f"Y: {self.qr_y}px",
                                        font=("Arial", 12))
        self.pos_y_label.pack(anchor="w")
        
        # Info
        info_frame = ctk.CTkFrame(right, fg_color="#2b2b3c", corner_radius=8)
        info_frame.pack(fill="x", padx=20, pady=10)
        
        info_inner = ctk.CTkFrame(info_frame, fg_color="transparent")
        info_inner.pack(padx=15, pady=12)
        
        ctk.CTkLabel(info_inner, text="💡 Instrucciones",
                    font=("Arial", 13, "bold"), text_color="#f59e0b").pack(anchor="w", pady=(0, 5))
        
        ctk.CTkLabel(info_inner, text="• Arrastra el QR con el mouse",
                    font=("Arial", 11), anchor="w").pack(anchor="w", pady=2)
        ctk.CTkLabel(info_inner, text="• Ajusta tamaño con slider",
                    font=("Arial", 11), anchor="w").pack(anchor="w", pady=2)
        ctk.CTkLabel(info_inner, text="• Click fuera del QR para mover",
                    font=("Arial", 11), anchor="w").pack(anchor="w", pady=2)
        
        # Botones
        btn_frame = ctk.CTkFrame(right, fg_color="transparent")
        btn_frame.pack(fill="x", side="bottom", padx=20, pady=20)
        
        ctk.CTkButton(btn_frame, text="✅ Confirmar Posición",
                     command=self.confirmar,
                     height=50, font=("Arial", 15, "bold"),
                     fg_color="#10b981").pack(fill="x", pady=(0, 10))
        
        ctk.CTkButton(btn_frame, text="Cancelar",
                     command=self.destroy,
                     height=45, fg_color="transparent",
                     border_width=2, border_color="#4b5563").pack(fill="x")
    
    def actualizar_preview(self):
        """Actualizar vista previa"""
        # Copiar plantilla
        img = self.plantilla.copy()
        
        # Generar QR de ejemplo
        qr = qrcode.QRCode(version=1, box_size=10, border=0)
        qr.add_data("PREVIEW-QR")
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img = qr_img.resize((self.qr_size, self.qr_size), Image.Resampling.LANCZOS)
        
        # Pegar QR
        img.paste(qr_img, (self.qr_x, self.qr_y))
        
        # Dibujar borde rojo alrededor del QR
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [self.qr_x - 3, self.qr_y - 3, 
             self.qr_x + self.qr_size + 3, self.qr_y + self.qr_size + 3],
            outline="red", width=6
        )
        
        # Escalar para canvas
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width = 600
            canvas_height = 1067
        
        # Mantener aspect ratio
        img_ratio = 1080 / 1920
        canvas_ratio = canvas_width / canvas_height
        
        if canvas_ratio > img_ratio:
            new_height = canvas_height
            new_width = int(new_height * img_ratio)
        else:
            new_width = canvas_width
            new_height = int(new_width / img_ratio)
        
        preview_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Guardar escala para conversión de coordenadas
        self.scale_x = 1080 / new_width
        self.scale_y = 1920 / new_height
        
        # Mostrar en canvas
        self.photo = ImageTk.PhotoImage(preview_img)
        self.canvas.delete("all")
        self.canvas.create_image(canvas_width // 2, canvas_height // 2, 
                                image=self.photo, anchor="center")
        
        # Actualizar labels
        self.pos_x_label.configure(text=f"X: {self.qr_x}px")
        self.pos_y_label.configure(text=f"Y: {self.qr_y}px")
    
    def on_size_change(self, value):
        """Cambio de tamaño"""
        self.qr_size = int(value)
        self.size_label.configure(text=f"{self.qr_size}px")
        self.actualizar_preview()
    
    def mouse_down(self, event):
        """Mouse presionado"""
        # Convertir coordenadas canvas a coordenadas imagen
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        # Centro del canvas
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        
        # Offset desde centro
        offset_x = event.x - center_x
        offset_y = event.y - center_y
        
        # Convertir a coordenadas imagen
        img_x = int((1080 / 2) + (offset_x * self.scale_x))
        img_y = int((1920 / 2) + (offset_y * self.scale_y))
        
        # Verificar si click está dentro del QR
        if (self.qr_x <= img_x <= self.qr_x + self.qr_size and
            self.qr_y <= img_y <= self.qr_y + self.qr_size):
            self.dragging = True
            self.drag_start_x = img_x - self.qr_x
            self.drag_start_y = img_y - self.qr_y
    
    def mouse_drag(self, event):
        """Mouse arrastrando"""
        if not self.dragging:
            return
        
        # Convertir coordenadas
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        
        offset_x = event.x - center_x
        offset_y = event.y - center_y
        
        img_x = int((1080 / 2) + (offset_x * self.scale_x))
        img_y = int((1920 / 2) + (offset_y * self.scale_y))
        
        # Nueva posición
        new_x = img_x - self.drag_start_x
        new_y = img_y - self.drag_start_y
        
        # Limitar a bordes
        if 0 <= new_x <= 1080 - self.qr_size:
            self.qr_x = new_x
        
        if 0 <= new_y <= 1920 - self.qr_size:
            self.qr_y = new_y
        
        self.actualizar_preview()
    
    def mouse_up(self, event):
        """Mouse soltado"""
        self.dragging = False
    
    def confirmar(self):
        """Confirmar posición"""
        config = {
            'x': self.qr_x,
            'y': self.qr_y,
            'size': self.qr_size
        }
        
        self.destroy()
        
        if self.callback:
            self.callback(config)
