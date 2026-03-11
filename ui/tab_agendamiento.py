"""
ui/tab_agendamiento.py
Lógica y layout completo del tab de Agendamiento.
"""

import streamlit as st
import pandas as pd
import sqlite3
import time

from ui.components import (
    DESC_AMBIENTES,
    section_card,
    ambiente_desc,
    chip_input,
)
from logic.crud_operaciones import obtener_vms_disponibles, guardar_ventana_mantenimiento

COL_CLIENTE = "CUSTOMER_Name_SCCD-TM"
COL_VM_ID   = "VM_ID_TM"
DIAS        = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
SEMANAS     = ["1", "2", "3", "4"]


def _cargar_clientes() -> list:
    """Devuelve clientes que aún tienen VMs sin agendar."""
    conn = sqlite3.connect("migraciones.db")
    try:
        df = pd.read_sql_query(f"""
            SELECT DISTINCT d."{COL_CLIENTE}"
            FROM DATABASE d
            WHERE NOT EXISTS (
                SELECT 1 FROM VMs v WHERE v."{COL_VM_ID}" = d."{COL_VM_ID}"
            )
            ORDER BY d."{COL_CLIENTE}"
        """, conn)
        return df[COL_CLIENTE].tolist() if not df.empty else []
    except Exception:
        # fallback si la tabla VMs aún no existe
        df = pd.read_sql_query(
            f'SELECT DISTINCT "{COL_CLIENTE}" FROM DATABASE ORDER BY "{COL_CLIENTE}"', conn
        )
        return df[COL_CLIENTE].tolist()
    finally:
        conn.close()


def render():
    """Renderiza el tab completo de Agendamiento."""

    clientes = _cargar_clientes()

    # ── Selección de cliente (DENTRO del card) ──
    with section_card("🏢 Selección de Cliente"):
        cliente_sel = st.selectbox(
            "Cliente:",
            ["— Seleccione un cliente —"] + clientes,
            key="cliente_sel",
        )

    if not cliente_sel or cliente_sel == "— Seleccione un cliente —":
        return

    df_vms = obtener_vms_disponibles(cliente_sel)

    if df_vms.empty:
        st.success("✅ Este cliente no tiene máquinas virtuales Sin Agendar de agendar.")
        return

    # ── Selección de VMs (DENTRO del card) ──
    with section_card("🖥️ Máquinas Virtuales"):
        vms_seleccionadas = st.multiselect(
            "Seleccione las VMs a agendar:",
            options=df_vms[COL_VM_ID].tolist(),
            key="vms_sel",
        )

    if not vms_seleccionadas:
        return

    # Vista previa de las VMs elegidas
    df_resumen = df_vms[df_vms[COL_VM_ID].isin(vms_seleccionadas)]
    st.dataframe(df_resumen, use_container_width=True, hide_index=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Información General + Detalles ──
    col_a, col_b = st.columns(2, gap="large")

    with col_a:
        with section_card("📋 Información General"):
            en_uso     = st.selectbox("¿La(s) Máquina(s) Virtual está actualmente en Uso?", ["Si", "No"], key="en_uso")
            ambiente   = st.selectbox("¿En qué ambiente se encuentra la VM?:", list(DESC_AMBIENTES.keys()), key="ambiente")
            ambiente_desc(ambiente)
            criticidad  = st.selectbox("¿Qué tan crítico fue/será atender al cliente?:", ["Critico", "Alta", "Media", "Baja"], key="criticidad")
            motivo_crit = st.text_input("Razón de la criticidad:", key="motivo")

    with col_b:
        with section_card("📝 Detalles Técnicos"):
            apps_lista  = chip_input("Aplicaciones y Servicios:", "apps_chips")
            st.markdown("<br>", unsafe_allow_html=True)
            comentarios = st.text_area("Comentarios Finales:", key="comentarios", height=110)

    # ── Configuración de Horario ──
    with section_card("🕒 Configuración de Horario"):
        tipo_ventana = st.radio(
            "Tipo de Ventana:",
            ["Horario Específico", "Rango de Horario", "Horario Semi-específico"],
            horizontal=True,
            key="tipo_ventana",
        )
        st.markdown("<br>", unsafe_allow_html=True)

        start_val = end_val = None
        sem_val = dia_val = turn_val = None

        if tipo_ventana == "Horario Específico":
            c1, c2 = st.columns(2, gap="large")
            with c1:
                d_i = st.date_input("📅 Fecha Inicio", key="spec_di")
                t_i = st.time_input("🕐 Hora Inicio",  key="spec_ti")
            with c2:
                d_f = st.date_input("📅 Fecha Fin",    key="spec_df")
                t_f = st.time_input("🕐 Hora Fin",     key="spec_tf")
            start_val, end_val = f"{d_i} {t_i}", f"{d_f} {t_f}"

        elif tipo_ventana == "Rango de Horario":
            c1, c2, c3 = st.columns(3, gap="large")
            with c1:
                sem_val  = st.multiselect("Semanas:",  SEMANAS, key="rango_sem")
            with c2:
                dia_val  = st.multiselect("Días:",     DIAS,    key="rango_dia")
            with c3:
                turn_val = st.selectbox("Turno:", ["Mañana (6AM a 2PM)", "Tarde (2PM a 10PM)", "Noche (10PM a 6AM)"], key="rango_turno")

        elif tipo_ventana == "Horario Semi-específico":
            c1, c2, c3 = st.columns(3, gap="large")
            with c1:
                sem_val = st.multiselect("Semanas:", SEMANAS, key="semi_sem")
            with c2:
                dia_val = st.multiselect("Días:",    DIAS,    key="semi_dia")
            with c3:
                t_i_s = st.time_input("🕐 Hora Inicio", key="semi_ti")
                t_f_s = st.time_input("🕐 Hora Fin",    key="semi_tf")
            start_val, end_val = str(t_i_s), str(t_f_s)

    # ── Botón guardar ──
    col_btn, _ = st.columns([2, 5])
    with col_btn:
        guardar = st.button("✅  Guardar Agendamiento", key="btn_guardar", use_container_width=True)

    if guardar:
        datos = {
            "en_uso":            en_uso,
            "ambiente":          ambiente,
            "descripcion":       DESC_AMBIENTES[ambiente][1] if isinstance(DESC_AMBIENTES[ambiente], tuple) else DESC_AMBIENTES[ambiente],
            "apps":              ", ".join(apps_lista) if apps_lista else "",
            "tipo_ventana":      tipo_ventana,
            "StartDateTime":     start_val,
            "EndDateTime":       end_val,
            "turno_rango":       turn_val,
            "semanas_rango":     ",".join(sem_val)  if sem_val  else None,
            "Días_Rango":        ",".join(dia_val)  if dia_val  else None,
            "criticidad":        criticidad,
            "motivo_criticidad": motivo_crit,
            "comentarios":       comentarios,
        }
        if guardar_ventana_mantenimiento(cliente_sel, vms_seleccionadas, datos):
            st.success(f"✅  Se agendaron {len(vms_seleccionadas)} VM(s) correctamente.")
            st.session_state["apps_chips"] = []
            st.balloons()
            
            time.sleep(2) # La pausa para ver los globos
            
            # --- CREAMOS EL TICKET DE REDIRECCIÓN ---
            st.session_state["redirect_to"] = "⏰ Ver Ventanas"
            
            st.rerun() # Disparamos la recarga
        else:
            st.error("❌  Ocurrió un error al guardar. Revise los datos e intente nuevamente.")