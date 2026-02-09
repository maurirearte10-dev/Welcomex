"""
WelcomeX - Database Manager
SQLite con todas las tablas necesarias
"""

import sqlite3
import os
import hashlib
import uuid
from datetime import datetime, timedelta
from config.settings import DATABASE_PATH

class DatabaseManager:
    def __init__(self):
        self.db_path = DATABASE_PATH
        self.connection = None
        self.cursor = None

        # DEBUG: Mostrar ruta de la base de datos
        print(f"[DB] Inicializando base de datos en: {self.db_path}")
        print(f"[DB] Directorio de datos: {os.path.dirname(self.db_path)}")

        self.init_database()
    
    def connect(self):
        """Conectar a la base de datos"""
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        return self.connection
    
    def disconnect(self):
        """Cerrar conexión"""
        if self.connection:
            self.connection.close()
            self.connection = None
            self.cursor = None
    
    def init_database(self):
        """Crear todas las tablas"""
        self.connect()
        
        # Tabla usuarios
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                nombre TEXT NOT NULL,
                apellido TEXT,
                telefono TEXT,
                rol TEXT NOT NULL DEFAULT 'admin',
                admin_id INTEGER,
                fecha_registro TEXT NOT NULL,
                ultimo_acceso TEXT,
                activo INTEGER DEFAULT 1,
                FOREIGN KEY (admin_id) REFERENCES usuarios(id)
            )
        ''')
        
        # Tabla licencias
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS licencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                plan TEXT NOT NULL,
                fecha_inicio TEXT NOT NULL,
                fecha_vencimiento TEXT NOT NULL,
                fecha_ultima_validacion TEXT,
                estado TEXT DEFAULT 'activa',
                precio_mensual REAL,
                precio_anual REAL,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
        ''')
        
        # Tabla eventos
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                nombre TEXT NOT NULL,
                fecha_evento TEXT NOT NULL,
                hora_inicio TEXT,
                hora_limite_acreditacion TEXT,
                video_loop TEXT,
                mesas_videos TEXT,
                mostrar_mesa INTEGER DEFAULT 1,
                estado TEXT DEFAULT 'creado',
                fecha_creacion TEXT NOT NULL,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
        ''')
        
        # Tabla invitados
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS invitados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evento_id INTEGER NOT NULL,
                qr_code TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                apellido TEXT NOT NULL,
                email TEXT,
                telefono TEXT,
                mesa INTEGER,
                acompanantes INTEGER DEFAULT 0,
                observaciones TEXT,
                video_personalizado TEXT,
                presente INTEGER DEFAULT 0,
                kiosco_acreditador INTEGER,
                fecha_registro TEXT NOT NULL,
                FOREIGN KEY (evento_id) REFERENCES eventos(id)
            )
        ''')
        
        # Tabla acreditaciones (para registrar ingresos/egresos)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS acreditaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invitado_id INTEGER NOT NULL,
                evento_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                kiosco_id INTEGER,
                FOREIGN KEY (invitado_id) REFERENCES invitados(id),
                FOREIGN KEY (evento_id) REFERENCES eventos(id)
            )
        ''')
        
        # Tabla sorteos
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sorteos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evento_id INTEGER NOT NULL,
                invitado_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                mesa INTEGER,
                fecha_sorteo TEXT NOT NULL,
                FOREIGN KEY (evento_id) REFERENCES eventos(id),
                FOREIGN KEY (invitado_id) REFERENCES invitados(id)
            )
        ''')
        
        # Tabla alertas de seguridad
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS alertas_seguridad (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invitado_id INTEGER NOT NULL,
                evento_id INTEGER NOT NULL,
                kiosco_id INTEGER,
                tipo TEXT NOT NULL,
                nivel TEXT NOT NULL,
                razon TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                detalles TEXT,
                resuelta INTEGER DEFAULT 0,
                FOREIGN KEY (invitado_id) REFERENCES invitados(id),
                FOREIGN KEY (evento_id) REFERENCES eventos(id)
            )
        ''')
        
        # Tabla sesiones_activas
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sesiones_activas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                sesion_id TEXT UNIQUE NOT NULL,
                dispositivo TEXT,
                navegador TEXT,
                ip TEXT,
                tipo_sesion TEXT DEFAULT 'admin',
                ultima_actividad TEXT NOT NULL,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
        ''')
        
        # Tabla videos_mesa (para videos por mesa)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS videos_mesa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evento_id INTEGER NOT NULL,
                mesa INTEGER NOT NULL,
                video_path TEXT NOT NULL,
                FOREIGN KEY (evento_id) REFERENCES eventos(id),
                UNIQUE(evento_id, mesa)
            )
        ''')

        # Tabla configuracion (para guardar license key, etc.)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )
        ''')

        self.connection.commit()
        
        # MIGRACIONES: Agregar columnas faltantes si no existen
        try:
            # Verificar si existe columna kiosco_acreditador en invitados
            self.cursor.execute("PRAGMA table_info(invitados)")
            columnas_invitados = [col[1] for col in self.cursor.fetchall()]
            
            if 'kiosco_acreditador' not in columnas_invitados:
                print("[MIGRACIÓN] Agregando columna kiosco_acreditador...")
                self.cursor.execute("ALTER TABLE invitados ADD COLUMN kiosco_acreditador INTEGER")
                self.connection.commit()
                print("[MIGRACIÓN] ✅ Columna agregada")
            
            # Verificar si existe columna mostrar_mesa en eventos
            self.cursor.execute("PRAGMA table_info(eventos)")
            columnas_eventos = [col[1] for col in self.cursor.fetchall()]
            
            if 'mostrar_mesa' not in columnas_eventos:
                print("[MIGRACIÓN] Agregando columna mostrar_mesa...")
                self.cursor.execute("ALTER TABLE eventos ADD COLUMN mostrar_mesa INTEGER DEFAULT 1")
                self.connection.commit()
                print("[MIGRACIÓN] ✅ Columna mostrar_mesa agregada")
        except Exception as e:
            print(f"[MIGRACIÓN] Error: {e}")
        
        # Crear super admin por defecto si no existe
        self.cursor.execute("SELECT COUNT(*) as count FROM usuarios")
        count = self.cursor.fetchone()['count']
        
        if count == 0:
            # Crear super admin automáticamente
            password_hash = hashlib.sha256("Malvinas!09".encode()).hexdigest()
            user_uuid = str(uuid.uuid4())
            
            self.cursor.execute("""
                INSERT INTO usuarios (uuid, email, password, nombre, apellido, rol, activo, fecha_registro)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """, (
                user_uuid,
                "mrearte21@hotmail.com",
                password_hash,
                "Admin",
                "Sistema",
                "super_admin",
                datetime.now().isoformat()
            ))
            
            self.connection.commit()
            print("✅ Super Admin creado automáticamente")
            print("   Email: mrearte21@hotmail.com")
            print("   Password: Malvinas!09")
        
        self.disconnect()
    
    # ============================================
    # USUARIOS
    # ============================================
    
    def autenticar_usuario(self, email, password):
        """Autenticar usuario"""
        self.connect()
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            self.cursor.execute("""
                SELECT u.*, l.plan, l.estado as licencia_estado, l.fecha_vencimiento
                FROM usuarios u
                LEFT JOIN licencias l ON u.id = l.usuario_id
                WHERE u.email = ? AND u.password = ? AND u.activo = 1
            """, (email, password_hash))
            
            usuario = self.cursor.fetchone()
            
            if usuario:
                # Actualizar último acceso
                self.cursor.execute(
                    "UPDATE usuarios SET ultimo_acceso = ? WHERE id = ?",
                    (datetime.now().isoformat(), usuario['id'])
                )
                self.connection.commit()
                
                return {"success": True, "usuario": dict(usuario)}
            else:
                return {"success": False, "error": "Email o contraseña incorrectos"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()
    
    def crear_usuario(self, email, password, nombre, apellido, rol, admin_id=None):
        """Crear nuevo usuario"""
        self.connect()
        try:
            # Verificar email único
            self.cursor.execute("SELECT id FROM usuarios WHERE email = ?", (email,))
            if self.cursor.fetchone():
                return {"success": False, "error": "El email ya existe"}
            
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            user_uuid = str(uuid.uuid4())
            
            self.cursor.execute("""
                INSERT INTO usuarios (uuid, email, password, nombre, apellido, rol, admin_id, fecha_registro, activo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (user_uuid, email, password_hash, nombre, apellido, rol, admin_id, datetime.now().isoformat()))
            
            self.connection.commit()
            user_id = self.cursor.lastrowid
            
            return {"success": True, "id": user_id, "uuid": user_uuid}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()
    
    def obtener_operarios(self, admin_id):
        """Obtener operarios de un admin"""
        self.connect()
        try:
            self.cursor.execute("""
                SELECT * FROM usuarios 
                WHERE admin_id = ? AND rol = 'operario' AND activo = 1
                ORDER BY nombre
            """, (admin_id,))
            
            return [dict(row) for row in self.cursor.fetchall()]
        except:
            return []
        finally:
            self.disconnect()
    
    def obtener_todos_usuarios(self):
        """Obtener todos los usuarios"""
        self.connect()
        try:
            self.cursor.execute("""
                SELECT * FROM usuarios
                ORDER BY fecha_registro DESC
            """)
            return [dict(row) for row in self.cursor.fetchall()]
        finally:
            self.disconnect()
    
    def desactivar_usuario(self, usuario_id):
        """Desactivar usuario"""
        self.connect()
        try:
            self.cursor.execute("""
                UPDATE usuarios
                SET activo = 0
                WHERE id = ?
            """, (usuario_id,))
            self.connection.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()
    
    def activar_usuario(self, usuario_id):
        """Activar usuario"""
        self.connect()
        try:
            self.cursor.execute("""
                UPDATE usuarios
                SET activo = 1
                WHERE id = ?
            """, (usuario_id,))
            self.connection.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()
    
    def cambiar_password_usuario(self, usuario_id, nueva_password):
        """Cambiar contraseña de usuario"""
        self.connect()
        try:
            password_hash = hashlib.sha256(nueva_password.encode()).hexdigest()
            self.cursor.execute("""
                UPDATE usuarios
                SET password = ?
                WHERE id = ?
            """, (password_hash, usuario_id))
            self.connection.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()
    
    # ============================================
    # LICENCIAS
    # ============================================
    
    def crear_licencia(self, usuario_id, plan, duracion_dias, precio_mensual=None, precio_anual=None):
        """Crear licencia"""
        self.connect()
        try:
            fecha_inicio = datetime.now()
            fecha_venc = fecha_inicio + timedelta(days=duracion_dias)
            
            self.cursor.execute("""
                INSERT INTO licencias (usuario_id, plan, fecha_inicio, fecha_vencimiento, 
                                      fecha_ultima_validacion, estado, precio_mensual, precio_anual)
                VALUES (?, ?, ?, ?, ?, 'activa', ?, ?)
            """, (usuario_id, plan, fecha_inicio.isoformat(), fecha_venc.isoformat(), 
                  fecha_inicio.isoformat(), precio_mensual, precio_anual))
            
            self.connection.commit()
            return {"success": True, "id": self.cursor.lastrowid}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()
    
    def obtener_licencias(self):
        """Obtener todas las licencias"""
        self.connect()
        try:
            self.cursor.execute("""
                SELECT l.*, u.nombre, u.apellido, u.email
                FROM licencias l
                JOIN usuarios u ON l.usuario_id = u.id
                ORDER BY l.fecha_inicio DESC
            """)
            return [dict(row) for row in self.cursor.fetchall()]
        except:
            return []
        finally:
            self.disconnect()
    
    # ============================================
    # EVENTOS
    # ============================================
    
    def crear_evento(self, usuario_id, nombre, fecha_evento, hora_inicio=None, 
                     hora_limite=None, video_loop=None):
        """Crear evento"""
        self.connect()
        try:
            self.cursor.execute("""
                INSERT INTO eventos (usuario_id, nombre, fecha_evento, hora_inicio, 
                                    hora_limite_acreditacion, video_loop, estado, fecha_creacion)
                VALUES (?, ?, ?, ?, ?, ?, 'creado', ?)
            """, (usuario_id, nombre, fecha_evento, hora_inicio, hora_limite, 
                  video_loop, datetime.now().isoformat()))
            
            self.connection.commit()
            return {"success": True, "id": self.cursor.lastrowid}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()
    
    def obtener_eventos_usuario(self, usuario_id):
        """Obtener eventos de un usuario"""
        self.connect()
        try:
            self.cursor.execute("""
                SELECT * FROM eventos 
                WHERE usuario_id = ? 
                ORDER BY fecha_evento DESC
            """, (usuario_id,))
            
            return [dict(row) for row in self.cursor.fetchall()]
        except:
            return []
        finally:
            self.disconnect()
    
    def cambiar_estado_evento(self, evento_id, nuevo_estado, usuario_id=None, motivo=None):
        """Cambiar estado de evento"""
        self.connect()
        try:
            self.cursor.execute(
                "UPDATE eventos SET estado = ? WHERE id = ?",
                (nuevo_estado, evento_id)
            )
            self.connection.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()
    
    def verificar_invitados_sin_mesa(self, evento_id):
        """Verificar si hay invitados sin mesa asignada"""
        self.connect()
        try:
            self.cursor.execute("""
                SELECT nombre, apellido FROM invitados 
                WHERE evento_id = ? AND (mesa IS NULL OR mesa = '')
            """, (evento_id,))
            
            sin_mesa = [dict(row) for row in self.cursor.fetchall()]
            return sin_mesa
        except:
            return []
        finally:
            self.disconnect()
    
    def eliminar_evento(self, evento_id):
        """Eliminar evento y sus dependencias"""
        self.connect()
        try:
            # Eliminar acreditaciones
            self.cursor.execute("DELETE FROM acreditaciones WHERE evento_id = ?", (evento_id,))
            # Eliminar sorteos
            self.cursor.execute("DELETE FROM sorteos WHERE evento_id = ?", (evento_id,))
            # Eliminar invitados
            self.cursor.execute("DELETE FROM invitados WHERE evento_id = ?", (evento_id,))
            # Eliminar videos mesa
            self.cursor.execute("DELETE FROM videos_mesa WHERE evento_id = ?", (evento_id,))
            # Eliminar evento
            self.cursor.execute("DELETE FROM eventos WHERE id = ?", (evento_id,))
            
            self.connection.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()
    
    def guardar_videos_mesa(self, evento_id, videos_mesa):
        """Guardar videos por mesa
        videos_mesa: dict {mesa: video_path}
        """
        self.connect()
        try:
            # Eliminar videos existentes del evento
            self.cursor.execute("DELETE FROM videos_mesa WHERE evento_id = ?", (evento_id,))
            
            # Insertar nuevos videos
            for mesa, video_path in videos_mesa.items():
                if video_path:  # Solo si hay video
                    self.cursor.execute("""
                        INSERT INTO videos_mesa (evento_id, mesa, video_path)
                        VALUES (?, ?, ?)
                    """, (evento_id, int(mesa), video_path))
            
            self.connection.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()
    
    def obtener_videos_mesa(self, evento_id):
        """Obtener todos los videos configurados para un evento
        Returns: dict {mesa: video_path}
        """
        self.connect()
        try:
            self.cursor.execute("""
                SELECT mesa, video_path
                FROM videos_mesa
                WHERE evento_id = ?
                ORDER BY mesa
            """, (evento_id,))
            
            videos = {}
            for row in self.cursor.fetchall():
                videos[row['mesa']] = row['video_path']
            
            return videos
        except Exception as e:
            return {}
        finally:
            self.disconnect()
    
    def obtener_video_por_mesa(self, evento_id, mesa):
        """Obtener video específico de una mesa"""
        self.connect()
        try:
            self.cursor.execute("""
                SELECT video_path
                FROM videos_mesa
                WHERE evento_id = ? AND mesa = ?
            """, (evento_id, mesa))
            
            row = self.cursor.fetchone()
            return row['video_path'] if row else None
        except Exception as e:
            return None
        finally:
            self.disconnect()
    
    # ============================================
    # INVITADOS
    # ============================================
    
    def agregar_invitado(self, evento_id, nombre, apellido, mesa=None, 
                        observaciones=None, video_personalizado=None, 
                        email=None, telefono=None, acompanantes=0):
        """Agregar invitado"""
        self.connect()
        try:
            # Generar QR único
            qr_code = f"EVT{evento_id}-{uuid.uuid4().hex[:8].upper()}"
            
            self.cursor.execute("""
                INSERT INTO invitados (evento_id, qr_code, nombre, apellido, mesa, 
                                      observaciones, video_personalizado, email, telefono, 
                                      acompanantes, presente, fecha_registro)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """, (evento_id, qr_code, nombre, apellido, mesa, observaciones, 
                  video_personalizado, email, telefono, acompanantes, datetime.now().isoformat()))
            
            self.connection.commit()
            return {"success": True, "id": self.cursor.lastrowid, "qr_code": qr_code}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()
    
    def obtener_invitados_evento(self, evento_id):
        """Obtener todos los invitados de un evento"""
        self.connect()
        try:
            self.cursor.execute("""
                SELECT * FROM invitados 
                WHERE evento_id = ? 
                ORDER BY apellido, nombre
            """, (evento_id,))
            
            return [dict(row) for row in self.cursor.fetchall()]
        except:
            return []
        finally:
            self.disconnect()
    
    def obtener_invitados_presentes(self, evento_id):
        """Obtener invitados acreditados"""
        self.connect()
        try:
            self.cursor.execute("""
                SELECT * FROM invitados 
                WHERE evento_id = ? AND presente = 1
                ORDER BY apellido, nombre
            """, (evento_id,))
            
            return [dict(row) for row in self.cursor.fetchall()]
        except:
            return []
        finally:
            self.disconnect()
    
    def obtener_invitado_por_qr(self, qr_code):
        """Obtener invitado por código QR"""
        self.connect()
        try:
            print(f"[DB] Buscando invitado con QR: '{qr_code}'")
            
            self.cursor.execute("""
                SELECT * FROM invitados 
                WHERE qr_code = ?
            """, (qr_code,))
            
            invitado = self.cursor.fetchone()
            
            if invitado:
                print(f"[DB] ✅ Encontrado: {dict(invitado)['nombre']} {dict(invitado)['apellido']}")
                return dict(invitado)
            else:
                print(f"[DB] ❌ No encontrado")
                return None
                
        except Exception as e:
            print(f"[DB ERROR] obtener_invitado_por_qr: {e}")
            return None
        finally:
            self.disconnect()
    
    def acreditar_invitado(self, invitado_id, evento_id, kiosco_id=None):
        """Acreditar invitado en un kiosco específico - REGISTRA EN ACREDITACIONES"""
        self.connect()
        try:
            # Verificar última acreditación para determinar tipo
            self.cursor.execute("""
                SELECT tipo FROM acreditaciones 
                WHERE invitado_id = ? AND evento_id = ?
                ORDER BY timestamp DESC LIMIT 1
            """, (invitado_id, evento_id))
            
            ultima = self.cursor.fetchone()
            
            # Determinar tipo (ingreso o egreso)
            if not ultima or ultima['tipo'] == 'egreso':
                tipo = 'ingreso'
                presente = 1
            else:
                tipo = 'egreso'
                presente = 0
            
            # Registrar acreditación CON kiosco_id
            self.cursor.execute("""
                INSERT INTO acreditaciones (invitado_id, evento_id, tipo, timestamp, kiosco_id)
                VALUES (?, ?, ?, ?, ?)
            """, (invitado_id, evento_id, tipo, datetime.now().isoformat(), kiosco_id))
            
            # Actualizar estado presente y kiosco acreditador
            self.cursor.execute("""
                UPDATE invitados 
                SET presente = ?, kiosco_acreditador = ?
                WHERE id = ? AND evento_id = ?
            """, (presente, kiosco_id, invitado_id, evento_id))
            
            self.connection.commit()
            
            print(f"[DB] Acreditación registrada: invitado_id={invitado_id}, tipo={tipo}, kiosco={kiosco_id}")
            
            return True
        except Exception as e:
            print(f"[DB ERROR] Error acreditando: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            self.disconnect()
    
    def obtener_acreditaciones_evento(self, evento_id):
        """Obtener todas las acreditaciones con info del invitado"""
        self.connect()
        try:
            self.cursor.execute("""
                SELECT a.*, i.nombre, i.apellido, i.mesa
                FROM acreditaciones a
                JOIN invitados i ON a.invitado_id = i.id
                WHERE a.evento_id = ?
                ORDER BY a.timestamp ASC
            """, (evento_id,))
            
            return [dict(row) for row in self.cursor.fetchall()]
        except Exception as e:
            print(f"Error obteniendo acreditaciones: {e}")
            return []
        finally:
            self.disconnect()
    
    def acreditar_invitado_legacy(self, qr_code, evento_id):
        """Acreditar invitado - registra ingreso/egreso (VERSIÓN LEGACY)"""
        self.connect()
        try:
            # Buscar invitado
            self.cursor.execute("""
                SELECT * FROM invitados 
                WHERE qr_code = ? AND evento_id = ?
            """, (qr_code, evento_id))
            
            invitado = self.cursor.fetchone()
            
            if not invitado:
                return {"success": False, "error": "QR no válido para este evento"}
            
            invitado = dict(invitado)
            
            # Verificar última acreditación
            self.cursor.execute("""
                SELECT tipo FROM acreditaciones 
                WHERE invitado_id = ? AND evento_id = ?
                ORDER BY timestamp DESC LIMIT 1
            """, (invitado['id'], evento_id))
            
            ultima = self.cursor.fetchone()
            
            # Determinar tipo (ingreso o egreso)
            if not ultima or ultima['tipo'] == 'egreso':
                tipo = 'ingreso'
                presente = 1
            else:
                tipo = 'egreso'
                presente = 0
            
            # Registrar acreditación
            self.cursor.execute("""
                INSERT INTO acreditaciones (invitado_id, evento_id, tipo, timestamp)
                VALUES (?, ?, ?, ?)
            """, (invitado['id'], evento_id, tipo, datetime.now().isoformat()))
            
            # Actualizar estado presente
            self.cursor.execute("""
                UPDATE invitados SET presente = ? WHERE id = ?
            """, (presente, invitado['id']))
            
            self.connection.commit()
            
            return {
                "success": True, 
                "tipo": tipo,
                "invitado": invitado
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()
    
    # ============================================
    # SORTEOS
    # ============================================
    
    def registrar_ganador(self, evento_id, invitado_id, tipo, mesa=None):
        """Registrar ganador de sorteo"""
        self.connect()
        try:
            self.cursor.execute("""
                INSERT INTO sorteos (evento_id, invitado_id, tipo, mesa, fecha_sorteo)
                VALUES (?, ?, ?, ?, ?)
            """, (evento_id, invitado_id, tipo, mesa, datetime.now().isoformat()))
            
            self.connection.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()
    
    def obtener_ganadores(self, evento_id):
        """Obtener ganadores de sorteos"""
        self.connect()
        try:
            self.cursor.execute("""
                SELECT s.*, i.nombre, i.apellido, i.mesa
                FROM sorteos s
                JOIN invitados i ON s.invitado_id = i.id
                WHERE s.evento_id = ?
                ORDER BY s.fecha_sorteo DESC
            """, (evento_id,))
            
            return [dict(row) for row in self.cursor.fetchall()]
        except:
            return []
        finally:
            self.disconnect()
    
    # ============================================
    # VIDEOS MESA
    # ============================================
    
    def guardar_video_mesa(self, evento_id, mesa, video_path):
        """Guardar video para una mesa"""
        self.connect()
        try:
            self.cursor.execute("""
                INSERT OR REPLACE INTO videos_mesa (evento_id, mesa, video_path)
                VALUES (?, ?, ?)
            """, (evento_id, mesa, video_path))
            
            self.connection.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.disconnect()
    
    def obtener_video_mesa(self, evento_id, mesa):
        """Obtener video de una mesa"""
        self.connect()
        try:
            self.cursor.execute("""
                SELECT video_path FROM videos_mesa 
                WHERE evento_id = ? AND mesa = ?
            """, (evento_id, mesa))
            
            row = self.cursor.fetchone()
            return row['video_path'] if row else None
        except:
            return None
        finally:
            self.disconnect()

    # ============================================
    # CONFIGURACION (clave-valor)
    # ============================================

    def get_config(self, clave, default=None):
        """Obtener valor de configuración"""
        self.connect()
        try:
            self.cursor.execute(
                "SELECT valor FROM configuracion WHERE clave = ?",
                (clave,)
            )
            row = self.cursor.fetchone()
            return row['valor'] if row else default
        except:
            return default
        finally:
            self.disconnect()

    def set_config(self, clave, valor):
        """Guardar valor de configuración"""
        self.connect()
        try:
            self.cursor.execute("""
                INSERT OR REPLACE INTO configuracion (clave, valor)
                VALUES (?, ?)
            """, (clave, str(valor)))
            self.connection.commit()
            return True
        except Exception as e:
            print(f"[DB] Error guardando config: {e}")
            return False
        finally:
            self.disconnect()

    def demo_invitaciones_usadas(self, machine_id):
        """Verificar si esta máquina ya agotó las generaciones de QR en demo"""
        clave = f"demo_inv_{machine_id}"
        count = self.get_config(clave, "0")
        try:
            return int(count) >= 3
        except:
            return False

    def demo_invitaciones_restantes(self, machine_id):
        """Obtener cuántas generaciones de QR le quedan en demo"""
        clave = f"demo_inv_{machine_id}"
        count = self.get_config(clave, "0")
        try:
            return max(0, 3 - int(count))
        except:
            return 3

    def incrementar_demo_invitaciones(self, machine_id):
        """Incrementar el contador de generaciones de QR en demo"""
        clave = f"demo_inv_{machine_id}"
        count = self.get_config(clave, "0")
        try:
            nuevo = int(count) + 1
        except:
            nuevo = 1
        return self.set_config(clave, str(nuevo))

    def registrar_demo_activada(self, machine_id):
        """Registrar que esta máquina activó el modo demo (con fecha)"""
        clave = f"demo_started_{machine_id}"
        existing = self.get_config(clave)
        if not existing:
            from datetime import datetime
            self.set_config(clave, datetime.now().isoformat())
            return True
        return False

    def demo_expirada(self, machine_id):
        """Verificar si la demo de esta máquina ya expiró (7 días)"""
        clave = f"demo_started_{machine_id}"
        fecha_str = self.get_config(clave)
        if not fecha_str:
            return False
        try:
            from datetime import datetime, timedelta
            fecha_inicio = datetime.fromisoformat(fecha_str)
            return datetime.now() > fecha_inicio + timedelta(days=7)
        except:
            return False

    def demo_dias_restantes(self, machine_id):
        """Obtener días restantes de demo para esta máquina"""
        clave = f"demo_started_{machine_id}"
        fecha_str = self.get_config(clave)
        if not fecha_str:
            return 7
        try:
            from datetime import datetime, timedelta
            fecha_inicio = datetime.fromisoformat(fecha_str)
            restantes = (fecha_inicio + timedelta(days=7) - datetime.now()).days
            return max(0, restantes)
        except:
            return 0

# Instancia global
db = DatabaseManager()
