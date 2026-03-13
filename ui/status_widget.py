"""
ui/status_widget.py
Reusable widget to view and update VM migration status.
Used from both tab_calendar.py and tab_agendados.py.
"""

from datetime import date, datetime

import streamlit as st

from logic.update_status import VALID_STATES, get_vm_status, upsert_vm_status

STATE_META = {
    "Agendado":       {"color": "#3182CE", "icon": "🔵"},
    "Migrada OK":     {"color": "#38A169", "icon": "✅"},
    "Sin Agendar":    {"color": "#D69E2E", "icon": "⏳"},
    "Rollback Tras Seguimiento": {"color": "#E53E3E", "icon": "↩️"},
    "Rollback Inmediato":        {"color": "#C53030", "icon": "❌"},
    "En Seguimiento": {"color": "#805AD5", "icon": "🔍"},
}


def _badge(estado: str) -> str:
    m = STATE_META.get(estado, {"color": "#FF7800", "icon": "🟠"})
    return (f'<span style="background:{m["color"]};color:#fff;padding:3px 12px;'
            f'border-radius:20px;font-size:.75rem;font-weight:700;">'
            f'{m["icon"]} {estado}</span>')


def _time_picker(label: str, key: str, initial: str = "") -> str:
    """
    Digital time picker — styled hour/minute number inputs.
    Returns time as "HH:MM" string or "" if both are 0 and no initial.
    """
    try:
        init_h = int(initial[:2]) if len(initial) >= 5 else 0
        init_m = int(initial[3:5]) if len(initial) >= 5 else 0
    except:
        init_h, init_m = 0, 0

    st.markdown(f"""
    <div style="font-size:.78rem;font-weight:600;color:#4A5568;margin-bottom:6px;">{label}</div>
    <style>
      div[data-testid="stNumberInput"] input {{
        text-align:center;font-size:1.4rem;font-weight:800;
        background:#EEEAFF;border:none;border-radius:8px;
        color:#4C3D99;padding:8px 4px;
      }}
    </style>""", unsafe_allow_html=True)

    c1, sep, c2 = st.columns([2, 0.3, 2])
    with c1:
        h = st.number_input("H", min_value=0, max_value=23, value=init_h,
                            key=f"{key}_h", label_visibility="collapsed")
    with sep:
        st.markdown('<div style="font-size:1.6rem;font-weight:800;color:#4C3D99;'
                    'text-align:center;padding-top:6px;">:</div>', unsafe_allow_html=True)
    with c2:
        m = st.number_input("M", min_value=0, max_value=59, value=init_m,
                            key=f"{key}_m", label_visibility="collapsed")

    st.markdown(f'<div style="display:flex;gap:20px;font-size:.65rem;color:#8A95A3;'
                f'font-weight:600;margin-top:2px;">'
                f'<span style="flex:1;text-align:center;">HORA</span>'
                f'<span style="width:14px;"></span>'
                f'<span style="flex:1;text-align:center;">MINUTO</span></div>',
                unsafe_allow_html=True)

    return f"{int(h):02d}:{int(m):02d}"


def render_status_editor(
    vm_id: str,
    cliente: str,
    estado_actual: str,
    key_suffix: str = "",
    allowed_states: list | None = None,
):
    """
    Renders the migration status editor for a VM.

    allowed_states: if provided, restricts the selectbox to those states only.
      - Calendar context:     ["En Seguimiento", "Rollback Inmediato"]
      - Seguimiento context:  ["Migrada OK", "Rollback Tras Seguimiento"]
      - None → all VALID_STATES (existing behaviour)

    Mandatory Observaciones_Fallo for any Rollback state.
    key_suffix: unique string to avoid widget key collisions between tabs.
    """
    # Load existing record from ESTADO_VMS
    record = get_vm_status(vm_id)

    def _parse_dt(val) -> datetime | None:
        if not val or str(val) in ("nan", "None", ""):
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(val)[:19], fmt)
            except:
                pass
        return None

    cur_estado  = record.get("Estado_Migracion", estado_actual) or estado_actual
    cur_fej     = _parse_dt(record.get("Fecha_Ejecucion"))
    cur_ffin    = _parse_dt(record.get("Fecha_Finalizacion"))
    cur_obs     = record.get("Observaciones_Fallo") or ""
    if str(cur_obs) in ("nan", "None"): cur_obs = ""

    # ── Point 17: "Sin Agendar" is read-only ────────────
    if cur_estado == "Sin Agendar":
        st.markdown(
            f'<div style="background:#FFFBEB;border:1.5px solid #F6AD55;border-radius:12px;'
            f'padding:16px 20px;margin-top:16px;">' 
            f'<div style="font-size:.65rem;font-weight:800;letter-spacing:.09em;'
            f'text-transform:uppercase;color:#D69E2E;margin-bottom:10px;">⏳ Estado bloqueado</div>'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">' 
            + _badge("Sin Agendar") +
            f'</div><div style="font-size:.78rem;color:#744210;font-weight:500;">'
            f'Las VMs en estado <b>Sin Agendar</b> no pueden modificarse desde aquí. '
            f'Para cambiar el estado, primero agenda una ventana de mantenimiento '
            f'desde la pestaña <b>📢 Notificaciones Clientes</b>.</div></div>',
            unsafe_allow_html=True,
        )
        return

    # ── Header card ──────────────────────────────────────
    m = STATE_META.get(cur_estado, {"color": "#FF7800", "icon": "🟠"})
    st.markdown(f"""
    <div style="background:#fff;border:1.5px solid #E8ECF1;border-radius:12px;
         padding:16px 20px;margin-top:16px;box-shadow:0 1px 4px rgba(0,0,0,.05);">
      <div style="font-size:.65rem;font-weight:800;letter-spacing:.09em;
           text-transform:uppercase;color:#FF7800;margin-bottom:12px;">
        ✏️ Estado de Migración
      </div>
      <div style="display:flex;align-items:center;gap:10px;">
        <span style="font-size:.77rem;color:#8A95A3;font-weight:600;">Estado actual:</span>
        {_badge(cur_estado)}
      </div>
    </div>""", unsafe_allow_html=True)

    # ── Form fields ──────────────────────────────────────
    k = f"{vm_id}_{key_suffix}"

    _state_opts = allowed_states if allowed_states else VALID_STATES
    _def_idx    = _state_opts.index(cur_estado) if cur_estado in _state_opts else 0

    if allowed_states:
        st.markdown(
            f'<div style="background:#EBF8FF;border:1px solid #90CDF4;border-radius:8px;'
            f'padding:7px 12px;font-size:.73rem;color:#2B6CB0;margin-bottom:8px;">'
            f'🔒 Transiciones permitidas desde <b>{cur_estado}</b>: '
            + " · ".join(f"<b>{s}</b>" for s in allowed_states) +
            f'</div>',
            unsafe_allow_html=True)

    nuevo_estado = st.selectbox(
        "Nuevo estado:",
        _state_opts,
        index=_def_idx,
        key=f"sel_est_{k}",
    )

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        st.markdown('<div style="font-size:.8rem;font-weight:700;color:#4A5568;'
                    'margin-bottom:4px;">📅 Fecha de Ejecución</div>',
                    unsafe_allow_html=True)
        fej_date = st.date_input("Fecha ejec.",
                                  value=cur_fej.date() if cur_fej else None,
                                  key=f"fej_d_{k}", label_visibility="collapsed")
        fej_time_str = _time_picker("🕐 Hora de Ejecución",
                                     key=f"fej_t_{k}",
                                     initial=cur_fej.strftime("%H:%M") if cur_fej else "")

    with col_f2:
        st.markdown('<div style="font-size:.8rem;font-weight:700;color:#4A5568;'
                    'margin-bottom:4px;">📅 Fecha de Finalización</div>',
                    unsafe_allow_html=True)
        ffin_date = st.date_input("Fecha fin.",
                                   value=cur_ffin.date() if cur_ffin else None,
                                   key=f"ffin_d_{k}", label_visibility="collapsed")
        ffin_time_str = _time_picker("🕐 Hora de Finalización",
                                      key=f"ffin_t_{k}",
                                      initial=cur_ffin.strftime("%H:%M") if cur_ffin else "")

    # Observations — always visible but required label changes
    _is_rollback = nuevo_estado in ("Rollback Inmediato", "Rollback Tras Seguimiento")
    needs_obs    = _is_rollback or nuevo_estado == "En Seguimiento"
    obs_label    = ("⚠️ Motivo del Rollback (obligatorio)"
                    if _is_rollback else "📝 Observaciones")
    observaciones = st.text_area(
        obs_label,
        value=cur_obs,
        key=f"obs_{k}",
        height=90,
        placeholder="Describe lo ocurrido, pasos ejecutados, próximas acciones…",
    )

    # ── Save button ──────────────────────────────────────
    m_new = STATE_META.get(nuevo_estado, {"color": "#FF7800", "icon": "🟠"})
    if st.button(
        f"{m_new['icon']} Guardar estado: {nuevo_estado}",
        key=f"btn_save_{k}",
        type="primary",
        use_container_width=True,
    ):
        if _is_rollback and not observaciones.strip():
            st.warning("⚠️ El motivo del Rollback es obligatorio. Por favor descríbelo antes de guardar.")
            return

        fej_str  = f"{fej_date} {fej_time_str}:00"  if fej_date  else ""
        ffin_str = f"{ffin_date} {ffin_time_str}:00" if ffin_date else ""

        # Validate: end must not be before start
        if fej_str and ffin_str and ffin_str < fej_str:
            st.warning("⚠️ La fecha/hora de finalización no puede ser anterior a la de ejecución.")
            return

        ok, err = upsert_vm_status(
            vm_id, cliente, nuevo_estado, fej_str, ffin_str, observaciones.strip()
        )
        if ok:
            st.success(f"✅ Estado actualizado a **{nuevo_estado}** correctamente.")
            if nuevo_estado == "Migrada OK":
                st.balloons()
            st.rerun()
        else:
            st.error(f"❌ Error al guardar: {err}")