"""
Gestor de Sincronización entre Kioscos
"""
import time
import os
import json
from pathlib import Path
from config.settings import DATA_DIR

SYNC_DIR = Path(DATA_DIR) / "sync"
SYNC_FILE = SYNC_DIR / "kiosco_sync.json"

class SyncManager:
    """Administra sincronización entre kioscos"""
    
    def __init__(self):
        SYNC_DIR.mkdir(parents=True, exist_ok=True)
        if not SYNC_FILE.exists():
            self._write_sync({
                'video_loops': {},
                'acreditaciones': []
            })
    
    def _read_sync(self):
        """Leer archivo de sincronización"""
        try:
            with open(SYNC_FILE, 'r') as f:
                return json.load(f)
        except:
            return {'video_loops': {}, 'acreditaciones': []}
    
    def _write_sync(self, data):
        """Escribir archivo de sincronización"""
        try:
            with open(SYNC_FILE, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error escribiendo sync: {e}")
    
    def registrar_loop_frame(self, kiosco_id, frame_num, timestamp):
        """Registrar frame actual del loop"""
        data = self._read_sync()
        data['video_loops'][str(kiosco_id)] = {
            'frame': frame_num,
            'timestamp': timestamp
        }
        self._write_sync(data)
    
    def obtener_frame_objetivo(self, kiosco_id, total_frames):
        """Obtener frame objetivo para sincronizar"""
        data = self._read_sync()
        loops = data.get('video_loops', {})
        
        # Si hay otros kioscos activos, sincronizar con ellos
        otros_kioscos = {k: v for k, v in loops.items() if k != str(kiosco_id)}
        
        if otros_kioscos:
            # Usar el frame del primer kiosco activo
            otro = list(otros_kioscos.values())[0]
            return otro['frame'] % total_frames
        
        return None
    
    def registrar_acreditacion(self, kiosco_id, invitado_id, timestamp):
        """Registrar acreditación para notificar a otros kioscos"""
        data = self._read_sync()
        data['acreditaciones'].append({
            'kiosco_id': kiosco_id,
            'invitado_id': invitado_id,
            'timestamp': timestamp
        })
        
        # Mantener solo las últimas 100
        data['acreditaciones'] = data['acreditaciones'][-100:]
        self._write_sync(data)
    
    def limpiar_kiosco(self, kiosco_id):
        """Limpiar data de kiosco al cerrar"""
        data = self._read_sync()
        if str(kiosco_id) in data['video_loops']:
            del data['video_loops'][str(kiosco_id)]
        self._write_sync(data)
