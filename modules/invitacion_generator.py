"""
Generador de Invitaciones con QR
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import qrcode
import io
import os

class InvitacionGenerator:
    def __init__(self):
        self.width = 1080
        self.height = 1920
        
    def generar_invitacion(self, invitado, evento, config=None):
        """
        Generar invitación personalizada
        
        config = {
            'fondo_color': '#1a1a2e',
            'texto_color': '#ffffff',
            'acento_color': '#3b82f6',
            'qr_size': 400,
            'qr_position': (340, 1200),
            'logo_text': None,
            'mostrar_mesa': True
        }
        """
        if config is None:
            config = {}
        
        # Configuración por defecto
        fondo_color = config.get('fondo_color', '#1a1a2e')
        texto_color = config.get('texto_color', '#ffffff')
        acento_color = config.get('acento_color', '#3b82f6')
        qr_size = config.get('qr_size', 400)
        qr_pos = config.get('qr_position', (340, 1200))
        mostrar_mesa = config.get('mostrar_mesa', True)
        
        # Crear imagen base
        img = Image.new('RGB', (self.width, self.height), fondo_color)
        draw = ImageDraw.Draw(img)
        
        try:
            # Intentar cargar fuentes del sistema
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
            font_subtitle = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 50)
            font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 90)
            font_info = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        except:
            # Fallback a fuente por defecto
            font_title = ImageFont.load_default()
            font_subtitle = ImageFont.load_default()
            font_name = ImageFont.load_default()
            font_info = ImageFont.load_default()
        
        # Header decorativo
        draw.rectangle([(0, 0), (self.width, 300)], fill=acento_color)
        
        # Título del evento
        evento_nombre = evento.get('nombre', 'Evento')
        self._draw_centered_text(draw, evento_nombre, 150, font_title, texto_color)
        
        # Fecha
        fecha_texto = f"📅 {evento.get('fecha_evento', '')}"
        if evento.get('hora_inicio'):
            fecha_texto += f" • {evento.get('hora_inicio')}"
        self._draw_centered_text(draw, fecha_texto, 250, font_subtitle, texto_color)
        
        # Espacio
        y_offset = 450
        
        # "Invitación para"
        self._draw_centered_text(draw, "Invitación para", y_offset, font_subtitle, acento_color)
        y_offset += 100
        
        # Nombre del invitado
        nombre_completo = f"{invitado['nombre']} {invitado['apellido']}"
        self._draw_centered_text(draw, nombre_completo, y_offset, font_name, texto_color)
        y_offset += 150
        
        # Mesa (si aplica)
        if mostrar_mesa and invitado.get('mesa'):
            mesa_text = f"Mesa: {invitado['mesa']}"
            self._draw_centered_text(draw, mesa_text, y_offset, font_info, acento_color)
            y_offset += 80
        
        # Observaciones (si hay)
        if invitado.get('observaciones'):
            obs_text = invitado['observaciones'][:50]
            self._draw_centered_text(draw, obs_text, y_offset, font_info, texto_color)
        
        # Generar QR
        qr_img = self._generar_qr(invitado.get('qr_code', ''), qr_size)
        
        # Pegar QR en la invitación
        img.paste(qr_img, qr_pos)
        
        # Texto debajo del QR
        qr_label_y = qr_pos[1] + qr_size + 30
        self._draw_centered_text(draw, "Escanea para acreditar", qr_label_y, font_info, texto_color)
        
        # Footer
        footer_y = self.height - 100
        self._draw_centered_text(draw, "WelcomeX", footer_y, font_subtitle, acento_color)
        
        return img
    
    def generar_con_plantilla(self, invitado, evento, plantilla_path, config=None):
        """Generar invitación usando imagen de fondo"""
        try:
            # Cargar plantilla
            img = Image.open(plantilla_path)
            img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)
            
            # Crear capa semi-transparente para mejor legibilidad
            overlay = Image.new('RGBA', img.size, (0, 0, 0, 128))
            img = img.convert('RGBA')
            img = Image.alpha_composite(img, overlay)
            img = img.convert('RGB')
            
            draw = ImageDraw.Draw(img)
            
            if config is None:
                config = {}
            
            texto_color = config.get('texto_color', '#ffffff')
            qr_size = config.get('qr_size', 400)
            qr_pos = config.get('qr_position', (340, 1200))
            
            try:
                font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 90)
                font_info = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
            except:
                font_name = ImageFont.load_default()
                font_info = ImageFont.load_default()
            
            # Nombre centrado
            nombre_completo = f"{invitado['nombre']} {invitado['apellido']}"
            self._draw_centered_text(draw, nombre_completo, 800, font_name, texto_color)
            
            # Mesa
            if invitado.get('mesa'):
                mesa_text = f"Mesa: {invitado['mesa']}"
                self._draw_centered_text(draw, mesa_text, 920, font_info, texto_color)
            
            # QR
            qr_img = self._generar_qr(invitado.get('qr_code', ''), qr_size)
            img.paste(qr_img, qr_pos)
            
            return img
            
        except Exception as e:
            print(f"Error con plantilla: {e}")
            # Fallback a invitación básica
            return self.generar_invitacion(invitado, evento, config)
    
    def _generar_qr(self, data, size):
        """Generar código QR"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img = qr_img.resize((size, size), Image.Resampling.LANCZOS)
        
        return qr_img
    
    def _draw_centered_text(self, draw, text, y, font, color):
        """Dibujar texto centrado"""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        draw.text((x, y), text, fill=color, font=font)
    
    def generar_todas(self, invitados, evento, output_dir, config=None, plantilla_path=None):
        """Generar todas las invitaciones y guardarlas"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        archivos = []
        
        for inv in invitados:
            try:
                # Generar invitación
                if plantilla_path and os.path.exists(plantilla_path):
                    img = self.generar_con_plantilla(inv, evento, plantilla_path, config)
                else:
                    img = self.generar_invitacion(inv, evento, config)
                
                # Nombre del archivo
                filename = f"{inv['apellido']}_{inv['nombre']}_Mesa{inv.get('mesa', 'X')}.png"
                filename = filename.replace(' ', '_')
                filepath = os.path.join(output_dir, filename)
                
                # Guardar
                img.save(filepath, 'PNG', quality=95)
                archivos.append(filepath)
                
            except Exception as e:
                print(f"Error generando invitación para {inv['nombre']}: {e}")
        
        return archivos
