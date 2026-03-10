"""
ui/tab_notificaciones.py
Tab para registrar notificaciones masivas a clientes.
Al final, un expander permite agendar una ventana de mantenimiento
sin salir del tab.
"""
import sqlite3

import pandas as pd
import streamlit as st

from logic.crud_operaciones import (
    guardar_notificaciones_masivas,
    guardar_ventana_mantenimiento,
    obtener_vms_disponibles,
)
from ui.components import (
    DESC_AMBIENTES,
    ambiente_desc,
    chip_input,
    section_card,
)

DIAS        = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
SEMANAS     = ["1", "2", "3", "4"]
COL_CLIENTE = "CUSTOMER_Name_SCCD-TM"
COL_VM_ID   = "VM_ID_TM"


def _clientes_directorio() -> list:
    conn = sqlite3.connect("migraciones.db")
    try:
        return pd.read_sql_query(
            'SELECT DISTINCT "Cliente" FROM DIRECTORIO_CLIENTE ORDER BY "Cliente"', conn
        )["Cliente"].tolist()
    except Exception:
        return []
    finally:
        conn.close()


def _clientes_pendientes() -> list:
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
        try:
            return pd.read_sql_query(
                f'SELECT DISTINCT "{COL_CLIENTE}" FROM DATABASE ORDER BY "{COL_CLIENTE}"', conn
            )[COL_CLIENTE].tolist()
        except Exception:
            return []
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Ventana scheduling section (inside expander)
# ─────────────────────────────────────────────────────────────
def _form_ventana():
    clientes = _clientes_pendientes()

    with section_card("🏢 Cliente y VMs"):
        cliente_sel = st.selectbox(
            "Cliente:",
            ["— Seleccione —"] + clientes,
            key="nv_cliente",
        )

    if not cliente_sel or cliente_sel == "— Seleccione —":
        return

    df_vms = obtener_vms_disponibles(cliente_sel)
    if df_vms.empty:
        st.success("✅ Este cliente no tiene VMs pendientes de agendar.")
        return

    with section_card("🖥️ Máquinas Virtuales"):
        vms_sel = st.multiselect(
            "VMs a agendar:",
            options=df_vms[COL_VM_ID].tolist(),
            key="nv_vms",
        )

    if not vms_sel:
        return

    st.dataframe(
        df_vms[df_vms[COL_VM_ID].isin(vms_sel)],
        use_container_width=True, hide_index=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    col_a, col_b = st.columns(2, gap="large")
    with col_a:
        with section_card("📋 Información General"):
            en_uso      = st.selectbox("¿En Uso?",     ["Si", "No"],                            key="nv_en_uso")
            ambiente    = st.selectbox("Ambiente:",    list(DESC_AMBIENTES.keys()),              key="nv_ambiente")
            ambiente_desc(ambiente)
            criticidad  = st.selectbox("Criticidad:", ["Critico", "Alta", "Media", "Baja"],     key="nv_criticidad")
            motivo_crit = st.text_input("Razón de la criticidad:",                              key="nv_motivo")

    with col_b:
        with section_card("📝 Detalles Técnicos"):
            apps_lista  = chip_input("Aplicaciones y Servicios:", "nv_apps_chips")
            st.markdown("<br>", unsafe_allow_html=True)
            comentarios = st.text_area("Comentarios Finales:", key="nv_comentarios", height=110)

    with section_card("🕒 Configuración de Horario"):
        tipo_ventana = st.radio(
            "Tipo de Ventana:",
            ["Horario Específico", "Rango de Horario", "Horario Semi-específico"],
            horizontal=True, key="nv_tipo_ventana",
        )
        st.markdown("<br>", unsafe_allow_html=True)

        start_val = end_val = sem_val = dia_val = turn_val = None

        if tipo_ventana == "Horario Específico":
            c1, c2 = st.columns(2, gap="large")
            with c1:
                d_i = st.date_input("📅 Fecha Inicio", key="nv_di")
                t_i = st.time_input("🕐 Hora Inicio",  key="nv_ti")
            with c2:
                d_f = st.date_input("📅 Fecha Fin",    key="nv_df")
                t_f = st.time_input("🕐 Hora Fin",     key="nv_tf")
            start_val, end_val = f"{d_i} {t_i}", f"{d_f} {t_f}"

        elif tipo_ventana == "Rango de Horario":
            c1, c2, c3 = st.columns(3, gap="large")
            with c1: sem_val  = st.multiselect("Semanas:", SEMANAS, key="nv_sem")
            with c2: dia_val  = st.multiselect("Días:",    DIAS,    key="nv_dia")
            with c3: turn_val = st.selectbox("Turno:", ["Mañana","Tarde","Noche"], key="nv_turno")

        elif tipo_ventana == "Horario Semi-específico":
            c1, c2, c3 = st.columns(3, gap="large")
            with c1: sem_val = st.multiselect("Semanas:", SEMANAS, key="nv_sem2")
            with c2: dia_val = st.multiselect("Días:",    DIAS,    key="nv_dia2")
            with c3:
                t_i_s = st.time_input("🕐 Hora Inicio", key="nv_tis")
                t_f_s = st.time_input("🕐 Hora Fin",    key="nv_tfs")
            start_val, end_val = str(t_i_s), str(t_f_s)

    col_btn, _ = st.columns([2, 5])
    with col_btn:
        if st.button("✅ Guardar Ventana", key="nv_btn_guardar", use_container_width=True):
            datos = {
                "en_uso":            en_uso,
                "ambiente":          ambiente,
                "descripcion":       DESC_AMBIENTES[ambiente][1],
                "apps":              ", ".join(apps_lista),
                "tipo_ventana":      tipo_ventana,
                "start_dt":          start_val,
                "end_dt":            end_val,
                "turno_rango":       turn_val,
                "semanas_rango":     ",".join(sem_val) if sem_val else None,
                "dias_rango":        ",".join(dia_val) if dia_val else None,
                "criticidad":        criticidad,
                "motivo_criticidad": motivo_crit,
                "comentarios":       comentarios,
            }
            if guardar_ventana_mantenimiento(cliente_sel, vms_sel, datos):
                st.success(f"✅ {len(vms_sel)} VM(s) agendadas correctamente.")
                st.session_state["nv_apps_chips"] = []
                st.balloons()
                st.rerun()
            else:
                st.error("❌ Error al guardar. Revisa los datos e intenta de nuevo.")


# ─────────────────────────────────────────────────────────────
# Main render
# ─────────────────────────────────────────────────────────────
def render():
    st.markdown("## 📢 Registro de Notificaciones a Clientes")

    clientes_lista = _clientes_directorio()

    col_form, col_info = st.columns([1.5, 1])

    with col_form:
        with st.form("form_notificaciones", clear_on_submit=True):
            st.markdown("### ✉️ Detalles del Envío")

            clientes_sel = st.multiselect(
                "Clientes notificados (uno o varios):", clientes_lista
            )
            c1, c2 = st.columns(2)
            with c1:
                creado_por = st.text_input("Ingeniero / Registrado por:")
                canal      = st.selectbox("Canal:", ["Email","Teléfono","Reunión Teams","WhatsApp","Otro"])
            with c2:
                estado   = st.selectbox("Estado:", ["Enviado","Recibido","Sin Respuesta","Rebotado"])
                cantidad = st.number_input("Intentos / mensajes:", min_value=1, value=1)

            notas  = st.text_area("Notas / Asunto / Observaciones:")
            submit = st.form_submit_button("🚀 Registrar Notificaciones")

            if submit:
                if not clientes_sel:
                    st.error("Selecciona al menos un cliente.")
                elif not creado_por.strip():
                    st.error("Indica quién registra la notificación.")
                else:
                    if guardar_notificaciones_masivas(
                        clientes_sel, creado_por.strip(), estado, canal, str(cantidad), notas.strip()
                    ):
                        st.success(f"✅ Notificación registrada para {len(clientes_sel)} cliente(s).")
                        st.balloons()

    with col_info:
        st.info(
            "**💡 Tip de uso masivo:**\n\n"
            "Usa esta herramienta cuando envíes un correo general o invites a múltiples "
            "clientes a una reunión de mantenimiento. El sistema crea una fila individual "
            "por cada cliente seleccionado en `NOTIFICACIONES_CLIENTES`."
        )

    # ── Expander: agendar ventana desde esta misma tab ────
    st.markdown("---")
    with st.expander("🗓️ ¿Concretaste una ventana con algún cliente? Agrégala aquí", expanded=False):
        st.markdown(
            '<div style="font-size:.8rem;color:#7B4A1E;font-weight:500;'
            'margin-bottom:14px;">Completa los campos para registrar la ventana '
            'de mantenimiento sin salir de esta pantalla.</div>',
            unsafe_allow_html=True,
        )
        _form_ventana()