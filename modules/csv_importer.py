"""
CSV Importer - Importar invitados desde Excel
"""

import openpyxl
from modules.database import db

class CSVImporter:
    def __init__(self, evento_id):
        self.evento_id = evento_id
    
    def importar_archivo(self, filepath):
        """Importar desde Excel"""
        try:
            wb = openpyxl.load_workbook(filepath)
            sheet = wb.active
            
            # Verificar columnas
            headers = [cell.value for cell in sheet[1]]
            
            required = ['Nombre', 'Apellido', 'Mesa']
            missing = [h for h in required if h not in headers]
            
            if missing:
                return {"success": False, "error": f"Faltan columnas: {', '.join(missing)}"}
            
            # Mapear índices
            idx_nombre = headers.index('Nombre')
            idx_apellido = headers.index('Apellido')
            idx_mesa = headers.index('Mesa')
            idx_obs = headers.index('Observaciones') if 'Observaciones' in headers else None
            
            total = 0
            exitosos = 0
            errores = []
            saltados = []
            
            # Procesar filas (desde la 2)
            for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                total += 1
                
                nombre = row[idx_nombre]
                apellido = row[idx_apellido]
                mesa = row[idx_mesa]
                obs = row[idx_obs] if idx_obs is not None else None
                
                # Validar nombre y apellido
                if not nombre or not apellido:
                    saltados.append(f"Fila {row_num}: Sin nombre/apellido")
                    continue
                
                # Validar mesa
                if not mesa:
                    errores.append(f"Fila {row_num}: {apellido} {nombre} - Falta mesa")
                    continue
                
                try:
                    mesa = int(mesa)
                except:
                    errores.append(f"Fila {row_num}: {apellido} {nombre} - Mesa debe ser número")
                    continue
                
                # Agregar invitado
                resultado = db.agregar_invitado(
                    evento_id=self.evento_id,
                    nombre=str(nombre).strip(),
                    apellido=str(apellido).strip(),
                    mesa=mesa,
                    observaciones=str(obs).strip() if obs else None
                )
                
                if resultado["success"]:
                    exitosos += 1
                else:
                    errores.append(f"Fila {row_num}: {resultado['error']}")
            
            return {
                "success": True,
                "total": total,
                "exitosos": exitosos,
                "errores": errores,
                "saltados": saltados
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
