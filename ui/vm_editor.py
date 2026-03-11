"""
ui/vm_editor.py
Widget to edit a VM's agendamiento record in the VMs table.
Completely separate from ESTADO_VMS — this only touches VMs.
"""

import sqlite3
import streamlit as st
import pandas as pd

from ui.db_utils import build_column_map, DB_PATH

DIAS    = ["Lunes","Martes","Miercoles","Jueves","Viernes","Sabado","Domingo"]
SEMANAS = ["1","2","3","4"]
TIPOS   = ["Horario Específico","Rango de Horario","Horario Semi-específico"]
TURNOS  = ["Mañana (6AM a 2PM)","Tarde (2PM a 10PM)","Noche (10PM a 6AM)"]


def _vms_for_client(cliente: str) -> list:
    cm      = build_column_map()
    col_vm  = cm.get("vm_id","VM_ID_TM")
    col_cli = cm.get("cliente","Cliente")
    conn    = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            f'SELECT "{col_vm}" FROM VMs WHERE "{col_cli}"=? ORDER BY "{col_vm}"',
            conn, params=(cliente,))
        return df[col_vm].tolist() if not df.empty else []
    except Exception:
        return []
    finally:
        conn.close()


def _load_vm_row(vm_id: str) -> pd.Series:
    cm     = build_column_map()
    col_vm = cm.get("vm_id","VM_ID_TM")
    conn   = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(f'SELECT * FROM VMs WHERE "{col_vm}"=?',
                               conn, params=(vm_id,))
        return df.iloc[0] if not df.empty else pd.Series(dtype=object)
    except:
        return pd.Series(dtype=object)
    finally:
        conn.close()


def _save_vm_row(original_vm_id: str, fields: dict) -> tuple[bool, str]:
    """
    Updates VMs table with new field values.
    original_vm_id is the WHERE key — if VM_ID_TM itself changes,
    we also cascade to ESTADO_VMS.
    """
    cm     = build_column_map()
    col_vm = cm.get("vm_id","VM_ID_TM")

    set_clauses = ", ".join(f'"{k}"=?' for k in fields)
    values      = list(fields.values()) + [original_vm_id]

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(f'UPDATE VMs SET {set_clauses} WHERE "{col_vm}"=?', values)

        # If VM_ID_TM itself changed, cascade to ESTADO_VMS
        new_id = fields.get(col_vm)
        if new_id and new_id != original_vm_id:
            try:
                conn.execute(
                    'UPDATE ESTADO_VMS SET "VM_ID_TM"=? WHERE "VM_ID_TM"=?',
                    (new_id, original_vm_id)
                )
            except Exception:
                pass  # ESTADO_VMS may not exist yet

        conn.commit()
        conn.close()
        return True, ""
    except Exception as e:
        return False, str(e)


def _g(row: pd.Series, col, default=""):
    if col is None or col not in row.index:
        return default
    v = str(row[col])
    return default if v in ("nan","None","","<NA>") else v


def _load_pending_vms_for_client(cliente: str) -> list:
    """Returns VM IDs with estado Agendado, Pendiente, or no ESTADO_VMS record."""
    cm     = build_column_map()
    col_vm = cm.get("vm_id","VM_ID_TM")
    col_cli = cm.get("cliente","Cliente")
    conn   = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(f"""
            SELECT v."{col_vm}" AS vm_id,
                   COALESCE(e.Estado_Migracion, 'Sin estado') AS estado
            FROM VMs v
            LEFT JOIN ESTADO_VMS e ON v."{col_vm}" = e."{col_vm}"
            WHERE v."{col_cli}" = ?
              AND (e.Estado_Migracion IS NULL
                   OR e.Estado_Migracion IN ('Agendado','Pendiente'))
            ORDER BY v.rowid
        """, conn, params=(cliente,))
        return df.to_dict("records") if not df.empty else []
    except Exception:
        return []
    finally:
        conn.close()


def _load_all_clients() -> list:
    cm     = build_column_map()
    col_cli = cm.get("cliente","Cliente")
    conn   = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            f'SELECT DISTINCT "{col_cli}" FROM VMs ORDER BY "{col_cli}"', conn)
        return df[col_cli].tolist()
    except Exception:
        return []
    finally:
        conn.close()


ESTADO_BADGE = {
    "Agendado":  ("🔵","#3182CE"),
    "Pendiente": ("⏳","#D69E2E"),
    "Sin estado":("⚪","#8A95A3"),
}


def render_vm_selector_and_editor(key_suffix: str = "vm_sel"):
    """
    Full self-contained widget:
    1. Select client
    2. Shows VMs with estado Agendado / Pendiente / Sin estado
    3. Select VM → opens editor
    Useful when you don't have a vm_id in hand yet.
    """
    clientes = _load_all_clients()
    if not clientes:
        st.info("No hay VMs registradas en la tabla VMs.")
        return

    c1, c2 = st.columns([2, 3])
    with c1:
        cliente_sel = st.selectbox(
            "Cliente:",
            ["— Seleccione —"] + clientes,
            key=f"vmed_cli_{key_suffix}",
        )

    if not cliente_sel or cliente_sel == "— Seleccione —":
        return

    vms = _load_pending_vms_for_client(cliente_sel)

    if not vms:
        st.success(f"✅ **{cliente_sel}** no tiene VMs Sin Agendar o sin estado.")
        return

    with c2:
        vm_opts  = [v["vm_id"] for v in vms]
        vm_label = {v["vm_id"]: v["estado"] for v in vms}
        vm_sel   = st.selectbox(
            f"VM ({len(vms)} Sin Agendar):",
            vm_opts,
            key=f"vmed_vm_{key_suffix}",
        )

    if not vm_sel:
        return

    # Badge for selected VM state
    est  = vm_label.get(vm_sel,"Sin estado")
    icon, color = ESTADO_BADGE.get(est, ("⚪","#8A95A3"))
    st.markdown(
        f'<div style="margin:8px 0 4px;">'
        f'<span style="background:{color};color:#fff;padding:2px 12px;'
        f'border-radius:20px;font-size:.74rem;font-weight:700;">'
        f'{icon} {est}</span></div>',
        unsafe_allow_html=True,
    )

    render_vm_editor(vm_sel, key_suffix=key_suffix, cliente=cliente_sel)


def render_vm_editor(vm_id: str, key_suffix: str = "", cliente: str = ""):
    """
    Renders an inline editor for all agendamiento fields of a VM.
    Only edits the VMs table — ESTADO_VMS is handled by status_widget.
    key_suffix: unique string per call site to avoid key collisions.
    """
    cm = build_column_map()
    row = _load_vm_row(vm_id)

    if row.empty:
        st.warning(f"No se encontró registro en VMs para: **{vm_id}**")
        return

    # ── Warning banner ────────────────────────────────────
    st.markdown("""
    <div style="background:#FFFBEB;border:1.5px solid #F6AD55;border-radius:10px;
         padding:10px 16px;margin-bottom:14px;display:flex;gap:10px;align-items:center;">
      <span style="font-size:1.2rem;">⚠️</span>
      <span style="font-size:.78rem;font-weight:600;color:#744210;">
        Estás editando los datos de agendamiento en la tabla <b>VMs</b>.
        Los cambios de estado/fechas se gestionan en la sección de estado de migración.
      </span>
    </div>""", unsafe_allow_html=True)

    k = f"{vm_id}_{key_suffix}"

    col_vm  = cm.get("vm_id","VM_ID_TM")
    col_cli = cm.get("cliente","Cliente")

    # ── Row 1: Identidad ──────────────────────────────────
    st.markdown('<div style="font-size:.7rem;font-weight:800;letter-spacing:.09em;'
                'text-transform:uppercase;color:#FF7800;margin:8px 0 10px;">🏷️ Identidad</div>',
                unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        # Cliente: pre-filled from selector, editable
        cur_cli = cliente or _g(row, col_cli)
        new_cli = st.text_input("Cliente", value=cur_cli, key=f"ed_cli_{k}")

    with c2:
        # VM ID: selectbox of all VMs for this client
        vm_options = _vms_for_client(new_cli) if new_cli else [vm_id]
        if vm_id not in vm_options:
            vm_options = [vm_id] + vm_options
        vm_idx    = vm_options.index(vm_id) if vm_id in vm_options else 0
        new_vm_id = st.selectbox("VM ID", vm_options, index=vm_idx, key=f"ed_vmid_{k}")

        # If VM changed, reload row
        if new_vm_id != vm_id:
            row = _load_vm_row(new_vm_id)
            vm_id = new_vm_id

    # ── Row 2: Clasificación ─────────────────────────────
    st.markdown('<div style="font-size:.7rem;font-weight:800;letter-spacing:.09em;'
                'text-transform:uppercase;color:#FF7800;margin:12px 0 10px;">📋 Clasificación</div>',
                unsafe_allow_html=True)

    col_amb  = cm.get("ambiente","Ambiente")
    col_crit = cm.get("criticidad","Criticidad")
    col_uso  = cm.get("en_uso","En_Uso")
    col_mot  = cm.get("motivo_criticidad","Motivo_Criticidad")

    AMBIENTES  = ["PROD","DEV","QA"]
    CRITS      = ["Critico","Alta","Media","Baja"]

    c1, c2, c3 = st.columns(3)
    with c1:
        cur_amb = _g(row, col_amb)
        amb_idx = AMBIENTES.index(cur_amb) if cur_amb in AMBIENTES else 0
        new_amb = st.selectbox("Ambiente", AMBIENTES, index=amb_idx, key=f"ed_amb_{k}")
    with c2:
        cur_crit = _g(row, col_crit)
        crit_idx = CRITS.index(cur_crit) if cur_crit in CRITS else 0
        new_crit = st.selectbox("Criticidad", CRITS, index=crit_idx, key=f"ed_crit_{k}")
    with c3:
        cur_uso = _g(row, col_uso)
        uso_opts = ["Si","No"]
        uso_idx  = uso_opts.index(cur_uso) if cur_uso in uso_opts else 0
        new_uso  = st.selectbox("En Uso", uso_opts, index=uso_idx, key=f"ed_uso_{k}")

    new_motivo = st.text_input("Motivo Criticidad", value=_g(row, col_mot),
                                key=f"ed_mot_{k}")

    # ── Row 3: Horario ────────────────────────────────────
    st.markdown('<div style="font-size:.7rem;font-weight:800;letter-spacing:.09em;'
                'text-transform:uppercase;color:#FF7800;margin:12px 0 10px;">🕒 Ventana de Mantenimiento</div>',
                unsafe_allow_html=True)

    col_tipo = cm.get("tipo_ventana","Tipo_Ventana")
    col_s    = cm.get("start_dt","StartDateTime")
    col_e    = cm.get("end_dt","EndDateTime")
    col_sem  = cm.get("semanas_rango","Semanas_Rango")
    col_dia  = cm.get("dias_rango","Días_Rango")
    col_turn = cm.get("turno_rango","Turno_Rango")

    cur_tipo = _g(row, col_tipo)
    tipo_idx = TIPOS.index(cur_tipo) if cur_tipo in TIPOS else 0
    new_tipo = st.selectbox("Tipo de Ventana", TIPOS, index=tipo_idx, key=f"ed_tipo_{k}")

    new_start = new_end = new_sem = new_dia = new_turn = ""

    if new_tipo == "Horario Específico":
        c1, c2 = st.columns(2)
        with c1:
            new_start = st.text_input("Inicio (YYYY-MM-DD HH:MM:SS)",
                                       value=_g(row, col_s), key=f"ed_s_{k}")
        with c2:
            new_end   = st.text_input("Fin (YYYY-MM-DD HH:MM:SS)",
                                       value=_g(row, col_e), key=f"ed_e_{k}")

    elif new_tipo == "Rango de Horario":
        cur_sems = _g(row, col_sem, "").split(",")
        cur_dias = _g(row, col_dia, "").split(",")
        cur_turn = _g(row, col_turn, "Mañana (6AM a 2PM)")
        c1, c2, c3 = st.columns(3)
        with c1:
            sel_sem  = st.multiselect("Semanas", SEMANAS,
                                       default=[s for s in cur_sems if s in SEMANAS],
                                       key=f"ed_sem_{k}")
        with c2:
            sel_dia  = st.multiselect("Días", DIAS,
                                       default=[d for d in cur_dias if d in DIAS],
                                       key=f"ed_dia_{k}")
        with c3:
            turn_idx = TURNOS.index(cur_turn) if cur_turn in TURNOS else 0
            sel_turn = st.selectbox("Turno", TURNOS, index=turn_idx, key=f"ed_turn_{k}")
        new_sem  = ",".join(sel_sem)
        new_dia  = ",".join(sel_dia)
        new_turn = sel_turn

    elif new_tipo == "Horario Semi-específico":
        cur_sems = _g(row, col_sem, "").split(",")
        cur_dias = _g(row, col_dia, "").split(",")
        c1, c2, c3 = st.columns(3)
        with c1:
            sel_sem = st.multiselect("Semanas", SEMANAS,
                                      default=[s for s in cur_sems if s in SEMANAS],
                                      key=f"ed_sem2_{k}")
        with c2:
            sel_dia = st.multiselect("Días", DIAS,
                                      default=[d for d in cur_dias if d in DIAS],
                                      key=f"ed_dia2_{k}")
        with c3:
            new_start = st.text_input("Hora inicio (HH:MM)", value=_g(row, col_s, "")[:5],
                                       key=f"ed_hs_{k}")
            new_end   = st.text_input("Hora fin (HH:MM)",    value=_g(row, col_e, "")[:5],
                                       key=f"ed_he_{k}")
        new_sem = ",".join(sel_sem)
        new_dia = ",".join(sel_dia)

    # ── Row 4: Apps / Comentarios ─────────────────────────
    st.markdown('<div style="font-size:.7rem;font-weight:800;letter-spacing:.09em;'
                'text-transform:uppercase;color:#FF7800;margin:12px 0 10px;">📝 Adicionales</div>',
                unsafe_allow_html=True)
    col_apps = cm.get("apps","Apps y Servicios")
    col_com  = cm.get("comentarios","Comentarios")

    c1, c2 = st.columns(2)
    with c1:
        new_apps = st.text_input("Apps y Servicios (separados por coma)",
                                  value=_g(row, col_apps), key=f"ed_apps_{k}")
    with c2:
        new_com  = st.text_area("Comentarios", value=_g(row, col_com),
                                 height=80, key=f"ed_com_{k}")

    # ── Save ──────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("💾 Guardar cambios en VMs", key=f"ed_save_{k}",
                 type="primary", use_container_width=True):

        # Warn if VM_ID changed
        if new_vm_id.strip() != vm_id:
            st.warning(f"⚠️ Vas a cambiar el VM ID de **{vm_id}** → **{new_vm_id.strip()}**. "
                       "El registro en ESTADO_VMS también será actualizado automáticamente.")

        fields = {
            col_vm:   new_vm_id.strip(),
            col_cli:  new_cli.strip(),
            col_amb:  new_amb,
            col_crit: new_crit,
            col_uso:  new_uso,
        }
        if col_mot: fields[col_mot] = new_motivo.strip()
        fields[col_tipo] = new_tipo
        if col_s:    fields[col_s]    = new_start
        if col_e:    fields[col_e]    = new_end
        if col_sem:  fields[col_sem]  = new_sem
        if col_dia:  fields[col_dia]  = new_dia
        if col_turn: fields[col_turn] = new_turn
        if col_apps: fields[col_apps] = new_apps.strip()
        if col_com:  fields[col_com]  = new_com.strip()

        ok, err = _save_vm_row(vm_id, fields)
        if ok:
            st.success("✅ Registro actualizado correctamente en la tabla VMs.")
            st.rerun()
        else:
            st.error(f"❌ Error al guardar: {err}")