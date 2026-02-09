# 🎬 VIDEOS DEMO PARA WELCOMEX

## 📁 Esta Carpeta se Empaqueta con el Programa

Los videos colocados aquí se incluirán automáticamente en el ejecutable compilado.
Al iniciar el **Modo Demo**, estos videos se copian a `data/videos_demo/` y se configuran en el evento demo.

---

## 📐 Videos Necesarios

### 1. video_loop_demo.mp4 (PRINCIPAL)
- **Resolución:** 1920x1080 (Horizontal) o 1080x1920 (Vertical)
- **Duración:** 10-30 segundos (loop infinito)
- **Formato:** MP4 (H.264)
- **Uso:** Video de espera en el kiosco cuando no hay acreditación activa

### 2. Video Personalizado VIP (RECOMENDADO para demo)
```
vip_maria.mp4
```
- **Uso:** Video exclusivo para "María González" (invitada VIP del demo)
- **Propósito:** Demostrar que cada invitado puede tener su propio video personalizado
- **Contenido sugerido:** "Bienvenida María" con nombre grande, animación especial

### 3. Videos por Mesa (OPCIONAL)
Crear archivos nombrados exactamente así:
```
mesa_1.mp4
mesa_2.mp4
mesa_3.mp4
mesa_4.mp4
mesa_5.mp4
```
- **Uso:** Se muestran después de acreditar según la mesa del invitado
- Solo las mesas 1-5 tienen video demo (para demostrar la funcionalidad)

---

## 🔧 Estructura Final

```
demo_videos/
├── README.md              # Este archivo
├── video_loop_demo.mp4    # Video principal de espera (REQUERIDO)
├── vip_maria.mp4          # Video personalizado para María González (VIP)
├── mesa_1.mp4             # Video para mesa 1 (opcional)
├── mesa_2.mp4             # Video para mesa 2 (opcional)
├── mesa_3.mp4             # Video para mesa 3 (opcional)
├── mesa_4.mp4             # Video para mesa 4 (opcional)
└── mesa_5.mp4             # Video para mesa 5 (opcional)
```

---

## 🎨 Contenido Sugerido para los Videos

### video_loop_demo.mp4
- Texto: "Bienvenidos" o "Acerque su QR"
- Logo de WelcomeX o marca genérica
- Animación sutil de fondo
- Colores: Dorado/negro para coincidir con el tema

### mesa_X.mp4
- Texto: "Mesa X" con número grande
- Indicación visual de ubicación
- Animación breve (5-10 segundos)

---

## 📦 Compilación con PyInstaller

Esta carpeta se incluye automáticamente con:
```python
datas=[
    ('demo_videos', 'demo_videos'),
    ...
]
```

Al compilar:
```bash
pyinstaller main.spec --clean
```

---

## 🎬 Herramientas Gratuitas para Crear Videos

- **Canva:** canva.com - Plantillas de video gratuitas
- **CapCut:** Editor de video móvil/desktop
- **DaVinci Resolve:** Editor profesional gratuito
- **PowerPoint:** Exportar presentación como video MP4

---

## 📝 Notas Importantes

1. **Sin videos = Sin problema:** El kiosco funciona normalmente sin videos
2. **Codec H.264:** Usar este codec para máxima compatibilidad
3. **Tamaño:** Mantener videos pequeños (<50MB cada uno) para no inflar el ejecutable
4. **Loop:** Los videos deben estar diseñados para repetirse infinitamente
