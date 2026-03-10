import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = 'migraciones.db'

def sincronizar_vms_pendientes():
    """
    Sincroniza la tabla DATABASE con ESTADO_VMS.
    Inserta como 'Pendiente' cualquier VM_ID_TM que esté en DATABASE pero no en ESTADO_VMS.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Usamos comillas dobles para la columna CUSTOMER_Name_SCCD-TM por el guion
    query = """
    INSERT INTO ESTADO_VMS (VM_ID_TM, Cliente, Estado_Migracion)
    SELECT d.VM_ID_TM, d."CUSTOMER_Name_SCCD-TM", 'Pendiente'
    FROM DATABASE d
    LEFT JOIN ESTADO_VMS e ON d.VM_ID_TM = e.VM_ID_TM
    WHERE e.VM_ID_TM IS NULL
    """
    try:
        cursor.execute(query)
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error al sincronizar: {e}")
    finally:
        conn.close()

def obtener_vms_disponibles(cliente_nombre):
    """
    Obtiene las VMs de un cliente específico que están marcadas como 'Pendiente'
    y que AÚN NO han sido agendadas en la tabla VMs.
    """
    conn = sqlite3.connect(DB_PATH)
    query = """
    SELECT 
        d.VM_ID_TM, 
        d.CID, 
        d.VM, 
        d."Primary IP Address" as HostName, 
        d."Total disk capacity MiB" as Almacenamiento
    FROM DATABASE d
    LEFT JOIN ESTADO_VMS e ON d.VM_ID_TM = e.VM_ID_TM
    WHERE d."CUSTOMER_Name_SCCD-TM" = ? 
    AND (e.Estado_Migracion = 'Pendiente' OR e.Estado_Migracion IS NULL)
    AND NOT EXISTS (SELECT 1 FROM VMs v WHERE v.VM_ID_TM = d.VM_ID_TM)
    """
    try:
        df = pd.read_sql_query(query, conn, params=(cliente_nombre,))
    finally:
        conn.close()
    return df

def guardar_ventana_mantenimiento(cliente, vms_seleccionadas, datos_formulario):
    """
    Guarda la información de agendamiento en la tabla VMs.
    Además, cambia el estado a 'Asignada' tanto en VMs como en ESTADO_VMS.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # TRUCO: Asegurarnos de que la tabla VMs tenga la columna Estado
    # Si no la tiene, la crea al vuelo. Si ya la tiene, ignora el error.
    try:
        cursor.execute("ALTER TABLE VMs ADD COLUMN Estado TEXT DEFAULT 'Asignada'")
    except sqlite3.OperationalError:
        pass 
        
    placeholders = ','.join(['?'] * len(vms_seleccionadas))
    query_base = f"""
    SELECT VM_ID_TM, CID, VM, "Primary IP Address", "Total disk capacity MiB" 
    FROM DATABASE 
    WHERE VM_ID_TM IN ({placeholders})
    """
    
    try:
        df_base = pd.read_sql_query(query_base, conn, params=vms_seleccionadas)
        
        for _, row in df_base.iterrows():
            # 1. Insertar en la tabla de agendamiento con Estado = 'Asignada'
            query_insert = """
            INSERT INTO VMs (
                Cliente, CID_Seleccionado, VM, VM_ID_TM, "Apps y Servicios",
                Tipo_Ventana, StartDateTime, EndDateTime, Turno_Rango,
                Semanas_Rango, "Días_Rango", Criticidad, Motivo_Criticidad,
                HostName, Almacenamiento, En_Uso, Ambiente, Comentarios, Estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            cursor.execute(query_insert, (
                cliente,
                row['CID'],
                row['VM'],
                row['VM_ID_TM'],
                datos_formulario['apps'],
                datos_formulario['tipo_ventana'],
                datos_formulario['StartDateTime'],
                datos_formulario['EndDateTime'],
                datos_formulario['turno_rango'],
                datos_formulario['semanas_rango'],
                datos_formulario['Días_Rango'],
                datos_formulario['criticidad'],
                datos_formulario['motivo_criticidad'],
                row['Primary IP Address'],
                row['Total disk capacity MiB'],
                datos_formulario['en_uso'],
                datos_formulario['ambiente'],
                datos_formulario['comentarios'],
                'Asignada' # <--- Inyección directa del estado nuevo
            ))
            
            # 2. Actualizar la tabla ESTADO_VMS para que deje de estar "Pendiente"
            query_update = "UPDATE ESTADO_VMS SET Estado_Migracion = 'Asignada' WHERE VM_ID_TM = ?"
            cursor.execute(query_update, (row['VM_ID_TM'],))
            
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error al guardar ventana: {e}")
        return False
    finally:
        conn.close()
    return True

def guardar_log_vm(vm_id: str, cliente: str, descripcion: str) -> bool:
    """Guarda un nuevo log para una máquina virtual."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    query = """
    INSERT INTO LOGS_VMS ("VM_ID_TM", "Cliente", "Fecha", "Descripcion") 
    VALUES (?, ?, ?, ?)
    """
    try:
        cursor.execute(query, (vm_id, cliente, fecha_actual, descripcion))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error al guardar log: {e}")
        return False
    finally:
        conn.close()

def obtener_historial_logs(vm_id: str) -> pd.DataFrame:
    """Trae el historial de logs de una VM."""
    conn = sqlite3.connect(DB_PATH)
    query = 'SELECT "Fecha", "Descripcion" FROM LOGS_VMS WHERE "VM_ID_TM" = ? ORDER BY "Fecha" DESC'
    df = pd.read_sql_query(query, conn, params=(vm_id,))
    conn.close()
    return df

def guardar_notificaciones_masivas(clientes: list, creado_por: str, estado: str, canal: str, cantidad: str, notas: str) -> bool:
    """Guarda notificaciones para múltiples clientes a la vez."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    query = """
    INSERT INTO NOTIFICACIONES_CLIENTES (
        "Cliente", "Creado_Por", "Estado_Notificacion", 
        "Fecha Notificación", "Canal_Notificacion", 
        "Cantidad_Notificaciones", "Notas"
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    try:
        for cliente in clientes:
            cursor.execute(query, (cliente, creado_por, estado, fecha_actual, canal, str(cantidad), notas))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error al guardar notificaciones: {e}")
        return False
    finally:
        conn.close()