"""
Sistema de Seguridad para Acreditaciones
Detecta patrones sospechosos y genera alertas
"""
from datetime import datetime, timedelta

class SistemaSeguridad:
    def __init__(self, db):
        self.db = db
        self.configuracion = {
            "tiempo_anti_doble": 15,  # segundos
            "tiempo_reingreso_minimo": 180,  # 3 minutos
            "max_intentos_rapidos": 3,
            "ventana_intentos": 600  # 10 minutos
        }
    
    def validar_acreditacion(self, invitado_id, evento_id, kiosco_id):
        """
        Valida si la acreditación es sospechosa
        Retorna: {"valido": bool, "alerta": dict o None}
        """
        self.db.connect()
        
        try:
            # Obtener historial reciente
            self.db.cursor.execute("""
                SELECT tipo, timestamp, kiosco_id
                FROM acreditaciones
                WHERE invitado_id = ? AND evento_id = ?
                ORDER BY timestamp DESC
                LIMIT 10
            """, (invitado_id, evento_id))
            
            historial = [dict(row) for row in self.db.cursor.fetchall()]
            
            if not historial:
                # Primera acreditación, todo OK
                return {"valido": True, "alerta": None}
            
            ultima = historial[0]
            ultima_dt = datetime.fromisoformat(ultima['timestamp'])
            ahora = datetime.now()
            segundos_desde_ultima = (ahora - ultima_dt).total_seconds()
            
            # Verificar doble escaneo rápido
            if segundos_desde_ultima < self.configuracion["tiempo_anti_doble"]:
                return {
                    "valido": True,  # Permitir pero alertar
                    "alerta": {
                        "tipo": "doble_escaneo",
                        "nivel": "MEDIO",
                        "razon": f"Doble escaneo ({int(segundos_desde_ultima)}s)",
                        "detalles": {
                            "segundos": int(segundos_desde_ultima),
                            "timestamp_anterior": ultima['timestamp']
                        }
                    }
                }
            
            # Verificar reingreso rápido (ya estaba dentro)
            if ultima['tipo'] == 'ingreso' and segundos_desde_ultima < self.configuracion["tiempo_reingreso_minimo"]:
                return {
                    "valido": True,
                    "alerta": {
                        "tipo": "reingreso_rapido",
                        "nivel": "MEDIO",
                        "razon": f"Ya estaba dentro (hace {int(segundos_desde_ultima/60)} min)",
                        "detalles": {
                            "minutos": int(segundos_desde_ultima/60),
                            "timestamp_ingreso": ultima['timestamp']
                        }
                    }
                }
            
            # Verificar múltiples kioscos
            if kiosco_id != ultima.get('kiosco_id') and segundos_desde_ultima < 300:  # 5 min
                return {
                    "valido": True,
                    "alerta": {
                        "tipo": "multiples_kioscos",
                        "nivel": "CRITICO",
                        "razon": f"QR en 2 kioscos diferentes ({int(segundos_desde_ultima)}s)",
                        "detalles": {
                            "kiosco_anterior": ultima.get('kiosco_id'),
                            "kiosco_actual": kiosco_id,
                            "segundos": int(segundos_desde_ultima)
                        }
                    }
                }
            
            # Verificar múltiples intentos rápidos
            ventana_inicio = ahora - timedelta(seconds=self.configuracion["ventana_intentos"])
            intentos_recientes = [
                h for h in historial 
                if datetime.fromisoformat(h['timestamp']) > ventana_inicio
            ]
            
            if len(intentos_recientes) >= self.configuracion["max_intentos_rapidos"]:
                return {
                    "valido": True,
                    "alerta": {
                        "tipo": "multiples_intentos",
                        "nivel": "ALTO",
                        "razon": f"{len(intentos_recientes)} escaneos en {int(self.configuracion['ventana_intentos']/60)} min",
                        "detalles": {
                            "cantidad": len(intentos_recientes),
                            "ventana_minutos": int(self.configuracion["ventana_intentos"]/60)
                        }
                    }
                }
            
            # Todo normal
            return {"valido": True, "alerta": None}
            
        except Exception as e:
            print(f"Error validación seguridad: {e}")
            return {"valido": True, "alerta": None}
        
        finally:
            self.db.disconnect()
    
    def registrar_alerta(self, invitado_id, evento_id, kiosco_id, alerta):
        """Registra una alerta de seguridad en la BD"""
        self.db.connect()
        
        try:
            self.db.cursor.execute("""
                INSERT INTO alertas_seguridad 
                (invitado_id, evento_id, kiosco_id, tipo, nivel, razon, timestamp, detalles)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                invitado_id,
                evento_id,
                kiosco_id,
                alerta['tipo'],
                alerta['nivel'],
                alerta['razon'],
                datetime.now().isoformat(),
                str(alerta.get('detalles', {}))
            ))
            
            self.db.connection.commit()
            return True
            
        except Exception as e:
            print(f"Error registrando alerta: {e}")
            return False
        
        finally:
            self.db.disconnect()
    
    def obtener_alertas(self, evento_id, solo_sin_resolver=False):
        """Obtiene alertas del evento"""
        self.db.connect()
        
        try:
            query = """
                SELECT a.*, i.nombre, i.apellido, i.mesa
                FROM alertas_seguridad a
                JOIN invitados i ON a.invitado_id = i.id
                WHERE a.evento_id = ?
            """
            
            if solo_sin_resolver:
                query += " AND a.resuelta = 0"
            
            query += " ORDER BY a.timestamp DESC"
            
            self.db.cursor.execute(query, (evento_id,))
            alertas = [dict(row) for row in self.db.cursor.fetchall()]
            
            return alertas
            
        except Exception as e:
            print(f"Error obteniendo alertas: {e}")
            return []
        
        finally:
            self.db.disconnect()
    
    def marcar_resuelta(self, alerta_id):
        """Marca una alerta como resuelta"""
        self.db.connect()
        
        try:
            self.db.cursor.execute("""
                UPDATE alertas_seguridad
                SET resuelta = 1
                WHERE id = ?
            """, (alerta_id,))
            
            self.db.connection.commit()
            return True
            
        except Exception as e:
            print(f"Error marcando alerta: {e}")
            return False
        
        finally:
            self.db.disconnect()
