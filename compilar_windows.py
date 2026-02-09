"""
Script de compilacion para WelcomeX
"""
import os
import sys
import shutil
import subprocess

print("=" * 60)
print("COMPILANDO WELCOMEX CON SISTEMA DE LICENCIAS")
print("=" * 60)

# Verificar que PyInstaller este instalado
try:
    import PyInstaller
    print("[OK] PyInstaller encontrado")
except ImportError:
    print("[!] PyInstaller no esta instalado")
    print("Instalando PyInstaller...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])

# Limpiar builds anteriores
if os.path.exists("build"):
    print("[*] Limpiando build anterior...")
    shutil.rmtree("build")

if os.path.exists("dist"):
    print("[*] Limpiando dist anterior...")
    shutil.rmtree("dist")

# Compilar usando el .spec existente
print("\n[*] Compilando con PyInstaller...")
print("Esto puede tardar 5-10 minutos...\n")

result = subprocess.run([
    sys.executable,
    "-m",
    "PyInstaller",
    "WelcomeX.spec",
    "--clean",
    "--noconfirm"
], capture_output=False)

if result.returncode == 0:
    print("\n" + "=" * 60)
    print("[OK] COMPILACION EXITOSA")
    print("=" * 60)
    print(f"[>] Ejecutable en: {os.path.abspath('dist/WelcomeX.exe')}")
    print("\n[>] El .exe tiene el sistema de licencias activo")
    print("[>] Conectado a: https://pampaguazu.com.ar")
    print("\n[!] IMPORTANTE:")
    print("   - Al ejecutar pedira la licencia")
    print("=" * 60)
else:
    print("\n[ERROR] Error en la compilacion")
    sys.exit(1)
