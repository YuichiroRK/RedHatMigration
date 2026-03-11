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

    # ══════════════════════════════════════════════════════
    # 1. HORARIO — primero
    # ══════════════════════════════════════════════════════
    with section_card("🕒 Configuración de Horario"):

        # ── Criticidad aquí para condicionar el horario ──
        st.markdown(
            '<div style="font-size:.7rem;font-weight:800;letter-spacing:.08em;'
            'text-transform:uppercase;color:#FF7800;margin-bottom:8px;">⚠️ Criticidad del cliente</div>',
            unsafe_allow_html=True,
        )
        CRIT_DESC = {
            "Crítico": ("🔴", "Cliente muy complejo de atender. Requiere coordinación especial, múltiples validaciones y acompañamiento técnico cercano."),
            "Alta":    ("🟠", "Cliente con cierta complejidad. Puede requerir atención adicional pero es manejable con planificación."),
            "Media":   ("🟡", "Cliente estándar. El proceso es sencillo y no presenta mayores complicaciones."),
            "Baja":    ("🟢", "Cliente sin complicaciones. El proceso es directo y fluye sin fricciones."),
        }
        crit_html = '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">'
        for nivel, (icon, desc) in CRIT_DESC.items():
            crit_html += (
                f'<div style="flex:1;min-width:160px;background:#F9FAFB;border:1.5px solid #E2E6ED;'
                f'border-radius:10px;padding:10px 12px;">'
                f'<div style="font-size:.8rem;font-weight:800;margin-bottom:4px;">{icon} {nivel}</div>'
                f'<div style="font-size:.72rem;color:#4A5568;line-height:1.4;">{desc}</div>'
                f'</div>'
            )
        crit_html += '</div>'
        st.markdown(crit_html, unsafe_allow_html=True)

        criticidad = st.selectbox(
            "Criticidad del cliente:",
            list(CRIT_DESC.keys()),
            key="nv_criticidad",
            label_visibility="collapsed",
        )
        motivo_crit = st.text_input("Razón de la criticidad:", key="nv_motivo")

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Si Crítico o Alta → advertencia + opción de agendar igual ──
        es_complejo = criticidad in ("Crítico", "Alta")
        forzar_agenda = False
        if es_complejo:
            st.warning(
                "⚡ Clientes **Crítico** o **Alta** normalmente no requieren agendar una ventana. "
                "Se registrarán como tipo **Complejo** — pero puedes agendar igual si ya tienes fecha confirmada."
            )
            forzar_agenda = st.checkbox(
                "📅 Tengo una fecha confirmada, quiero agendar de todas formas",
                key="nv_forzar_agenda",
            )
            if not forzar_agenda:
                tipo_ventana = "Complejo"
                start_val = end_val = sem_val = dia_val = turn_val = None

        if not es_complejo or forzar_agenda:
            # ── Tipo de ventana: Rango primero, luego Específico ──
            tipo_ventana = st.radio(
                "Tipo de Ventana:",
                ["Rango de Horario", "Horario Específico / Semi-específico"],
                horizontal=True, key="nv_tipo_ventana",
            )
            st.markdown("<br>", unsafe_allow_html=True)

            start_val = end_val = sem_val = dia_val = turn_val = None

            if tipo_ventana == "Rango de Horario":
                c1, c2, c3 = st.columns(3, gap="large")
                with c1: sem_val  = st.multiselect("Semanas:", SEMANAS, key="nv_sem")
                with c2: dia_val  = st.multiselect("Días:",    DIAS,    key="nv_dia")
                with c3: turn_val = st.selectbox("Turno:", ["Mañana (6AM a 2PM)","Tarde (2PM a 10PM)","Noche (10PM a 6AM)"], key="nv_turno")

            else:
                # Toggle: fecha específica vs horas con semanas
                modo = st.toggle("📅 Usar fechas exactas (desactivado = solo horas + semanas)", key="nv_modo_esp", value=True)
                st.markdown("<br>", unsafe_allow_html=True)

                if modo:
                    # Horario Específico
                    tipo_ventana = "Horario Específico"
                    c1, c2 = st.columns(2, gap="large")
                    with c1:
                        d_i = st.date_input("📅 Fecha Inicio", key="nv_di")
                        t_i = st.time_input("🕐 Hora Inicio",  key="nv_ti")
                    with c2:
                        d_f = st.date_input("📅 Fecha Fin",    key="nv_df")
                        t_f = st.time_input("🕐 Hora Fin",     key="nv_tf")
                    start_val, end_val = f"{d_i} {t_i}", f"{d_f} {t_f}"
                else:
                    # Horario Semi-específico
                    tipo_ventana = "Horario Semi-específico"
                    c1, c2, c3 = st.columns(3, gap="large")
                    with c1: sem_val = st.multiselect("Semanas:", SEMANAS, key="nv_sem2")
                    with c2: dia_val = st.multiselect("Días:",    DIAS,    key="nv_dia2")
                    with c3:
                        t_i_s = st.time_input("🕐 Hora Inicio", key="nv_tis")
                        t_f_s = st.time_input("🕐 Hora Fin",    key="nv_tfs")
                    start_val, end_val = str(t_i_s), str(t_f_s)

    # ══════════════════════════════════════════════════════
    # 2. DETALLES TÉCNICOS + INFO GENERAL — después del horario
    # ══════════════════════════════════════════════════════
    col_a, col_b = st.columns(2, gap="large")

    with col_a:
        with section_card("📝 Detalles Técnicos"):
            apps_lista  = chip_input("Aplicaciones y Servicios:", "nv_apps_chips")
            st.markdown("<br>", unsafe_allow_html=True)
            comentarios = st.text_area("Comentarios Finales:", key="nv_comentarios", height=110)

    with col_b:
        with section_card("📋 Información General"):
            en_uso = st.selectbox(
                "¿La(s) VM(s) están actualmente en Uso?", ["Si", "No"], key="nv_en_uso"
            )

            # ── Ambiente: mostrar las 3 descripciones primero ──
            st.markdown(
                '<div style="font-size:.72rem;font-weight:700;color:#4A5568;margin-bottom:6px;">'
                'Descripción de ambientes:</div>',
                unsafe_allow_html=True,
            )
            amb_preview = ""
            for amb_key, (titulo, desc, _) in DESC_AMBIENTES.items():
                COLOR = {"PROD": "#FFF5F5", "DEV": "#F0FFF4", "QA": "#FEFCBF"}
                BORDER = {"PROD": "#FC8181", "DEV": "#68D391", "QA": "#F6E05E"}
                bg  = COLOR.get(amb_key, "#F9FAFB")
                brd = BORDER.get(amb_key, "#CBD5E0")
                amb_preview += (
                    f'<div style="background:{bg};border:1.5px solid {brd};'
                    f'border-radius:8px;padding:6px 10px;margin-bottom:5px;">'
                    f'<span style="font-size:.75rem;font-weight:800;">{titulo}</span> '
                    f'<span style="font-size:.7rem;color:#4A5568;">— {desc}</span>'
                    f'</div>'
                )
            st.markdown(amb_preview, unsafe_allow_html=True)

            ambiente = st.selectbox(
                "Ambiente:", list(DESC_AMBIENTES.keys()), key="nv_ambiente"
            )

    # ── Botón guardar ─────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    col_btn, _ = st.columns([2, 5])
    with col_btn:
        if st.button("✅ Guardar Ventana", key="nv_btn_guardar", use_container_width=True):
            datos = {
                "en_uso":            en_uso,
                "ambiente":          ambiente,
                "descripcion":       DESC_AMBIENTES[ambiente][1],
                "apps":              ", ".join(apps_lista),
                "tipo_ventana":      tipo_ventana,
                "StartDateTime":     start_val,
                "EndDateTime":       end_val,
                "turno_rango":       turn_val,
                "semanas_rango":     ",".join(sem_val) if sem_val else None,
                "Días_Rango":        ",".join(dia_val) if dia_val else None,
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
# Client selector (outside form — supports paste)
# ─────────────────────────────────────────────────────────────
def _cliente_selector(clientes_lista: list) -> list:
    """
    Paste + multiselect OUTSIDE the form so dynamic defaults work correctly.
    Returns the final list of selected clients.
    """
    with section_card("👥 Selección de Clientes"):
        # ── Paste area ───────────────────────────────────
        paste_raw = st.text_area(
            "📋 Pegar clientes (Ctrl+V — uno por línea o separados por coma):",
            key="notif_paste",
            height=75,
            placeholder="Pega aquí la lista de clientes…",
        )

        # Parse + match against directory (case-insensitive)
        auto_selected = []
        not_found     = []
        if paste_raw.strip():
            tokens = list(dict.fromkeys(
                t.strip()
                for t in paste_raw.replace(",", "\n").splitlines()
                if t.strip()
            ))
            upper_map = {c.upper(): c for c in clientes_lista if c and isinstance(c, str)}
            for tok in tokens:
                match = upper_map.get(tok.upper())
                if match:
                    auto_selected.append(match)
                else:
                    not_found.append(tok)

            if not_found:
                st.warning(
                    "⚠️ No encontrados en el directorio: " +
                    ", ".join(f"**{n}**" for n in not_found)
                )
            if auto_selected:
                st.success(
                    f"✅ {len(auto_selected)} cliente(s) identificados automáticamente."
                )

        # ── Multiselect — default driven by paste result ─
        # Use session_state to persist selection across reruns
        ss_key = "notif_clientes_sel"
        if auto_selected:
            # Merge pasted into existing selection without duplicates
            existing = st.session_state.get(ss_key, [])
            merged   = list(dict.fromkeys(existing + auto_selected))
            st.session_state[ss_key] = merged

        clientes_sel = st.multiselect(
            "Clientes seleccionados:",
            options=clientes_lista,
            default=st.session_state.get(ss_key, []),
            key=ss_key,
        )

    return clientes_sel


# ─────────────────────────────────────────────────────────────
# Main render
# ─────────────────────────────────────────────────────────────
def render():
    st.markdown("## 📢 Registro de Notificaciones a Clientes")

    clientes_lista = _clientes_directorio()

    # ── Client selector lives OUTSIDE the form ───────────
    clientes_sel = _cliente_selector(clientes_lista)

    col_form, col_info = st.columns([1.5, 1])

    with col_form:
        with st.form("form_notificaciones", clear_on_submit=True):
            st.markdown("### ✉️ Detalles del Envío")

            # Show selected clients as read-only summary inside the form
            if clientes_sel:
                st.markdown(
                    f'<div style="background:#F0FFF4;border:1px solid #9AE6B4;'
                    f'border-radius:8px;padding:8px 14px;margin-bottom:10px;'
                    f'font-size:.8rem;color:#22543D;font-weight:600;">'
                    f'✅ {len(clientes_sel)} cliente(s) seleccionado(s): '
                    + ", ".join(clientes_sel[:5])
                    + (f" … y {len(clientes_sel)-5} más" if len(clientes_sel) > 5 else "")
                    + "</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.info("ℹ️ Selecciona clientes arriba antes de registrar.")

            c1, c2 = st.columns(2)
            with c1:
                creado_por = st.text_input("Ingeniero / Registrado por:")
                canal      = st.selectbox("Canal:", ["Email","Teléfono","Reunión Teams","WhatsApp","Otro"])
            with c2:
                estado   = st.selectbox("Estado:", ["Enviado","Recibido","Sin Respuesta","Rebotado","Cliente por Contactar"])

            notas  = st.text_area("Notas / Asunto / Observaciones:")
            submit = st.form_submit_button("🚀 Registrar Notificaciones")

            if submit:
                if not clientes_sel:
                    st.error("Selecciona al menos un cliente en la sección de arriba.")
                elif not creado_por.strip():
                    st.error("Indica quién registra la notificación.")
                else:
                    if guardar_notificaciones_masivas(
                        clientes_sel, creado_por.strip(), estado, canal, "1", notas.strip()
                    ):
                        st.success(f"✅ Notificación registrada para {len(clientes_sel)} cliente(s).")
                        # Clear client selection after successful submit
                        st.session_state["notif_clientes_sel"] = []
                        st.session_state["notif_paste"] = ""
                        st.balloons()

    with col_info:
        st.info(
            "**💡 Tip de uso masivo:**\n\n"
            "Pega la lista de clientes con Ctrl+V (uno por línea o separados "
            "por coma) y se seleccionarán automáticamente.\n\n"
            "El sistema crea una fila individual por cada cliente en "
            "`NOTIFICACIONES_CLIENTES`."
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