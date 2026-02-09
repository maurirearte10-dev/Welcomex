# 🚀 INICIO RÁPIDO - WELCOMEX

## ⚡ OPCIÓN 1: AUTOMÁTICO (RECOMENDADO)

### Windows:
```
Doble click en: SETUP.bat
```

Ese script hace TODO automáticamente:
- ✅ Detecta si es primera vez o actualización
- ✅ Ejecuta migraciones necesarias
- ✅ Crea super admin (si es primera vez)
- ✅ Inicia el programa

---

## 🔧 OPCIÓN 2: MANUAL

### Primera Vez (BD Nueva):
```powershell
python -m pip install -r requirements.txt
python crear_super_admin.py
python migrar_kioscos_multiples.py
python main.py
```

### Con BD Existente:
```powershell
python migrar_mesas_videos.py
python migrar_kioscos_multiples.py
python main.py
```

---

## 🔑 CREDENCIALES SUPER ADMIN

```
Email: mrearte21@hotmail.com
Password: Malvinas!09
```

---

## ✅ CHECKLIST

- [ ] Instalaste Python 3.9+
- [ ] Instalaste dependencias (requirements.txt)
- [ ] Ejecutaste crear_super_admin.py (primera vez)
- [ ] Ejecutaste migraciones (migrar_*.py)
- [ ] Iniciaste el programa (main.py)

---

## 📁 ESTRUCTURA

```
WelcomeX_DEFINITIVO/
├── SETUP.bat                    ← Doble click aquí (automático)
├── main.py                      ← Programa principal
├── crear_super_admin.py         ← Setup inicial
├── migrar_mesas_videos.py       ← Migración 1
├── migrar_kioscos_multiples.py  ← Migración 2
└── requirements.txt             ← Dependencias
```

---

## 🆘 PROBLEMAS

**"ModuleNotFoundError"**
→ `python -m pip install -r requirements.txt`

**"Base de datos bloqueada"**
→ Cierra todas las ventanas de WelcomeX

**"No existe super admin"**
→ `python crear_super_admin.py`

**"Columna no existe"**
→ Ejecuta todas las migraciones en orden

---

## 🎯 PRÓXIMOS PASOS

1. ✅ Ejecutar setup
2. Login con credenciales
3. Crear evento
4. Importar invitados
5. Configurar videos
6. Configurar kioscos múltiples
7. ¡Listo para tu evento!
