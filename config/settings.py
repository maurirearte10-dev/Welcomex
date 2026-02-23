"""
WelcomeX - Configuración del Sistema
"""

import os
import sys

# Versión actual de la aplicación
APP_VERSION = "1.4.2"

# Detectar si está corriendo como .exe empaquetado por PyInstaller
def is_frozen():
    """Detecta si la aplicación está corriendo como .exe"""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

def get_base_dir():
    """Obtiene el directorio base correcto según si es .exe o script Python"""
    if is_frozen():
        # Si es .exe, retorna el directorio donde está el ejecutable
        return os.path.dirname(sys.executable)
    else:
        # Si es script Python, retorna el directorio del proyecto
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_resource_dir():
    """Obtiene el directorio de recursos empaquetados en el .exe"""
    if is_frozen():
        # PyInstaller extrae archivos a sys._MEIPASS
        return sys._MEIPASS
    else:
        # En desarrollo, es el mismo que BASE_DIR
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Paths
BASE_DIR = get_base_dir()  # Directorio donde está el .exe o el proyecto
RESOURCE_DIR = get_resource_dir()  # Directorio de recursos empaquetados

# La base de datos se guarda junto al .exe (no dentro del .exe)
DATA_DIR = os.path.join(BASE_DIR, "data")
DATABASE_PATH = os.path.join(DATA_DIR, "welcomex.db")

# Crear carpeta data si no existe (importante para .exe)
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

# Colores (según especificación)
COLORS = {
    "bg": "#0f0f0f",              # Fondo negro grafito
    "sidebar": "#1a1a2e",         # Sidebar gris oscuro
    "card": "#2b2b3c",            # Cards gris carbón
    "primary": "#3b82f6",         # Azul botones importantes
    "success": "#10b981",         # Verde
    "warning": "#f59e0b",         # Amarillo
    "gold": "#f59e0b",            # Dorado (alias de warning)
    "danger": "#ef4444",          # Rojo
    "text": "#ffffff",            # Texto principal blanco
    "text_light": "#9ca3af",      # Texto secundario gris
    "border": "#4b5563",          # Bordes
    "hover": "#374151"            # Hover state
}

# Permisos por rol
PERMISOS = {
    # SUPER ADMIN - Todo acceso
    'super_admin': {
        'crear_eventos': True,
        'editar_eventos': True,
        'eliminar_eventos': True,
        'iniciar_eventos': True,
        'finalizar_eventos': True,
        'ver_invitados': True,
        'agregar_invitados': True,
        'editar_invitados': True,
        'eliminar_invitados': True,
        'importar_excel': True,
        'exportar_datos': True,
        'hacer_sorteos': True,
        'abrir_kiosco': True,
        'ver_estadisticas': True,
        'gestionar_licencias': True,
        'modificar_planes': True,
        'facturar': True,
        'crear_operarios': True,
        'editar_operarios': True
    },
    
    # ADMIN (cliente que compra) - Según su plan
    'admin': {
        'crear_eventos': True,
        'editar_eventos': True,
        'eliminar_eventos': True,
        'iniciar_eventos': True,
        'finalizar_eventos': True,
        'ver_invitados': True,
        'agregar_invitados': True,
        'editar_invitados': True,
        'eliminar_invitados': True,
        'importar_excel': True,
        'exportar_datos': True,
        'hacer_sorteos': True,
        'abrir_kiosco': True,
        'ver_estadisticas': True,
        'gestionar_licencias': False,
        'modificar_planes': False,
        'facturar': False,
        'crear_operarios': True,
        'editar_operarios': True
    },
    
    # OPERARIO - Solo escanear y agregar
    'operario': {
        'crear_eventos': False,
        'editar_eventos': False,
        'eliminar_eventos': False,
        'iniciar_eventos': False,
        'finalizar_eventos': False,
        'ver_invitados': True,
        'agregar_invitados': True,  # Solo individual
        'editar_invitados': False,
        'eliminar_invitados': False,
        'importar_excel': False,
        'exportar_datos': False,
        'hacer_sorteos': False,
        'abrir_kiosco': True,       # Solo acceso al kiosco
        'ver_estadisticas': False,
        'gestionar_licencias': False,
        'modificar_planes': False,
        'facturar': False,
        'crear_operarios': False,
        'editar_operarios': False
    }
}

# Límite fijo de operarios
MAX_OPERARIOS = 2

# Planes disponibles (a definir precios después)
PLANES = {
    'basico': {
        'nombre': 'Básico',
        'eventos_mes': 10,
        'invitados_evento': 100,
        'sorteos': False,
        'kiosco': True,
        'estadisticas': False,
        'operarios': 2  # Fijo
    },
    'medio': {
        'nombre': 'Medio',
        'eventos_mes': 25,
        'invitados_evento': 500,
        'sorteos': True,
        'kiosco': True,
        'estadisticas': True,
        'operarios': 2  # Fijo
    },
    'premium': {
        'nombre': 'Premium',
        'eventos_mes': -1,  # Ilimitado
        'invitados_evento': -1,  # Ilimitado
        'sorteos': True,
        'kiosco': True,
        'estadisticas': True,
        'operarios': 2  # Fijo
    }
}
