#!/usr/bin/env python3
"""
WelcomeX - Launcher con Splash Fluido
"""
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import sys

# Detectar si está corriendo como .exe empaquetado
def get_resource_path(relative_path):
    """Obtiene la ruta correcta para recursos empaquetados en .exe"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller extrae recursos a sys._MEIPASS
        return os.path.join(sys._MEIPASS, relative_path)
    # En desarrollo
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

def show_splash_and_launch():
    """Mostrar splash y lanzar app principal"""
    
    # Crear splash
    splash = ctk.CTk()
    splash.title("WelcomeX")

    # Icono
    try:
        icon_path = get_resource_path(os.path.join("assets", "icon.ico"))
        splash.iconbitmap(icon_path)
    except:
        pass

    width, height = 600, 400
    x = (splash.winfo_screenwidth() - width) // 2
    y = (splash.winfo_screenheight() - height) // 2
    splash.geometry(f"{width}x{height}+{x}+{y}")
    splash.overrideredirect(True)
    splash.configure(fg_color="#000000")
    
    container = ctk.CTkFrame(splash, fg_color="#000000")
    container.pack(fill="both", expand=True)
    
    # Logo
    try:
        logo_path = get_resource_path(os.path.join("assets", "logo.png"))
        logo_img = Image.open(logo_path).resize((250, 250), Image.Resampling.LANCZOS)
        logo_photo = ImageTk.PhotoImage(logo_img)
        ctk.CTkLabel(container, image=logo_photo, text="").pack(pady=(50, 15))
        # Mantener referencia
        container.logo_photo = logo_photo
    except:
        ctk.CTkLabel(container, text="WX", font=("Arial", 72, "bold"),
                    text_color="#3b82f6").pack(pady=(50, 15))
    
    ctk.CTkLabel(container, text="WelcomeX", font=("Arial", 28, "bold"),
                text_color="#FFFFFF").pack(pady=(5, 2))
    
    ctk.CTkLabel(container, text="Sistema de Gestión de Eventos", 
                font=("Arial", 13), text_color="#666666").pack(pady=(0, 25))
    
    progress = ctk.CTkProgressBar(container, width=400, height=8)
    progress.pack(pady=15)
    progress.set(0)
    
    status = ctk.CTkLabel(container, text="Iniciando...", 
                         font=("Arial", 11), text_color="#999999")
    status.pack(pady=8)
    
    ctk.CTkLabel(container, text="v4.7", font=("Arial", 9),
                text_color="#444444").pack(side="bottom", pady=10)
    
    # Función de animación
    def animate(step=0):
        if step < 40:
            progress.set(step / 40)
            
            if step < 10:
                status.configure(text="Iniciando sistema...")
            elif step < 20:
                status.configure(text="Cargando módulos...")
            elif step < 30:
                status.configure(text="Preparando interfaz...")
            else:
                status.configure(text="Casi listo...")
            
            splash.after(25, lambda: animate(step + 1))
        else:
            status.configure(text="¡Listo!")
            splash.after(200, launch_main)
    
    def launch_main():
        """Lanzar aplicación principal"""
        # Fade out del splash
        def fade_out(alpha=1.0):
            if alpha > 0:
                try:
                    splash.attributes('-alpha', alpha)
                except:
                    pass
                splash.after(15, lambda: fade_out(alpha - 0.1))
            else:
                splash.destroy()
                start_main_app()
        
        fade_out()
    
    def start_main_app():
        """Iniciar app principal"""
        from main import WelcomeXApp
        app = WelcomeXApp()
        app.mainloop()
    
    # Iniciar animación
    splash.after(100, animate)
    splash.mainloop()

if __name__ == "__main__":
    show_splash_and_launch()
