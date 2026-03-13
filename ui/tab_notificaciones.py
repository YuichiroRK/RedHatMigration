"""
ui/tab_notificaciones.py
"""
import sqlite3
import pandas as pd
import streamlit as st

from logic.crud_operaciones import (
    guardar_notificaciones_masivas,
    guardar_ventana_mantenimiento,
    obtener_vms_disponibles,
)
from ui.components import DESC_AMBIENTES, chip_input, section_card

DIAS      = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
SEMANAS   = ["1", "2", "3", "4"]
COL_CLI   = "CUSTOMER_Name_SCCD-TM"
COL_VM    = "VM_ID_TM"

ESTADOS_POR_CANAL = {
    "Email": [
        "Correo Enviado",
        "Correo Rebotado",
        "Cliente por Contactar",
        "Agenda Confirmada",
        "Sin Respuesta",
    ],
    "Contacto Directo": [
        "Cliente por Contactar",
        "Agenda Confirmada",
        "Sin Respuesta",
    ],
}


# ──────────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────────
def _team_migracion():
    conn = sqlite3.connect("migraciones.db")
    try:
        return pd.read_sql_query(
            'SELECT "Nombre" FROM TEAM_MIGRACION WHERE "Nombre" IS NOT NULL ORDER BY "Nombre"', conn
        )["Nombre"].tolist()
    except Exception:
        return []
    finally:
        conn.close()


def _clientes_directorio():
    conn = sqlite3.connect("migraciones.db")
    try:
        return pd.read_sql_query(
            'SELECT DISTINCT "Cliente" FROM DIRECTORIO_CLIENTE ORDER BY "Cliente"', conn
        )["Cliente"].tolist()
    except Exception:
        return []
    finally:
        conn.close()


def _clientes_pendientes():
    conn = sqlite3.connect("migraciones.db")
    try:
        df = pd.read_sql_query(f"""
            SELECT DISTINCT d."{COL_CLI}" FROM DATABASE d
            WHERE NOT EXISTS (SELECT 1 FROM VMs v WHERE v."{COL_VM}"=d."{COL_VM}")
            ORDER BY d."{COL_CLI}"
        """, conn)
        return df[COL_CLI].tolist() if not df.empty else []
    except Exception:
        try:
            return pd.read_sql_query(
                f'SELECT DISTINCT "{COL_CLI}" FROM DATABASE ORDER BY "{COL_CLI}"', conn
            )[COL_CLI].tolist()
        except Exception:
            return []
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────
# Client selector with paste
# ──────────────────────────────────────────────────────────
def _cliente_selector(clientes_lista):
    with section_card("👥 Selección de Clientes"):
        st.markdown(
            '<div style="font-size:.74rem;color:#4A5568;margin-bottom:6px;">'
            '📋 Pega clientes (uno por línea, coma o punto y coma) — '
            'se identifican automáticamente al salir del campo.</div>',
            unsafe_allow_html=True,
        )
        # If paste was just processed, wipe the widget key before rendering
        if st.session_state.get("_notif_paste_cleared"):
            st.session_state["notif_paste"] = ""
            st.session_state["_notif_paste_cleared"] = False

        paste_raw = st.text_area(
            "Pegar:", value=st.session_state.get("_notif_paste_store", ""),
            key="notif_paste", height=80,
            placeholder="Pega aquí o escribe los clientes…",
            label_visibility="collapsed",
        )
        # Sync store with whatever is currently in the widget
        st.session_state["_notif_paste_store"] = paste_raw

        # Auto-detect change → merge into selection + rerun
        last = st.session_state.get("_notif_paste_last", "")
        not_found = []
        if paste_raw.strip() and paste_raw.strip() != last.strip():
            tokens = list(dict.fromkeys(
                t.strip() for t in
                paste_raw.replace(",", "\n").replace(";", "\n").splitlines()
                if t.strip()
            ))
            umap  = {c.upper(): c for c in clientes_lista if c and isinstance(c, str)}
            found = []
            for tok in tokens:
                m = umap.get(tok.upper())
                if m: found.append(m)
                else: not_found.append(tok)
            if found:
                existing = st.session_state.get("_notif_sel_store", [])
                st.session_state["_notif_sel_store"] = list(dict.fromkeys(existing + found))
            # Auto-clear paste area after processing
            st.session_state["_notif_paste_store"]  = ""
            st.session_state["_notif_paste_last"]   = ""
            st.session_state["_notif_paste_cleared"] = True  # clears widget key next render
            st.rerun()
        elif paste_raw.strip():
            tokens    = list(dict.fromkeys(t.strip() for t in paste_raw.replace(",","\n").replace(";","\n").splitlines() if t.strip()))
            umap      = {c.upper(): c for c in clientes_lista if c and isinstance(c, str)}
            not_found = [t for t in tokens if not umap.get(t.upper())]

        if not_found:
            st.warning("⚠️ No encontrados: " + ", ".join(f"**{n}**" for n in not_found))

        # Streamlit ignores default= after first render.
        # Writing to the widget key before rendering sets the value on every rerun.
        # on_change keeps the store synced when user manually adds/removes.
        _clean_store = [c for c in st.session_state.get("_notif_sel_store", []) if c is not None]
        st.session_state["_notif_sel_store"] = _clean_store
        st.session_state["notif_clientes_sel"] = _clean_store

        sel = st.multiselect(
            "Clientes seleccionados:", options=clientes_lista,
            key="notif_clientes_sel",
            on_change=lambda: st.session_state.update(
                {"_notif_sel_store": st.session_state.get("notif_clientes_sel", [])}
            ),
        )
        st.session_state["_notif_sel_store"] = sel
        if sel:
            st.caption(f"✅ {len(sel)} cliente(s) seleccionado(s).")
    return sel


# ──────────────────────────────────────────────────────────
# Inline ventana fields  (returns dict or None)
# ──────────────────────────────────────────────────────────
def _ventana_fields(cliente: str):
    """Renders ventana fields for a fixed client. Returns (vms_sel, datos) or (None, None)."""
    df_vms = obtener_vms_disponibles(cliente)
    if df_vms.empty:
        st.success("✅ Este cliente no tiene VMs pendientes de agendar.")
        return None, None

    with section_card("🖥️ Máquinas Virtuales"):
        vms_sel = st.multiselect("VMs a agendar:", df_vms[COL_VM].tolist(), key="nv_vms")

    if not vms_sel:
        st.caption("Selecciona al menos una VM para continuar.")
        return None, None

    st.dataframe(df_vms[df_vms[COL_VM].isin(vms_sel)], use_container_width=True, hide_index=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Complejidad del cliente (guardada como Criticidad en BD) ──
    CRIT_DESC = {
        "Alta":  ("🟠", "Requiere coordinación especial"),
        "Media": ("🟡", "Confirma horarios pero presenta situaciones especiales"),
        "Baja":  ("🟢", "Confirma horario y sin novedades"),
    }
    with section_card("🕒 Configuración de Horario"):
        st.markdown(
            '<div style="font-size:.7rem;font-weight:800;letter-spacing:.08em;'
            'text-transform:uppercase;color:#FF7800;margin-bottom:8px;">'
            '⚙️ Complejidad del cliente</div>',
            unsafe_allow_html=True)
        crit_html = '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;">'
        for nv, (ic, dc) in CRIT_DESC.items():
            crit_html += (f'<div style="flex:1;min-width:130px;background:#F9FAFB;border:1.5px solid #E2E6ED;'
                          f'border-radius:10px;padding:9px 11px;">'
                          f'<div style="font-size:.8rem;font-weight:800;">{ic} {nv}</div>'
                          f'<div style="font-size:.7rem;color:#4A5568;line-height:1.4;">{dc}</div></div>')
        crit_html += '</div>'
        st.markdown(crit_html, unsafe_allow_html=True)

        criticidad  = st.selectbox("Complejidad:", list(CRIT_DESC.keys()), key="nv_criticidad", label_visibility="collapsed")
        motivo_crit = st.text_input("Razón / observación:", key="nv_motivo")
        st.markdown("<br>", unsafe_allow_html=True)

        tipo_ventana = st.radio("Tipo de Ventana:", ["Rango de Horario", "Horario Específico", "Horario Semi-específico"],
                                horizontal=True, key="nv_tipo")
        st.markdown("<br>", unsafe_allow_html=True)

        start_val = end_val = sem_val = dia_val = turn_val = None
        _errors = []

        if tipo_ventana == "Rango de Horario":
            c1, c2, c3 = st.columns(3, gap="large")
            with c1: sem_val  = st.multiselect("Semanas:", SEMANAS, key="nv_sem")
            with c2: dia_val  = st.multiselect("Días:",    DIAS,    key="nv_dia")
            with c3: turn_val = st.selectbox("Turno:", ["Mañana (6AM a 2PM)", "Tarde (2PM a 10PM)", "Noche (10PM a 6AM)"], key="nv_turno")
            if not sem_val: _errors.append("Selecciona al menos una semana.")
            if not dia_val: _errors.append("Selecciona al menos un día.")

        elif tipo_ventana == "Horario Específico":
            import datetime as _dtv
            c1, c2 = st.columns(2, gap="large")
            with c1:
                st.markdown('<div style="background:#F0FFF4;border:1.5px solid #9AE6B4;border-radius:10px;padding:10px 12px;margin-bottom:4px;"><div style="font-size:.68rem;font-weight:800;color:#276749;margin-bottom:6px;">📅 Inicio de Ventana</div>', unsafe_allow_html=True)
                d_i = st.date_input("Fecha Inicio", key="nv_di", label_visibility="collapsed")
                t_i = st.time_input("Hora Inicio",  key="nv_ti", label_visibility="collapsed")
                st.markdown("</div>", unsafe_allow_html=True)
            with c2:
                st.markdown('<div style="background:#FFF5F5;border:1.5px solid #FC8181;border-radius:10px;padding:10px 12px;margin-bottom:4px;"><div style="font-size:.68rem;font-weight:800;color:#9B2C2C;margin-bottom:6px;">🏁 Fin de Ventana</div>', unsafe_allow_html=True)
                d_f = st.date_input("Fecha Fin",    key="nv_df", label_visibility="collapsed")
                t_f = st.time_input("Hora Fin",     key="nv_tf", label_visibility="collapsed")
                st.markdown("</div>", unsafe_allow_html=True)
            start_val = f"{d_i} {t_i}"
            end_val   = f"{d_f} {t_f}"
            # Validation: end must be after start
            try:
                dt_s = _dtv.datetime.combine(d_i, t_i)
                dt_e = _dtv.datetime.combine(d_f, t_f)
                if dt_e <= dt_s:
                    _errors.append("⚠️ La fecha/hora de fin debe ser posterior al inicio.")
                else:
                    dur = dt_e - dt_s
                    h, m = divmod(int(dur.total_seconds()), 3600)
                    st.markdown(
                        f'<div style="background:#EBF8FF;border:1px solid #90CDF4;border-radius:8px;'
                        f'padding:8px 14px;font-size:.78rem;color:#2B6CB0;font-weight:600;margin-top:6px;">'
                        f'⏱ {h}h {m//60}min &nbsp;·&nbsp; '
                        f'{d_i.strftime("%d/%m/%Y")} {t_i.strftime("%H:%M")} → '
                        f'{d_f.strftime("%d/%m/%Y")} {t_f.strftime("%H:%M")}</div>',
                        unsafe_allow_html=True)
            except Exception:
                pass

        else:  # Horario Semi-específico
            import datetime as _dtv
            c1, c2, c3 = st.columns(3, gap="large")
            with c1: sem_val = st.multiselect("Semanas:", SEMANAS, key="nv_sem2")
            with c2: dia_val = st.multiselect("Días:",    DIAS,    key="nv_dia2")
            with c3:
                t_is = st.time_input("🕐 Hora Inicio", key="nv_tis")
                t_fs = st.time_input("🕐 Hora Fin",    key="nv_tfs")
            start_val, end_val = str(t_is), str(t_fs)
            if not sem_val: _errors.append("Selecciona al menos una semana.")
            if not dia_val: _errors.append("Selecciona al menos un día.")
            try:
                if _dtv.datetime.combine(_dtv.date.today(), t_fs) <= _dtv.datetime.combine(_dtv.date.today(), t_is):
                    _errors.append("⚠️ La hora de fin debe ser posterior a la hora de inicio.")
            except Exception:
                pass

        for err in _errors:
            st.warning(err)

    col_a, col_b = st.columns(2, gap="large")
    with col_a:
        with section_card("📝 Detalles Técnicos"):
            apps_lista  = chip_input("Aplicaciones y Servicios:", "nv_apps_chips")
            st.markdown("<br>", unsafe_allow_html=True)
            comentarios = st.text_area("Comentarios Finales:", key="nv_comentarios", height=100)
    with col_b:
        with section_card("📋 Información General"):
            en_uso = st.selectbox("¿VM(s) en uso actualmente?", ["Si", "No"], key="nv_en_uso")
            amb_html = ""
            for ak, (titulo, desc, _) in DESC_AMBIENTES.items():
                COLOR  = {"PRODUCCIÓN (PROD)": "#FFF5F5", "DESARROLLO (DEV)": "#F0FFF4", "CALIDAD (QA)": "#FEFCBF"}
                BORDER = {"PRODUCCIÓN (PROD)": "#FC8181", "DESARROLLO (DEV)": "#68D391", "CALIDAD (QA)": "#F6E05E"}
                bg = COLOR.get(ak,"#F9FAFB"); br = BORDER.get(ak,"#CBD5E0")
                amb_html += (f'<div style="background:{bg};border:1.5px solid {br};border-radius:8px;'
                             f'padding:6px 10px;margin-bottom:5px;">'
                             f'<span style="font-size:.75rem;font-weight:800;">{titulo}</span> '
                             f'<span style="font-size:.7rem;color:#4A5568;">— {desc}</span></div>')
            st.markdown(amb_html, unsafe_allow_html=True)
            ambiente = st.selectbox("Ambiente:", list(DESC_AMBIENTES.keys()), key="nv_ambiente")

    datos = {
        "en_uso": en_uso, "ambiente": ambiente,
        "descripcion": DESC_AMBIENTES[ambiente][1],
        "apps": ", ".join(apps_lista), "tipo_ventana": tipo_ventana,
        "StartDateTime": start_val, "EndDateTime": end_val,
        "turno_rango": turn_val,
        "semanas_rango": ",".join(sem_val) if sem_val else None,
        "Días_Rango": ",".join(dia_val) if dia_val else None,
        "criticidad": criticidad, "motivo_criticidad": motivo_crit,
        "comentarios": comentarios,
    }
    return (None, None) if _errors else (vms_sel, datos)


# ──────────────────────────────────────────────────────────
# Main render
# ──────────────────────────────────────────────────────────
def render():
    st.markdown("## 📢 Registro de Notificaciones a Clientes")

    clientes_lista = _clientes_directorio()
    clientes_sel   = _cliente_selector(clientes_lista)

    st.markdown("---")
    st.markdown("### 📋 Registro de la Notificación")

    if clientes_sel:
        st.markdown(
            f'<div style="background:#F0FFF4;border:1px solid #9AE6B4;border-radius:8px;'
            f'padding:8px 14px;margin-bottom:12px;font-size:.8rem;color:#22543D;font-weight:600;">'
            f'✅ {len(clientes_sel)} cliente(s): '
            + ", ".join(str(c) for c in clientes_sel[:5] if c is not None)
            + (f" … y {len(clientes_sel)-5} más" if len(clientes_sel) > 5 else "")
            + "</div>", unsafe_allow_html=True)
    else:
        st.info("ℹ️ Selecciona clientes arriba antes de registrar.")

    col_campos, col_ayuda = st.columns([1.5, 1])

    with col_campos:
        cc1, cc2 = st.columns(2)
        with cc1:
            _team = _team_migracion()
            if _team:
                creado_por = st.selectbox("👤 Ingeniero / Registrado por:", _team, key="notif_creado_por")
            else:
                creado_por = st.text_input("👤 Ingeniero / Registrado por:", key="notif_creado_por",
                                           placeholder="(sin datos en TEAM_MIGRACION)")

            # Canal — cambiar resetea el estado seleccionado
            prev_canal = st.session_state.get("_notif_canal_prev", "Email")
            canal = st.selectbox(
                "📡 Canal:",
                list(ESTADOS_POR_CANAL.keys()),
                key="notif_canal",
            )
            # Si canal cambió, resetear estado guardado
            if canal != prev_canal:
                st.session_state["_notif_canal_prev"] = canal
                # Always land on "Sin Respuesta" when switching canal
                opciones_nuevo = ESTADOS_POR_CANAL.get(canal, [])
                sin_resp_idx = opciones_nuevo.index("Sin Respuesta") if "Sin Respuesta" in opciones_nuevo else 0
                st.session_state["_notif_estado_idx"] = sin_resp_idx
                st.rerun()

        with cc2:
            st.markdown('<div style="font-size:.72rem;font-weight:700;color:#4A5568;margin-top:4px;margin-bottom:4px;">📌 Estado de Notificación:</div>', unsafe_allow_html=True)
            opciones_estado = ESTADOS_POR_CANAL[canal]
            estado = st.selectbox(
                "Estado:", opciones_estado,
                index=min(st.session_state.get("_notif_estado_idx", 0), len(opciones_estado)-1),
                key="notif_estado",
                label_visibility="collapsed",
                on_change=lambda: st.session_state.update(
                    {"_notif_estado_idx": opciones_estado.index(st.session_state.get("notif_estado", opciones_estado[0]))
                     if st.session_state.get("notif_estado") in opciones_estado else 0}
                ),
            )

        notas = st.text_area("📝 Notas / Asunto / Observaciones:", key="notif_notas", height=90)

    with col_ayuda:
        st.markdown("<br>", unsafe_allow_html=True)
        st.info(
            "**📨 Email:** Correo Enviado · Correo Rebotado · "
            "Cliente por Contactar · Agenda Confirmada · Sin Respuesta\n\n"
            "**📞 Contacto Directo:** Cliente por Contactar · "
            "Agenda Confirmada · Sin Respuesta"
        )

    # ── Agenda Confirmada: mostrar ventana inline ─────────
    is_agenda = estado == "Agenda Confirmada"
    vms_sel_ventana = None
    datos_ventana   = None

    if is_agenda:
        if len(clientes_sel) != 1:
            st.warning("⚠️ **Agenda Confirmada** requiere seleccionar **exactamente un cliente**.")
        else:
            st.markdown("---")
            st.markdown(
                f'<div style="background:#EBF8FF;border:1.5px solid #90CDF4;border-radius:10px;'
                f'padding:12px 16px;margin-bottom:14px;font-size:.85rem;color:#2B6CB0;font-weight:600;">'
                f'🗓️ Ventana confirmada con <strong>{clientes_sel[0]}</strong> — '
                f'Completa los campos para registrarla junto con la notificación.</div>',
                unsafe_allow_html=True)
            vms_sel_ventana, datos_ventana = _ventana_fields(clientes_sel[0])

    # ── Botón único de registro ───────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)

    btn_label = "🚀 Registrar Notificación y Ventana" if (is_agenda and datos_ventana) else "🚀 Registrar Notificación"
    btn_disabled = is_agenda and len(clientes_sel) != 1

    if not btn_disabled:
        if st.button(btn_label, key="notif_submit", type="primary", use_container_width=True):
            # Validations
            if not clientes_sel:
                st.error("Selecciona al menos un cliente.")
            elif not creado_por.strip():
                st.error("Indica quién registra la notificación.")
            elif is_agenda and (not vms_sel_ventana or datos_ventana is None):
                st.error("Selecciona al menos una VM para registrar la ventana.")
            else:
                ok_notif = guardar_notificaciones_masivas(
                    clientes_sel, creado_por.strip(), estado, canal, "1", notas.strip()
                )
                ok_ventana = True
                if is_agenda and vms_sel_ventana and datos_ventana:
                    ok_ventana = guardar_ventana_mantenimiento(clientes_sel[0], vms_sel_ventana, datos_ventana)

                if ok_notif and ok_ventana:
                    msg = f"✅ Notificación registrada para {len(clientes_sel)} cliente(s)."
                    if is_agenda:
                        msg += f" + Ventana guardada para {len(vms_sel_ventana)} VM(s)."
                    st.success(msg)
                    # Clear state
                    for k in ["_notif_sel_store", "_notif_paste_store", "_notif_paste_last",
                              "_notif_canal_prev", "_notif_estado_idx"]:
                        st.session_state.pop(k, None)
                    st.session_state.get("nv_apps_chips", None) and st.session_state.update({"nv_apps_chips": []})
                    st.balloons()
                    st.rerun()
                elif not ok_notif:
                    st.error("❌ Error al guardar la notificación.")
                elif not ok_ventana:
                    st.error("❌ Notificación guardada pero error en la ventana.")