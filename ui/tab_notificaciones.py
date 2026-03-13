"""
ui/tab_notificaciones.py
"""
import io
import sqlite3
from datetime import date
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
        "No Migrar"
    ],
    "Contacto Directo": [
        "Cliente por Contactar",
        "Agenda Confirmada",
        "Sin Respuesta",
        "No Migrar"
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
        if st.session_state.get("_notif_paste_cleared"):
            st.session_state["notif_paste"] = ""
            st.session_state["_notif_paste_cleared"] = False

        paste_raw = st.text_area(
            "Pegar:", value=st.session_state.get("_notif_paste_store", ""),
            key="notif_paste", height=80,
            placeholder="Pega aquí o escribe los clientes…",
            label_visibility="collapsed",
        )
        st.session_state["_notif_paste_store"] = paste_raw

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
            
            st.session_state["_notif_paste_store"]  = ""
            st.session_state["_notif_paste_last"]   = ""
            st.session_state["_notif_paste_cleared"] = True 
            st.rerun()
        elif paste_raw.strip():
            tokens    = list(dict.fromkeys(t.strip() for t in paste_raw.replace(",","\n").replace(";","\n").splitlines() if t.strip()))
            umap      = {c.upper(): c for c in clientes_lista if c and isinstance(c, str)}
            not_found = [t for t in tokens if not umap.get(t.upper())]

        if not_found:
            st.warning("⚠️ No encontrados: " + ", ".join(f"**{n}**" for n in not_found))

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
def _ventana_fields(cliente: str, key_prefix: str = "nv_"):
    """Renders ventana fields for a fixed client. Returns (vms_sel, datos) or (None, None).
    A key_prefix is used so we can reuse this component in New and Edit tabs without ID conflicts."""
    df_vms = obtener_vms_disponibles(cliente)
    if df_vms.empty:
        st.success("✅ Este cliente no tiene VMs pendientes de agendar.")
        return None, None

    with section_card("🖥️ Máquinas Virtuales"):
        vms_sel = st.multiselect("VMs a agendar:", df_vms[COL_VM].tolist(), key=f"{key_prefix}vms")

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

        criticidad  = st.selectbox("Complejidad:", list(CRIT_DESC.keys()), key=f"{key_prefix}criticidad", label_visibility="collapsed")
        motivo_crit = st.text_input("Razón / observación:", key=f"{key_prefix}motivo")
        st.markdown("<br>", unsafe_allow_html=True)

        # Variables globales para los datos a guardar
        start_val = end_val = sem_val = dia_val = turn_val = None
        _errors = []
        tipo_ventana = None
        mostrar_opciones_horario = True

        if criticidad == "Alta":
            st.info("ℹ️ Al indicar **Complejidad Alta**, el cliente se registrará como **Complejo** en el directorio. No es obligatorio agendar una ventana de mantenimiento.")
            mostrar_opciones_horario = st.toggle("Habilitar configuración de horario manual", value=False, key=f"{key_prefix}toggle_horario")
            if not mostrar_opciones_horario:
                tipo_ventana = "Cliente Complejo (Sin ventana)"

        if mostrar_opciones_horario:
            st.markdown('<div style="font-size:.75rem;font-weight:600;color:#4A5568;margin-bottom:8px;">Selecciona la modalidad de ventana:</div>', unsafe_allow_html=True)
            
            # Selector horizontal que simula pestañas pero retorna el valor automáticamente
            tipo_ventana_sel = st.radio(
                "Modalidad de ventana:", 
                ["📅 Rango de Horario", "🎯 Horario Específico"], 
                horizontal=True, 
                label_visibility="collapsed",
                key=f"{key_prefix}tipo_radio"
            )
            
            st.markdown("<hr style='margin:10px 0 20px 0;'>", unsafe_allow_html=True)

            if tipo_ventana_sel == "📅 Rango de Horario":
                tipo_ventana = "Rango de Horario"
                c1, c2, c3 = st.columns(3, gap="large")
                with c1: sem_val  = st.multiselect("Semanas:", SEMANAS, key=f"{key_prefix}sem_rng")
                with c2: dia_val  = st.multiselect("Días:",    DIAS,    key=f"{key_prefix}dia_rng")
                with c3: turn_val = st.selectbox("Turno:", ["Mañana (6AM a 2PM)", "Tarde (2PM a 10PM)", "Noche (10PM a 6AM)"], key=f"{key_prefix}turno_rng")
                
                if not sem_val: _errors.append("Selecciona al menos una semana.")
                if not dia_val: _errors.append("Selecciona al menos un día.")

            elif tipo_ventana_sel == "🎯 Horario Específico":
                tipo_ventana = "Horario Específico"
                es_fecha_exacta = st.toggle("🎯 Usar Fecha y Hora Exacta", value=False, key=f"{key_prefix}toggle_precision",
                                            help="Desactívalo para usar una hora fija dentro de un rango de días/semanas")
                st.markdown("<br>", unsafe_allow_html=True)

                import datetime as _dtv
                if es_fecha_exacta:
                    c1, c2 = st.columns(2, gap="large")
                    with c1:
                        st.markdown('<div style="background:#F0FFF4;border:1.5px solid #9AE6B4;border-radius:10px;padding:10px 12px;margin-bottom:4px;"><div style="font-size:.68rem;font-weight:800;color:#276749;margin-bottom:6px;">📅 Inicio de Ventana</div>', unsafe_allow_html=True)
                        d_i = st.date_input("Fecha Inicio", key=f"{key_prefix}di_esp", label_visibility="collapsed")
                        t_i = st.time_input("Hora Inicio",  key=f"{key_prefix}ti_esp", label_visibility="collapsed")
                        st.markdown("</div>", unsafe_allow_html=True)
                    with c2:
                        st.markdown('<div style="background:#FFF5F5;border:1.5px solid #FC8181;border-radius:10px;padding:10px 12px;margin-bottom:4px;"><div style="font-size:.68rem;font-weight:800;color:#9B2C2C;margin-bottom:6px;">🏁 Fin de Ventana</div>', unsafe_allow_html=True)
                        d_f = st.date_input("Fecha Fin",    key=f"{key_prefix}df_esp", label_visibility="collapsed")
                        t_f = st.time_input("Hora Fin",     key=f"{key_prefix}tf_esp", label_visibility="collapsed")
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                    start_val = f"{d_i} {t_i}"
                    end_val   = f"{d_f} {t_f}"
                    
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
                else:
                    c1, c2, c3 = st.columns(3, gap="large")
                    with c1: sem_val = st.multiselect("Semanas:", SEMANAS, key=f"{key_prefix}sem2_esp")
                    with c2: dia_val = st.multiselect("Días:",    DIAS,    key=f"{key_prefix}dia2_esp")
                    with c3:
                        t_is = st.time_input("🕐 Hora Inicio", key=f"{key_prefix}tis_esp")
                        t_fs = st.time_input("🕐 Hora Fin",    key=f"{key_prefix}tfs_esp")
                        
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
            apps_lista  = chip_input("Aplicaciones y Servicios:", f"{key_prefix}apps_chips")
            st.markdown("<br>", unsafe_allow_html=True)
            comentarios = st.text_area("Comentarios Finales:", key=f"{key_prefix}comentarios", height=100)
    with col_b:
        with section_card("📋 Información General"):
            en_uso = st.selectbox("¿VM(s) en uso actualmente?", ["Si", "No"], key=f"{key_prefix}en_uso")
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
            ambiente = st.selectbox("Ambiente:", list(DESC_AMBIENTES.keys()), key=f"{key_prefix}ambiente")

    # Mapeo de datos para envío
    datos = {
        "en_uso": en_uso, "ambiente": ambiente,
        "descripcion": DESC_AMBIENTES[ambiente][1] if ambiente in DESC_AMBIENTES else "",
        "apps": ", ".join(apps_lista), "tipo_ventana": tipo_ventana,
        "StartDateTime": start_val, "EndDateTime": end_val,
        "turno_rango": turn_val,
        "semanas_rango": ",".join(sem_val) if sem_val else None,
        "Días_Rango": ",".join(dia_val) if dia_val else None,
        "criticidad": criticidad, "motivo_criticidad": motivo_crit,
        "comentarios": comentarios,
        "Tipo_Cliente": "Complejo" if criticidad == "Alta" else "Normal"
    }
    
    return (None, None) if _errors else (vms_sel, datos)


# ──────────────────────────────────────────────────────────
# Notif editor
# ──────────────────────────────────────────────────────────
ESTADO_COLORS_NOTIF = {
    "Correo Enviado":        "#38A169",
    "Correo Rebotado":       "#E53E3E",
    "Cliente por Contactar": "#D69E2E",
    "Agenda Confirmada":     "#3182CE",
    "Sin Respuesta":         "#718096",
    "No Migrar":             "#1B0606",
}

def _badge_notif(estado: str) -> str:
    c = ESTADO_COLORS_NOTIF.get(estado, "#8A95A3")
    return (f'<span style="background:{c};color:#fff;padding:2px 10px;'
            f'border-radius:20px;font-size:.72rem;font-weight:700;">{estado}</span>')


def _update_notificacion(rowid: int, nuevo_estado: str, nuevo_canal: str,
                         nuevas_notas: str) -> tuple[bool, str]:
    try:
        conn = sqlite3.connect("migraciones.db")
        conn.execute(
            '''UPDATE NOTIFICACIONES_CLIENTES
               SET "Estado_Notificacion" = ?,
                   "Canal_Notificacion"  = ?,
                   "Notas"               = ?
               WHERE rowid = ?''',
            (nuevo_estado, nuevo_canal, nuevas_notas, rowid),
        )
        conn.commit()
        conn.close()
        return True, ""
    except Exception as e:
        return False, str(e)


def _load_notificaciones_cliente(cliente_filter: str = None) -> pd.DataFrame:
    conn = sqlite3.connect("migraciones.db")
    try:
        df = pd.read_sql_query(
            'SELECT rowid, * FROM NOTIFICACIONES_CLIENTES ORDER BY "Fecha Notificación" DESC', conn)
        if cliente_filter:
            df = df[df["Cliente"] == cliente_filter]
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


def _notif_editor():
    """Editor de notificaciones existentes. Soporta guardado de ventana en línea."""
    st.markdown("---")
    with section_card("✏️ Editar Notificación Existente"):
        st.markdown('''
        <div style="background:#EBF8FF;border:1.5px solid #90CDF4;border-radius:10px;
             padding:10px 16px;margin-bottom:14px;display:flex;gap:10px;align-items:center;">
          <span style="font-size:1.1rem;">ℹ️</span>
          <span style="font-size:.77rem;font-weight:600;color:#2A4365;">
            Modifica el estado de la notificación. Si elijes <b>Agenda Confirmada</b>, 
            podrás agendar la ventana aquí mismo.
          </span>
        </div>''', unsafe_allow_html=True)

        ec1, ec2 = st.columns([2, 3])
        with ec1:
            cli_filter = st.text_input("Buscar por cliente:", key="edit_notif_cli_filter",
                                        placeholder="Escribe para filtrar…")

        df_edit = _load_notificaciones_cliente(cli_filter.strip() if cli_filter.strip() else None)

        if df_edit.empty:
            st.info("No hay notificaciones registradas aún.")
            return

        def _label(row):
            fecha = str(row.get("Fecha Notificación",""))[:16]
            cli   = str(row.get("Cliente",""))
            est   = str(row.get("Estado_Notificacion",""))
            return f"{cli}  ·  {fecha}  ·  {est}"

        opciones = {_label(r): r for _, r in df_edit.iterrows()}
        sel_label = st.selectbox("Seleccionar notificación:", list(opciones.keys()),
                                  key="edit_notif_sel")
        if not sel_label:
            return

        row   = opciones[sel_label]
        rowid = int(row["rowid"]) if pd.notna(row.get("rowid")) else None
        cliente_edit = str(row.get("Cliente", ""))
        
        if rowid is None:
            st.warning("No se pudo identificar el registro.")
            return

        cur_estado = str(row.get("Estado_Notificacion", "Correo Enviado"))
        cur_canal  = str(row.get("Canal_Notificacion",  "Email"))
        cur_notas  = str(row.get("Notas", ""))
        if cur_notas in ("nan","None"): cur_notas = ""
        if cur_canal not in ESTADOS_POR_CANAL: cur_canal = "Email"

        st.markdown(
            f'<div style="margin:8px 0 14px;">Estado actual: {_badge_notif(cur_estado)}</div>',
            unsafe_allow_html=True)

        ec1, ec2 = st.columns(2)
        with ec2:
            canales = list(ESTADOS_POR_CANAL.keys())
            new_canal = st.selectbox("Canal:", canales,
                                      index=canales.index(cur_canal) if cur_canal in canales else 0,
                                      key="edit_notif_canal")
        with ec1:
            estados = ESTADOS_POR_CANAL[new_canal]
            new_estado = st.selectbox("Nuevo Estado:", estados,
                                       index=estados.index(cur_estado) if cur_estado in estados else 0,
                                       key="edit_notif_estado")

        new_notas = st.text_area("Notas / Observaciones:", value=cur_notas,
                                  height=80, key="edit_notif_notas",
                                  placeholder="Agrega detalles del seguimiento…")

        # ── Agenda Confirmada: ventana inline para Editar ─────────────────
        is_agenda = new_estado == "Agenda Confirmada"
        vms_sel_ventana = None
        datos_ventana   = None

        if is_agenda:
            st.markdown("---")
            st.markdown(
                f'<div style="background:#EBF8FF;border:1.5px solid #90CDF4;border-radius:10px;'
                f'padding:12px 16px;margin-bottom:14px;font-size:.85rem;color:#2B6CB0;font-weight:600;">'
                f'🗓️ Ventana confirmada con <strong>{cliente_edit}</strong> — '
                f'Completa los campos para agendar.</div>',
                unsafe_allow_html=True)
            # Pasamos "ev_" como prefijo (Edit Ventana) para que los IDs no colisionen
            vms_sel_ventana, datos_ventana = _ventana_fields(cliente_edit, key_prefix="ev_")

        st.markdown("<br>", unsafe_allow_html=True)
        btn_label = "🚀 Guardar Cambios y Ventana" if (is_agenda and datos_ventana) else "💾 Guardar cambios de Notificación"

        if st.button(btn_label, key="edit_notif_save", type="primary", use_container_width=True):
            if is_agenda and (not vms_sel_ventana or datos_ventana is None):
                st.error("Selecciona al menos una VM y completa los datos de la ventana.")
                return
            
            ok_notif, err = _update_notificacion(rowid, new_estado, new_canal, new_notas.strip())
            ok_ventana = True
            
            if ok_notif and is_agenda and vms_sel_ventana and datos_ventana:
                try:
                    conn = sqlite3.connect("migraciones.db")
                    if "Tipo_Cliente" in datos_ventana:
                        conn.execute(
                            'UPDATE DIRECTORIO_CLIENTE SET "Tipo_Cliente"=? WHERE "Cliente"=?',
                            (datos_ventana["Tipo_Cliente"], cliente_edit))
                        conn.commit()
                except Exception: pass
                finally: conn.close()
                ok_ventana = guardar_ventana_mantenimiento(cliente_edit, vms_sel_ventana, datos_ventana)

            if ok_notif and ok_ventana:
                msg = "✅ Notificación actualizada."
                if is_agenda: msg += f" + Ventana guardada para {len(vms_sel_ventana)} VM(s)."
                st.success(msg)
                # Limpiar cache de chips si existe
                if st.session_state.get("ev_apps_chips"): st.session_state["ev_apps_chips"] = []
                st.balloons()
                st.rerun()
            elif not ok_notif:
                st.error(f"❌ Error al guardar la notificación: {err}")
            else:
                st.error("❌ Notificación guardada pero hubo un error al agendar la ventana.")


# ──────────────────────────────────────────────────────────
# Main render
# ──────────────────────────────────────────────────────────
def _tab_nueva_notificacion(clientes_lista: list):
    """Contenido del tab 'Nueva Notificación'."""
    clientes_sel = _cliente_selector(clientes_lista)

    st.markdown("---")

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

            prev_canal = st.session_state.get("_notif_canal_prev", "Email")
            canal = st.selectbox("📡 Canal:", list(ESTADOS_POR_CANAL.keys()), key="notif_canal")
            if canal != prev_canal:
                st.session_state["_notif_canal_prev"] = canal
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
            "Agenda Confirmada\n\n"
            "**❌ No Migrar:** Indica que el cliente no será migrado, ya sea por decisión propia o por análisis técnico. No se agenda ventana."
        )

    # ── Agenda Confirmada: ventana inline para Nueva ─────────────────
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
            # Pasamos "nv_" como prefijo (New Ventana)
            vms_sel_ventana, datos_ventana = _ventana_fields(clientes_sel[0], key_prefix="nv_")

    # ── Botón ─────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    btn_label    = "🚀 Registrar Notificación y Ventana" if (is_agenda and datos_ventana) else "🚀 Registrar Notificación"
    btn_disabled = is_agenda and len(clientes_sel) != 1

    if not btn_disabled:
        if st.button(btn_label, key="notif_submit", type="primary", use_container_width=True):
            if not clientes_sel:
                st.error("Selecciona al menos un cliente.")
            elif not creado_por.strip():
                st.error("Indica quién registra la notificación.")
            elif is_agenda and (not vms_sel_ventana or datos_ventana is None):
                st.error("Selecciona al menos una VM para registrar la ventana o verifica los datos faltantes.")
            else:
                ok_notif  = guardar_notificaciones_masivas(
                    clientes_sel, creado_por.strip(), estado, canal, "1", notas.strip())
                ok_ventana = True
                
                if is_agenda and vms_sel_ventana and datos_ventana:
                    try:
                        conn = sqlite3.connect("migraciones.db")
                        if "Tipo_Cliente" in datos_ventana:
                            conn.execute(
                                'UPDATE DIRECTORIO_CLIENTE SET "Tipo_Cliente"=? WHERE "Cliente"=?',
                                (datos_ventana["Tipo_Cliente"], clientes_sel[0]))
                            conn.commit()
                    except Exception: pass
                    finally: conn.close()
                    ok_ventana = guardar_ventana_mantenimiento(clientes_sel[0], vms_sel_ventana, datos_ventana)

                if ok_notif and ok_ventana:
                    msg = f"✅ Notificación registrada para {len(clientes_sel)} cliente(s)."
                    if is_agenda:
                        msg += f" + Ventana guardada para {len(vms_sel_ventana)} VM(s)."
                    st.success(msg)
                    for k in ["_notif_sel_store","_notif_paste_store","_notif_paste_last",
                              "_notif_canal_prev","_notif_estado_idx"]:
                        st.session_state.pop(k, None)
                    if st.session_state.get("nv_apps_chips"):
                        st.session_state["nv_apps_chips"] = []
                    st.balloons()
                    st.rerun()
                elif not ok_notif:
                    st.error("❌ Error al guardar la notificación.")
                else:
                    st.error("❌ Notificación guardada pero error en la ventana.")


def _tab_editar_notificacion(clientes_lista: list):
    """Contenido del tab 'Editar Notificación'."""
    _notif_editor()


def render():
    st.markdown("## 📢 Notificaciones a Clientes")

    clientes_lista = _clientes_directorio()

    tab_nueva, tab_editar = st.tabs(["✉️ Nueva Notificación", "✏️ Editar Notificación"])

    with tab_nueva:
        _tab_nueva_notificacion(clientes_lista)

    with tab_editar:
        _tab_editar_notificacion(clientes_lista)