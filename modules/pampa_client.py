"""
PAMPA Client - Módulo de validación de licencias
Para integrar en WelcomeX, Tauro360, Clickear, etc.
"""
import requests
import platform
import uuid
import subprocess
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict

class PampaClient:
    """Cliente para validar licencias con PAMPA"""

    def __init__(self, program_code: str, api_url: str = "https://pampaguazu.com.ar"):
        """
        Args:
            program_code: Código del programa (WELCOME_X, TAURO_360, etc.)
            api_url: URL del servidor PAMPA
        """
        self.program_code = program_code
        self.api_url = api_url.rstrip('/')

        # Cache local
        self.cache_file = Path.home() / ".pampa" / f"{program_code}_license.json"
        self.cache_file.parent.mkdir(exist_ok=True)

    # ==============================================
    # HARDWARE FINGERPRINT
    # ==============================================

    def get_cpu_id(self) -> str:
        """Obtiene ID de CPU"""
        try:
            if platform.system() == "Windows":
                result = subprocess.check_output(
                    "wmic cpu get ProcessorId", shell=True
                ).decode().strip().split('\n')[1].strip()
                return result
            else:
                # Linux/Mac
                return str(uuid.getnode())
        except:
            return "CPU_UNKNOWN"

    def get_motherboard_serial(self) -> str:
        """Obtiene serial de motherboard"""
        try:
            if platform.system() == "Windows":
                result = subprocess.check_output(
                    "wmic baseboard get SerialNumber", shell=True
                ).decode().strip().split('\n')[1].strip()
                return result if result else "MB_UNKNOWN"
            else:
                return "MB_UNKNOWN"
        except:
            return "MB_UNKNOWN"

    def get_disk_serial(self) -> str:
        """Obtiene serial del disco principal"""
        try:
            if platform.system() == "Windows":
                result = subprocess.check_output(
                    "wmic diskdrive get SerialNumber", shell=True
                ).decode().strip().split('\n')[1].strip()
                return result if result else "DISK_UNKNOWN"
            else:
                return "DISK_UNKNOWN"
        except:
            return "DISK_UNKNOWN"

    def get_mac_address(self) -> str:
        """Obtiene MAC address"""
        try:
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                           for elements in range(0,2*6,2)][::-1])
            return mac
        except:
            return "MAC_UNKNOWN"

    def get_system_uuid(self) -> str:
        """Obtiene UUID del sistema"""
        try:
            if platform.system() == "Windows":
                result = subprocess.check_output(
                    "wmic csproduct get UUID", shell=True
                ).decode().strip().split('\n')[1].strip()
                return result if result else str(uuid.uuid4())
            else:
                return str(uuid.uuid4())
        except:
            return str(uuid.uuid4())

    def get_hardware_fingerprint(self) -> Dict[str, str]:
        """
        Obtiene los 5 identificadores de hardware

        Returns:
            Dict con cpu_id, motherboard_serial, disk_serial, mac_address, system_uuid
        """
        return {
            "cpu_id": self.get_cpu_id(),
            "motherboard_serial": self.get_motherboard_serial(),
            "disk_serial": self.get_disk_serial(),
            "mac_address": self.get_mac_address(),
            "system_uuid": self.get_system_uuid()
        }

    # ==============================================
    # CACHE LOCAL
    # ==============================================

    def save_cache(self, license_key: str, validation_result: dict):
        """Guarda validación en cache local"""
        cache_data = {
            "license_key": license_key,
            "program_code": self.program_code,
            "last_validation": datetime.now().isoformat(),
            "valid": validation_result.get("valid", False),
            "status": validation_result.get("status"),
            "expires_at": validation_result.get("expires_at"),
            "days_remaining": validation_result.get("days_remaining"),
            "message": validation_result.get("message")
        }

        with open(self.cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)

    def load_cache(self) -> Optional[dict]:
        """Carga cache local (si existe y es válido)"""
        if not self.cache_file.exists():
            return None

        try:
            with open(self.cache_file, 'r') as f:
                cache = json.load(f)

            # Verificar que no tenga más de 30 días
            last_validation = datetime.fromisoformat(cache['last_validation'])
            days_since = (datetime.now() - last_validation).days

            if days_since > 30:
                print("[PAMPA] Cache expirado (>30 días). Requiere validación online.")
                return None

            return cache

        except Exception as e:
            print(f"[PAMPA] Error leyendo cache: {e}")
            return None

    def clear_cache(self):
        """Elimina cache local"""
        if self.cache_file.exists():
            self.cache_file.unlink()

    # ==============================================
    # VALIDACIÓN
    # ==============================================

    def validate_license(self, license_key: str, force_online: bool = False) -> dict:
        """
        Valida una licencia con PAMPA

        Args:
            license_key: La clave de licencia
            force_online: Fuerza validación online (ignora cache)

        Returns:
            dict con:
                - valid (bool)
                - status (str)
                - message (str)
                - expires_at (str, optional)
                - days_remaining (int, optional)
                - used_cache (bool)
        """

        # Intentar usar cache primero (si no forzamos online)
        if not force_online:
            cache = self.load_cache()
            if cache and cache.get('license_key') == license_key:
                if cache.get('valid'):
                    print(f"[PAMPA] Usando cache local (última validación: {cache['last_validation']})")
                    cache['used_cache'] = True
                    return cache
                else:
                    print(f"[PAMPA] Cache indica licencia inválida: {cache.get('status')}")
                    cache['used_cache'] = True
                    return cache

        # Validación online
        print("[PAMPA] Validando licencia online...")

        try:
            hardware = self.get_hardware_fingerprint()

            response = requests.post(
                f"{self.api_url}/api/v1/validate",
                json={
                    "program_code": self.program_code,
                    "license_key": license_key,
                    "hardware": hardware
                },
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                result['used_cache'] = False

                # Guardar en cache
                self.save_cache(license_key, result)

                return result
            else:
                return {
                    "valid": False,
                    "status": "connection_error",
                    "message": f"Error del servidor: {response.status_code}",
                    "used_cache": False
                }

        except requests.exceptions.Timeout:
            return {
                "valid": False,
                "status": "connection_error",
                "message": "Timeout al conectar con PAMPA. Verifica tu conexión a internet.",
                "used_cache": False
            }

        except requests.exceptions.ConnectionError:
            return {
                "valid": False,
                "status": "connection_error",
                "message": "No se pudo conectar con PAMPA. Verifica tu conexión a internet.",
                "used_cache": False
            }

        except Exception as e:
            return {
                "valid": False,
                "status": "error",
                "message": f"Error inesperado: {str(e)}",
                "used_cache": False
            }

    def get_license_status(self, license_key: str) -> Optional[dict]:
        """
        Obtiene el estado de una licencia (sin validar hardware)

        Útil para mostrar info al usuario

        Returns:
            dict con información de la licencia o None si hay error
        """
        try:
            response = requests.get(
                f"{self.api_url}/api/v1/license/{license_key}/status",
                timeout=10
            )

            if response.status_code == 200:
                return response.json()
            else:
                return None

        except Exception as e:
            print(f"[PAMPA] Error obteniendo estado: {e}")
            return None

    def check_expiration_alerts(self, license_key: str) -> Optional[str]:
        """
        Verifica si la licencia está por vencer y retorna el mensaje de alerta

        Returns:
            - None si no hay alerta
            - String con el mensaje de alerta si aplica
        """
        cache = self.load_cache()
        if not cache or cache.get('license_key') != license_key:
            return None

        days_remaining = cache.get('days_remaining')
        if days_remaining is None:
            return None

        if days_remaining <= 1:
            return f"⚠️ Tu licencia vence en {days_remaining} día(s). Renueva ahora para evitar interrupciones."
        elif days_remaining <= 3:
            return f"⚠️ Tu licencia vence en {days_remaining} días."
        elif days_remaining <= 7:
            return f"ℹ️ Tu licencia vence en {days_remaining} días."

        return None

    def get_validation_info(self) -> Dict:
        """
        Obtiene información sobre el estado de validación mensual

        Returns:
            dict con:
                - last_validation (datetime o None)
                - days_since_validation (int)
                - days_until_required (int) - días hasta que se requiera conexión
                - requires_connection (bool) - True si necesita conectarse ahora
        """
        cache = self.load_cache()

        if not cache:
            return {
                "last_validation": None,
                "days_since_validation": None,
                "days_until_required": 0,
                "requires_connection": True
            }

        try:
            last_validation = datetime.fromisoformat(cache['last_validation'])
            days_since = (datetime.now() - last_validation).days
            days_until = max(0, 30 - days_since)

            return {
                "last_validation": last_validation,
                "days_since_validation": days_since,
                "days_until_required": days_until,
                "requires_connection": days_since >= 30
            }
        except:
            return {
                "last_validation": None,
                "days_since_validation": None,
                "days_until_required": 0,
                "requires_connection": True
            }

    def is_cache_expired(self) -> bool:
        """Verifica si el cache local ha expirado (>30 días)"""
        info = self.get_validation_info()
        return info.get("requires_connection", True)

    # ==============================================
    # AUTENTICACIÓN DE USUARIOS
    # ==============================================

    def login(self, email: str, password: str) -> dict:
        """
        Autenticar usuario contra PAMPA

        Args:
            email: Email del usuario
            password: Contraseña

        Returns:
            dict con:
                - success (bool)
                - usuario (dict) si success
                - licencias (list) si success
                - error (str) si no success
        """
        print("[PAMPA] Autenticando usuario online...")

        try:
            response = requests.post(
                f"{self.api_url}/api/v1/auth/login",
                json={
                    "email": email,
                    "password": password
                },
                timeout=15
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print(f"[PAMPA] ✅ Usuario autenticado: {result['usuario']['email']}")
                else:
                    print(f"[PAMPA] ❌ Error: {result.get('error')}")
                return result
            else:
                return {
                    "success": False,
                    "error": f"Error del servidor: {response.status_code}"
                }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "Timeout al conectar. Verifica tu conexión a internet."
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "error": "No se pudo conectar con el servidor. Verifica tu conexión."
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error inesperado: {str(e)}"
            }

    def register(self, email: str, password: str, nombre: str, apellido: str = "", telefono: str = "") -> dict:
        """
        Registrar usuario en PAMPA

        Args:
            email: Email del usuario
            password: Contraseña
            nombre: Nombre
            apellido: Apellido (opcional)
            telefono: Teléfono (opcional)

        Returns:
            dict con:
                - success (bool)
                - usuario (dict) si success
                - error (str) si no success
        """
        print("[PAMPA] Registrando usuario online...")

        try:
            response = requests.post(
                f"{self.api_url}/api/v1/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "nombre": nombre,
                    "apellido": apellido,
                    "telefono": telefono
                },
                timeout=15
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print(f"[PAMPA] ✅ Usuario registrado: {email}")
                else:
                    print(f"[PAMPA] ❌ Error: {result.get('error')}")
                return result
            else:
                return {
                    "success": False,
                    "error": f"Error del servidor: {response.status_code}"
                }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "Timeout al conectar. Verifica tu conexión a internet."
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "error": "No se pudo conectar con el servidor. Verifica tu conexión."
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error inesperado: {str(e)}"
            }

# ==============================================
# EJEMPLO DE USO
# ==============================================

if __name__ == "__main__":
    # Test del cliente
    print("=== PAMPA Client - Test ===\n")

    # Inicializar cliente para WelcomeX
    client = PampaClient("WELCOME_X", "http://localhost:8000")

    # Obtener huella de hardware
    print("1. Obteniendo huella de hardware...")
    hw = client.get_hardware_fingerprint()
    for key, value in hw.items():
        print(f"   {key}: {value}")

    print("\n2. Validando licencia de prueba...")
    # Reemplazar con una licencia real
    result = client.validate_license("TEST-LICENSE-KEY")

    print(f"\n   Valid: {result['valid']}")
    print(f"   Status: {result['status']}")
    print(f"   Message: {result['message']}")

    if result.get('days_remaining'):
        print(f"   Days remaining: {result['days_remaining']}")

    print("\n3. Verificando alertas...")
    alert = client.check_expiration_alerts("TEST-LICENSE-KEY")
    if alert:
        print(f"   {alert}")
    else:
        print("   Sin alertas")
