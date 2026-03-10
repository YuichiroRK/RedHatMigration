"""ui/db_utils.py — Schema inspector & column mapper."""

import sqlite3
import streamlit as st
import pandas as pd

DB_PATH = "migraciones.db"

# Nombre real de la BD → primero; alternativas después
_CANDIDATES = {
    "vm_id":             ["VM_ID_TM",         "vm_id",        "vmid"],
    "cliente":           ["Cliente",           "CUSTOMER_Name_SCCD-TM", "cliente", "customer"],
    "tipo_ventana":      ["Tipo_Ventana",      "tipo_ventana", "tipo"],
    "start_dt":          ["StartDateTime",     "start_dt",     "fecha_inicio", "inicio"],
    "end_dt":            ["EndDateTime",       "end_dt",       "fecha_fin",    "fin"],
    "turno_rango":       ["Turno_Rango",       "turno_rango",  "turno"],
    "semanas_rango":     ["Semanas_Rango",     "semanas_rango","semanas"],
    "dias_rango":        ["Días_Rango",        "Dias_Rango",   "dias_rango",   "dias"],
    "estado":            ["Estado",            "estado",       "status"],
    "ambiente":          ["Ambiente",          "ambiente",     "env"],
    "criticidad":        ["Criticidad",        "criticidad",   "priority"],
    "en_uso":            ["En_Uso",            "en_uso",       "en uso"],
    "apps":              ["Apps y Servicios",  "apps",         "aplicaciones", "apps_servicios"],
    "comentarios":       ["Comentarios",       "comentarios",  "comments"],
    "motivo_criticidad": ["Motivo_Criticidad", "motivo_criticidad", "motivo_crit"],
}


def get_vms_columns() -> list:
    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.execute("PRAGMA table_info(VMs)")
        cols = [row[1] for row in cur.fetchall()]
        conn.close()
        return cols
    except:
        return []


def build_column_map() -> dict:
    actual       = get_vms_columns()
    actual_lower = {c.lower(): c for c in actual}
    mapping = {}
    for role, candidates in _CANDIDATES.items():
        found = None
        for cand in candidates:
            if cand.lower() in actual_lower:
                found = actual_lower[cand.lower()]
                break
        mapping[role] = found
    return mapping


def safe_get(row: pd.Series, col, default="") -> str:
    if col is None or col not in row.index:
        return default
    val = row[col]
    return default if pd.isna(val) else str(val)


def diagnostics_expander():
    with st.expander("🔧 Diagnóstico de esquema DB", expanded=False):
        cols = get_vms_columns()
        if not cols:
            st.warning("No se pudo leer la tabla VMs.")
            return
        st.code(", ".join(cols))
        mapping = build_column_map()
        rows = [{"Rol": r, "Columna detectada": c or "⚠️ NO ENCONTRADA"}
                for r, c in mapping.items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        try:
            conn = sqlite3.connect(DB_PATH)
            df   = pd.read_sql_query("SELECT * FROM VMs LIMIT 3", conn)
            conn.close()
            st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(str(e))