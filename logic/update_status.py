"""
logic/update_status.py
Upsert de estado de migración en la tabla ESTADO_VMS.
"""

import sqlite3
from ui.db_utils import DB_PATH

VALID_STATES = ["Agendado", "Éxito", "RollBack", "Fallida", "En Seguimiento"]


def upsert_vm_status(
    vm_id: str,
    cliente: str,
    nuevo_estado: str,
    fecha_ejecucion: str = "",
    fecha_finalizacion: str = "",
    observaciones: str = "",
) -> tuple[bool, str]:
    """
    Inserta o actualiza el registro de estado en ESTADO_VMS.
    Si el vm_id ya existe, hace UPDATE; si no, INSERT.
    Retorna (True, "") en éxito o (False, mensaje_error).
    """
    if nuevo_estado not in VALID_STATES:
        return False, f"Estado inválido: {nuevo_estado}"

    try:
        conn = sqlite3.connect(DB_PATH)

        exists = conn.execute(
            'SELECT 1 FROM ESTADO_VMS WHERE "VM_ID_TM" = ?', (vm_id,)
        ).fetchone()

        if exists:
            conn.execute(
                """UPDATE ESTADO_VMS SET
                     "Cliente"              = ?,
                     "Estado_Migracion"     = ?,
                     "Fecha_Ejecucion"      = ?,
                     "Fecha_Finalizacion"   = ?,
                     "Observaciones_Fallo"  = ?
                   WHERE "VM_ID_TM" = ?""",
                (cliente, nuevo_estado, fecha_ejecucion,
                 fecha_finalizacion, observaciones, vm_id),
            )
        else:
            conn.execute(
                """INSERT INTO ESTADO_VMS
                     ("VM_ID_TM","Cliente","Estado_Migracion",
                      "Fecha_Ejecucion","Fecha_Finalizacion","Observaciones_Fallo")
                   VALUES (?,?,?,?,?,?)""",
                (vm_id, cliente, nuevo_estado, fecha_ejecucion,
                 fecha_finalizacion, observaciones),
            )

        conn.commit()
        conn.close()
        return True, ""
    except Exception as e:
        return False, str(e)


def get_vm_status(vm_id: str) -> dict:
    """
    Devuelve el registro de ESTADO_VMS para vm_id, o un dict vacío.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        import pandas as pd
        df = pd.read_sql_query(
            'SELECT * FROM ESTADO_VMS WHERE "VM_ID_TM" = ?', conn, params=(vm_id,)
        )
        conn.close()
        return df.iloc[0].to_dict() if not df.empty else {}
    except:
        return {}