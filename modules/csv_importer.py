"""
CSV Importer - Importar invitados desde Excel
"""

import openpyxl
from modules.database import db

class CSVImporter:
    def __init__(self, evento_id):
        self.evento_id = evento_id

    def importar_archivo(self, filepath):
        """Importar desde Excel — bulk insert (1 transacción para todas las filas)"""
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
            idx_nombre   = headers.index('Nombre')
            idx_apellido = headers.index('Apellido')
            idx_mesa     = headers.index('Mesa')
            idx_obs      = headers.index('Observaciones') if 'Observaciones' in headers else None

            # Cargar invitados existentes para detectar duplicados
            try:
                db.connect()
                existentes = db.obtener_invitados_evento(self.evento_id)
                db.disconnect()
            except Exception:
                existentes = []
            nombres_existentes = {
                (i['nombre'].strip().lower(), i['apellido'].strip().lower())
                for i in existentes
            }

            total    = 0
            errores  = []
            saltados = []
            filas_validas = []  # (nombre, apellido, mesa, observaciones)

            # Validar filas — sin tocar la BD todavía
            for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                total += 1

                nombre   = row[idx_nombre]
                apellido = row[idx_apellido]
                mesa     = row[idx_mesa]
                obs      = row[idx_obs] if idx_obs is not None else None

                if not nombre or not apellido:
                    saltados.append(f"Fila {row_num}: Sin nombre/apellido")
                    continue

                # Detectar duplicados con invitados ya cargados
                clave = (str(nombre).strip().lower(), str(apellido).strip().lower())
                if clave in nombres_existentes:
                    saltados.append(f"Fila {row_num}: {apellido} {nombre} - Ya existe")
                    continue

                if not mesa:
                    errores.append(f"Fila {row_num}: {apellido} {nombre} - Falta mesa")
                    continue

                try:
                    mesa = int(mesa)
                except Exception:
                    errores.append(f"Fila {row_num}: {apellido} {nombre} - Mesa debe ser número")
                    continue

                filas_validas.append((
                    str(nombre).strip(),
                    str(apellido).strip(),
                    mesa,
                    str(obs).strip() if obs else None
                ))

            if not filas_validas:
                return {
                    "success": True,
                    "total": total,
                    "exitosos": 0,
                    "errores": errores,
                    "saltados": saltados
                }

            # Insertar todas las filas válidas en UNA sola transacción
            resultado = db.insertar_invitados_bulk(self.evento_id, filas_validas)

            if not resultado["success"]:
                return {"success": False, "error": resultado["error"]}

            return {
                "success": True,
                "total": total,
                "exitosos": resultado["insertados"],
                "errores": errores,
                "saltados": saltados
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
