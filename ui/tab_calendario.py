"""
ui/tab_calendario.py — Calendario de ventanas de mantenimiento.
"""

import io
import sqlite3
from datetime import date, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from ui.calendar_utils import (
    MONTH_NAMES_ES, build_calendar_html, events_to_df,
    get_events_for_month, ESTADO_COLOR, DEFAULT_COLOR,
)
from ui.components import section_card
from ui.db_utils import build_column_map, safe_get, DB_PATH
from ui.status_widget import render_status_editor
from ui.vm_editor import render_vm_editor, render_vm_selector_and_editor

ESTADO_ICON = {
    "Agendado":"🔵","Éxito":"✅","Sin Agendar":"⏳",
    "RollBack":"↩️","Fallida":"❌","En Seguimiento":"🔍",
}
TURNO_DESC  = {"Mañana":"06:00–14:00","Tarde":"14:00–22:00","Noche":"22:00–06:00 (+1d)"}
AMB_COLORS  = {"PROD":"#E53E3E","DEV":"#38A169","QA":"#D69E2E"}


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _init():
    today = date.today()
    for k, v in {
        "cal_year":today.year,"cal_month":today.month,
        "cal_date":today,"cal_view":"📅 Calendario",
        "cal_client":"— Todos —","cal_vm":None,
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _set_date(d: date):
    """Cambia la fecha activa y actualiza año/mes."""
    st.session_state["cal_date"]  = d
    st.session_state["cal_year"]  = d.year
    st.session_state["cal_month"] = d.month


def _clientes() -> list:
    try:
        col  = build_column_map().get("cliente","Cliente")
        conn = sqlite3.connect(DB_PATH)
        df   = pd.read_sql_query(f'SELECT DISTINCT "{col}" FROM VMs ORDER BY "{col}"',conn)
        conn.close()
        return df[col].tolist()
    except:
        return []


# ─────────────────────────────────────────────────────────────
# VM Detail
# ─────────────────────────────────────────────────────────────
def _vm_detail(vm_id: str):
    cm     = build_column_map()
    col_vm = cm.get("vm_id","VM_ID_TM")

    if st.button("⬅  Volver al Calendario", key="back"):
        st.session_state["cal_vm"] = None
        st.rerun()

    # ── Load from VMs (schedule data) ────────────────────
    conn = sqlite3.connect(DB_PATH)
    try:
        df_vm = pd.read_sql_query(
            f'SELECT * FROM VMs WHERE "{col_vm}"=?', conn, params=(vm_id,))
    except Exception as e:
        st.error(str(e)); conn.close(); return

    # ── Load from DATABASE (infra data: IP, storage, OS…) ─
    try:
        df_db = pd.read_sql_query(
            f'SELECT * FROM DATABASE WHERE "{col_vm}"=?', conn, params=(vm_id,))
    except:
        df_db = pd.DataFrame()
    conn.close()

    if df_vm.empty and df_db.empty:
        st.warning(f"Sin registro para VM: **{vm_id}**"); return

    row_vm = df_vm.iloc[0] if not df_vm.empty else pd.Series(dtype=object)
    row_db = df_db.iloc[0] if not df_db.empty else pd.Series(dtype=object)

    def gv(role, default="—"):
        v = safe_get(row_vm, cm.get(role), default)
        return v if v and v not in ("nan","None","") else default

    def gd(col, default="—"):
        """Get from DATABASE row by actual column name."""
        if col not in row_db.index: return default
        v = str(row_db[col])
        return default if v in ("nan","None","","<NA>") else v

    tipo   = gv("tipo_ventana")
    estado = gv("estado","Sin Agendar")
    ecss   = ESTADO_COLOR.get(estado, DEFAULT_COLOR)
    eicon  = ESTADO_ICON.get(estado,"🟠")
    amb    = gv("ambiente")

    # ── Columnas exactas de la tabla DATABASE ────────────
    def _mib_to_gb(val: str) -> str:
        try:    return f"{int(val)/1024:.1f} GB"
        except: return val

    # ── Header ───────────────────────────────────────────
    st.markdown(f"""
    <div style="background:#fff;border-radius:14px;border-left:5px solid #FF7800;
        padding:18px 24px;margin-bottom:18px;box-shadow:0 2px 10px rgba(0,0,0,.07);
        display:flex;align-items:center;gap:16px;">
      <div style="font-size:2rem;">🖥️</div>
      <div>
        <div style="font-size:1.1rem;font-weight:800;color:#1E2330;">{vm_id}</div>
        <div style="font-size:.82rem;color:#8A95A3;margin-top:2px;">{gv('cliente')}</div>
      </div>
      <div style="margin-left:auto;">
        <span style="font-size:.8rem;font-weight:700;padding:5px 14px;
          border-radius:20px;background:{ecss};color:#fff;">{eicon} {estado}</span>
      </div>
    </div>""", unsafe_allow_html=True)

    def irow(label, value, color=None):
        vs = f"color:{color};font-weight:700;" if color else "color:#1E2330;font-weight:600;"
        return (f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:8px 0;border-bottom:1px solid #F4F5F7;">'
                f'<span style="font-size:.77rem;color:#8A95A3;font-weight:600;">{label}</span>'
                f'<span style="font-size:.82rem;{vs}">{value or "—"}</span></div>')

    def card(title, content_html):
        return (f'<div style="background:#fff;border-radius:12px;border:1px solid #E8ECF1;'
                f'padding:14px 16px;box-shadow:0 1px 4px rgba(0,0,0,.05);height:100%;">'
                f'<div style="font-size:.65rem;font-weight:800;letter-spacing:.09em;'
                f'text-transform:uppercase;color:#FF7800;margin-bottom:10px;">{title}</div>'
                f'{content_html}</div>')

    # ── Row 1: General + Infraestructura ────────────────
    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown(card("📋 Información General",
            irow("Ambiente",    amb, AMB_COLORS.get(amb))
            + irow("Criticidad",  gv("criticidad"))
            + irow("Motivo",      gv("motivo_criticidad"))
            + irow("En Uso",      gv("en_uso"))
        ), unsafe_allow_html=True)

    with col2:
        # RAM: columna "Memory" está en MB → convertir a GB
        def _mb_to_gb(val):
            try:    return f"{int(val)/1024:.1f} GB"
            except: return val

        ip       = gd("Primary IP Address")
        dns      = gd("DNS Name")
        ip_str   = ip if ip == "—" else (f"{ip}  ({dns})" if dns != "—" else ip)

        storage_mib = gd("Total disk capacity MiB")
        storage_str = _mib_to_gb(storage_mib) if storage_mib != "—" else "—"

        ram_mb  = gd("Memory")
        ram_str = _mb_to_gb(ram_mb) if ram_mb != "—" else "—"

        infra  = irow("🌐 IP Address",      ip_str)
        infra += irow("💻 VM Name",         gd("VM"))
        infra += irow("💿 SO (Config)",     gd("OS according to the configuration file"))
        infra += irow("🔧 SO (VMware Tools)",gd("OS according to the VMware Tools"))
        infra += irow("⚡ vCPUs",           gd("CPUs"))
        infra += irow("🧠 Memoria RAM",     ram_str)
        infra += irow("💾 Almacenamiento",  storage_str)
        infra += irow("💿 Discos",          gd("Disks"))
        infra += irow("🔌 NICs",            gd("NICs"))
        infra += irow("⚡ Estado",          gd("VM Powerstate"))
        infra += irow("🏢 Datacenter",      gd("DATACENTER"))
        infra += irow("🔗 Cluster",         gd("Cluster"))
        infra += irow("📦 Solución",        gd("SOLUTION"))
        infra += irow("🏷️ Categoría",      gd("CATEGORY"))

        st.markdown(card("🖥️ Infraestructura", infra),
                    unsafe_allow_html=True)

    # ── Formateo inteligente de días ─────────────────────
    ORDEN_DIAS  = ["Lunes","Martes","Miercoles","Jueves","Viernes","Sabado","Domingo"]
    DIAS_SHORT  = {"Lunes":"Lun","Martes":"Mar","Miercoles":"Mié",
                   "Jueves":"Jue","Viernes":"Vie","Sabado":"Sáb","Domingo":"Dom"}
    DIAS_SET    = set(ORDEN_DIAS)

    def _fmt_dias(dias_str: str) -> str:
        """Convierte 'Lunes,Martes,Miercoles' → 'Lunes a Miércoles'; todos → 'Todos los días'."""
        if not dias_str or dias_str == "—":
            return "—"
        partes = [d.strip() for d in dias_str.split(",") if d.strip() in DIAS_SET]
        if not partes:
            return dias_str
        if len(partes) == 7:
            return "Todos los días"
        # Check if consecutive in week order
        indices = [ORDEN_DIAS.index(d) for d in partes if d in ORDEN_DIAS]
        indices_sorted = sorted(set(indices))
        if indices_sorted == list(range(min(indices_sorted), max(indices_sorted)+1)):
            first = ORDEN_DIAS[indices_sorted[0]]
            last  = ORDEN_DIAS[indices_sorted[-1]]
            return first if len(indices_sorted)==1 else f"{first} a {last}"
        return ", ".join(DIAS_SHORT.get(d, d) for d in partes)

    def _fmt_semanas(sem_str: str) -> str:
        """Convierte '1,2,3,4' → 'Todas las semanas'; '1,2' → 'Semanas 1 y 2'."""
        if not sem_str or sem_str == "—":
            return "—"
        sems = sorted(set(s.strip() for s in sem_str.split(",") if s.strip()))
        if set(sems) == {"1","2","3","4"}:
            return "Todas las semanas del mes"
        if len(sems) == 1:
            return f"Semana {sems[0]} del mes"
        if sems == [str(i) for i in range(int(sems[0]), int(sems[-1])+1)]:
            return f"Semanas {sems[0]} a {sems[-1]} del mes"
        return "Semanas " + ", ".join(sems[:-1]) + f" y {sems[-1]}"

    # ── Row 2: Ventana de Mantenimiento ──────────────────
    st.markdown("<br>", unsafe_allow_html=True)

    if tipo == "Horario Específico":
        ventana_html = (
            irow("📅 Inicio",  gv("start_dt")[:16])
            + irow("📅 Fin",   gv("end_dt")[:16])
        )
    elif tipo in ("Rango de Horario", "Horario Semi-específico"):
        sem_fmt  = _fmt_semanas(gv("semanas_rango"))
        dias_fmt = _fmt_dias(gv("dias_rango"))
        if tipo == "Rango de Horario":
            turno     = gv("turno_rango")
            hora_fmt  = f'{turno}  ({TURNO_DESC.get(turno, "")})'
        else:
            hora_fmt  = f'{gv("start_dt")[:5]} – {gv("end_dt")[:5]}'
        ventana_html = (
            irow("📆 Semanas",    sem_fmt)
            + irow("📅 Días",     dias_fmt)
            + irow("🕒 Horario",  hora_fmt)
        )
    else:
        ventana_html = irow("📅 Fecha/Hora", gv("start_dt"))

    st.markdown(card("🕒 Ventana de Mantenimiento",
        irow("Tipo", tipo) + ventana_html
    ), unsafe_allow_html=True)

    # ── Motivo de criticidad — banner visual ──────────────
    motivo = gv("motivo_criticidad")
    crit   = gv("criticidad")
    if motivo != "—" or crit != "—":
        CRIT_STYLES = {
            "Critico": ("🔴", "#9B2C2C", "#FFF5F5", "#FC8181"),
            "Alta":    ("🟠", "#7B341E", "#FFFAF0", "#F6AD55"),
            "Media":   ("🟡", "#744210", "#FFFFF0", "#ECC94B"),
            "Baja":    ("🟢", "#22543D", "#F0FFF4", "#68D391"),
        }
        icon, text_color, bg, border = CRIT_STYLES.get(crit, ("⚪","#4A5568","#F7FAFC","#CBD5E0"))
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="background:{bg};border:1.5px solid {border};border-radius:12px;
             padding:14px 18px;display:flex;align-items:flex-start;gap:12px;">
          <div style="font-size:1.6rem;line-height:1;margin-top:2px;">{icon}</div>
          <div>
            <div style="font-size:.67rem;font-weight:800;letter-spacing:.09em;
                 text-transform:uppercase;color:{border};margin-bottom:4px;">
              Criticidad {crit}
            </div>
            <div style="font-size:.86rem;font-weight:500;color:{text_color};line-height:1.55;">
              {motivo if motivo != "—" else "Sin justificación registrada."}
            </div>
          </div>
        </div>""", unsafe_allow_html=True)

    # ── Apps ──────────────────────────────────────────────
    apps = gv("apps")
    if apps != "—":
        st.markdown("<br>", unsafe_allow_html=True)
        with section_card("⚙️ Aplicaciones y Servicios"):
            chips = [a.strip() for a in apps.split(",") if a.strip()]
            st.markdown("".join(
                f'<span style="display:inline-block;padding:3px 11px;margin:3px;'
                f'background:rgba(255,120,0,.11);border:1px solid rgba(255,120,0,.28);'
                f'color:#E86A00;border-radius:20px;font-size:.77rem;font-weight:600;">{c}</span>'
                for c in (chips or [apps])
            ), unsafe_allow_html=True)

    # ── Comentarios ───────────────────────────────────────
    com = gv("comentarios")
    if com != "—":
        st.markdown("<br>", unsafe_allow_html=True)
        with section_card("💬 Comentarios"):
            st.markdown(
                f'<div style="font-size:.85rem;color:#4A5568;line-height:1.7;">{com}</div>',
                unsafe_allow_html=True)

    # ── Dos pestañas: estado vs agendamiento ─────────────
    st.markdown("<br>", unsafe_allow_html=True)
    t_estado, t_agend = st.tabs([
        "📊 Estado de Migración (ESTADO_VMS)",
        "✏️ Editar Agendamiento (VMs)",
    ])
    with t_estado:
        st.caption("Modifica el estado de migración, fechas y observaciones. "
                   "Escribe en la tabla **ESTADO_VMS** — no toca el agendamiento.")
        render_status_editor(vm_id, gv('cliente'), estado, key_suffix="cal")
    with t_agend:
        st.caption("Modifica los datos de agendamiento: VM ID, cliente, horario, etc. "
                   "Escribe en la tabla **VMs** — no toca el estado de migración.")
        render_vm_selector_and_editor(key_suffix="cal_det")


# ─────────────────────────────────────────────────────────────
# Day detail section (shared by both views)
# ─────────────────────────────────────────────────────────────
def _day_section(day_evs: list, sel: date, key_prefix: str, show_table: bool = True):
    """Tabla del día + botones de VM. key_prefix evita duplicados entre vistas."""
    sel_key = sel.strftime("%Y-%m-%d")

    if not day_evs:
        st.info("Sin ventanas en este día.")
        return

    if show_table:
        _df_day = events_to_df(day_evs)
        st.dataframe(_df_day, use_container_width=True, hide_index=True)
        _download_row(_df_day, "Ventanas del día", f"cal_dia_{key_prefix}")

    st.markdown(
        '<div style="font-size:.77rem;font-weight:700;color:#4A5568;margin:12px 0 6px;">'
        '🖥️ Ver detalle completo de una VM:</div>', unsafe_allow_html=True)

    vm_ids = [ev["vm_id"] for ev in day_evs if ev["vm_id"]]
    for i in range(0, len(vm_ids), 4):
        cols = st.columns(min(4, len(vm_ids)-i))
        for col, vid in zip(cols, vm_ids[i:i+4]):
            ev_match = next((e for e in day_evs if e["vm_id"]==vid), {})
            color    = ev_match.get("color", DEFAULT_COLOR)
            estado   = ev_match.get("estado","")
            with col:
                st.markdown(
                    f'<div style="font-size:.63rem;color:{color};font-weight:700;'
                    f'margin-bottom:1px;text-align:center;">'
                    f'{ESTADO_ICON.get(estado,"🖥️")} {estado}</div>',
                    unsafe_allow_html=True)
                if st.button(vid, key=f"{key_prefix}_{vid}_{sel_key}",
                             use_container_width=True):
                    st.session_state["cal_vm"] = vid
                    st.rerun()


# ─────────────────────────────────────────────────────────────
# Pending VMs panel
# ─────────────────────────────────────────────────────────────
def _load_pending_vms(cliente: str) -> pd.DataFrame:
    """
    Returns VMs for a client whose Estado_Migracion is
    'Asignada', 'Pendiente', or has no entry in ESTADO_VMS.
    """
    cm     = build_column_map()
    col_vm  = cm.get("vm_id","VM_ID_TM")
    col_cli = cm.get("cliente","Cliente")
    conn   = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(f"""
            SELECT
                v."{col_vm}" AS VM_ID,
                COALESCE(e.Estado_Migracion, 'Sin estado') AS Estado,
                v."{cm.get('ambiente','Ambiente')}"         AS Ambiente,
                v."{cm.get('criticidad','Criticidad')}"     AS Criticidad,
                v."{cm.get('tipo_ventana','Tipo_Ventana')}" AS Tipo_Ventana
            FROM VMs v
            LEFT JOIN ESTADO_VMS e ON v."{col_vm}" = e."{col_vm}"
            WHERE v."{col_cli}" = ?
              AND (
                e.Estado_Migracion IS NULL
                OR e.Estado_Migracion IN ('Agendado','Sin Agendar')
              )
            ORDER BY v.rowid
        """, conn, params=(cliente,))
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


def _pending_vms_section(cliente: str):
    """Shows pending/unstarted VMs for the selected client as quick-access buttons."""
    if not cliente or cliente == "— Todos —":
        return

    df = _load_pending_vms(cliente)
    if df.empty:
        st.info(f"✅ **{cliente}** no tiene VMs pendientes o sin estado.")
        return

    ESTADO_COL = {
        "Agendado":    "#3182CE",
        "Sin Agendar": "#D69E2E",
        "Sin estado":  "#8A95A3",
    }

    st.markdown(
        f'<div style="font-size:.72rem;font-weight:800;letter-spacing:.08em;'
        f'text-transform:uppercase;color:#FF7800;margin-bottom:8px;">'
        f'🖥️ VMs pendientes de {cliente} ({len(df)})</div>',
        unsafe_allow_html=True)

    # Grid of buttons — 5 per row
    for i in range(0, len(df), 5):
        cols = st.columns(min(5, len(df)-i))
        for col, (_, row) in zip(cols, df.iloc[i:i+5].iterrows()):
            vid    = row["VM_ID"]
            est    = row["Estado"]
            color  = ESTADO_COL.get(est, "#8A95A3")
            with col:
                st.markdown(
                    f'<div style="font-size:.6rem;color:{color};font-weight:700;'
                    f'text-align:center;margin-bottom:1px;">{est}</div>',
                    unsafe_allow_html=True)
                if st.button(vid, key=f"pv_{vid}", use_container_width=True):
                    st.session_state["cal_vm"] = vid
                    st.rerun()


# ─────────────────────────────────────────────────────────────
# Download helper
# ─────────────────────────────────────────────────────────────
def _download_row(df: pd.DataFrame, label: str, key: str):
    """Renders CSV + Excel download buttons for a DataFrame."""
    if df.empty:
        return
    dc1, dc2, _ = st.columns([1, 1, 4])
    with dc1:
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            f"📥 CSV — {label}", data=csv,
            file_name=f"{key}.csv", mime="text/csv",
            key=f"dl_csv_{key}", use_container_width=True,
        )
    with dc2:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name=label[:31])
            ws = w.sheets[label[:31]]
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(
                    max(len(str(c.value or '')) for c in col) + 4, 40)
        st.download_button(
            f"📥 Excel — {label}", data=buf.getvalue(),
            file_name=f"{key}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_xl_{key}", use_container_width=True,
        )


# ─────────────────────────────────────────────────────────────
# Main render
# ─────────────────────────────────────────────────────────────
def render():
    _init()

    # ── VM detail view ────────────────────────────────────
    if st.session_state["cal_vm"]:
        _vm_detail(st.session_state["cal_vm"])
        return

    year  = st.session_state["cal_year"]
    month = st.session_state["cal_month"]

    # ── Top controls bar ─────────────────────────────────
    c1, c2, c3 = st.columns([1.5, 2.2, 2.2])

    with c1:
        view = st.radio("Vista:", ["📅 Calendario","📋 Tabla"],
                        horizontal=True, key="cal_view_r",
                        index=0 if "Calendario" in st.session_state["cal_view"] else 1)
        st.session_state["cal_view"] = view

    with c2:
        # Date picker — key IS cal_date so Streamlit syncs automatically
        # We manually sync cal_dp when nav buttons change date
        picked = st.date_input("Ir a fecha:",
                               value=st.session_state["cal_date"],
                               label_visibility="collapsed")
        if picked != st.session_state["cal_date"]:
            _set_date(picked)
            st.rerun()

    with c3:
        clientes = _clientes()
        opts     = ["— Todos —"] + clientes
        idx      = opts.index(st.session_state["cal_client"]) if st.session_state["cal_client"] in opts else 0
        st.session_state["cal_client"] = st.selectbox(
            "Cliente:", opts, index=idx, key="cal_cli",
            label_visibility="collapsed")

    # ── Pending VMs for selected client ─────────────────
    if st.session_state["cal_client"] != "— Todos —":
        with section_card(f"🔍 VMs Pendientes — {st.session_state['cal_client']}"):
            render_vm_selector_and_editor(key_suffix="cal_pend")
        st.markdown("<br>", unsafe_allow_html=True)

    # ── Month navigator (embedded in calendar header area) ──
    mh1, mh2, mh3 = st.columns([1, 3, 1])
    with mh1:
        if st.button("◀  Mes anterior", key="prev_m", use_container_width=True):
            if month == 1:
                st.session_state["cal_year"]  = year - 1
                st.session_state["cal_month"] = 12
            else:
                st.session_state["cal_month"] -= 1
            st.rerun()
    with mh2:
        st.markdown(
            f'<div style="text-align:center;font-size:1.1rem;font-weight:800;'
            f'color:#1E2330;padding:6px 0;">'
            f'{MONTH_NAMES_ES[month]} {year}</div>',
            unsafe_allow_html=True)
    with mh3:
        if st.button("Mes siguiente  ▶", key="next_m", use_container_width=True):
            if month == 12:
                st.session_state["cal_year"]  = year + 1
                st.session_state["cal_month"] = 1
            else:
                st.session_state["cal_month"] += 1
            st.rerun()

    # ── Load events — only show Agendado VMs ─────────────
    cliente_filter = None if st.session_state["cal_client"] == "— Todos —" else st.session_state["cal_client"]
    _raw_events = get_events_for_month(
        st.session_state["cal_year"],
        st.session_state["cal_month"],
        cliente_filter,
    )
    events_by_date = {
        dk: [ev for ev in evs if ev.get("estado") == "Agendado"]
        for dk, evs in _raw_events.items()
        if any(ev.get("estado") == "Agendado" for ev in evs)
    }

    sel     = st.session_state["cal_date"]
    sel_key = sel.strftime("%Y-%m-%d")
    day_evs = events_by_date.get(sel_key, [])

    # ══════════════════════════════════════════════════════
    # VISTA CALENDARIO
    # ══════════════════════════════════════════════════════
    if "Calendario" in st.session_state["cal_view"]:

        # Estado legend
        leg = '<div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:8px;">'
        for estado, color in ESTADO_COLOR.items():
            icon = ESTADO_ICON.get(estado,"")
            leg += (f'<span style="font-size:.66rem;font-weight:700;padding:2px 9px;'
                    f'border-radius:20px;background:{color};color:#fff;">{icon} {estado}</span>')
        leg += "</div>"
        st.markdown(leg, unsafe_allow_html=True)

        # Calendar iframe (visual + hover tooltips, NO links)
        import calendar as cal_mod
        _, num_days = cal_mod.monthrange(
            st.session_state["cal_year"], st.session_state["cal_month"])
        num_weeks = -(-num_days // 7) + 1  # ceil + header row
        cal_height = max(480, num_weeks * 95 + 50)

        cal_html = build_calendar_html(
            st.session_state["cal_year"],
            st.session_state["cal_month"],
            events_by_date,
            selected_date=sel,
            selected_vm_id=st.session_state.get("cal_vm"),
        )
        components.html(cal_html, height=cal_height, scrolling=False)

        # ── Day nav + detail ─────────────────────────────
        st.markdown("---")

        nav1, nav2, nav3 = st.columns([1, 4, 1])
        with nav1:
            if st.button("◀ Día ant.", key="d_prev", use_container_width=True):
                _set_date(sel - timedelta(days=1))
                st.rerun()
        with nav2:
            cnt = len(day_evs)
            st.markdown(
                f'<div style="text-align:center;font-size:.95rem;font-weight:800;'
                f'color:#1E2330;padding:6px 0;">'
                f'📆 {sel.day} de {MONTH_NAMES_ES[sel.month]} de {sel.year} '
                f'<span style="font-size:.74rem;color:#8A95A3;font-weight:500;">'
                f'— {cnt} ventana{"s" if cnt!=1 else ""}</span></div>',
                unsafe_allow_html=True)
        with nav3:
            if st.button("Día sig. ▶", key="d_next", use_container_width=True):
                _set_date(sel + timedelta(days=1))
                st.rerun()

        _day_section(day_evs, sel, "cv")

    # ══════════════════════════════════════════════════════
    # VISTA TABLA — resumen semana/mes + detalle del día
    # ══════════════════════════════════════════════════════
    else:
        # ── Semana / Mes toggle ───────────────────────────
        import calendar as _cal_mod
        tab_rng = st.radio(
            "Rango:", ["📅 Semana", "🗓️ Mes"],
            horizontal=True, key="ta_rango",
        )

        if tab_rng == "📅 Semana":
            # ISO week containing sel
            week_start = sel - timedelta(days=sel.weekday())
            week_end   = week_start + timedelta(days=6)
            rng_evs = [
                ev
                for dk, evs in events_by_date.items()
                for ev in evs
                if week_start <= date.fromisoformat(dk) <= week_end
            ]
            card_title = (f"📋 Semana {sel.isocalendar()[1]} "
                          f"({week_start.strftime('%d/%m')} – {week_end.strftime('%d/%m/%Y')}) "
                          f"— {len(rng_evs)} ventanas")
        else:
            rng_evs    = [ev for evs in events_by_date.values() for ev in evs]
            card_title = f"📋 Todas las ventanas — {MONTH_NAMES_ES[month]} {year}  ({len(rng_evs)})"

        with section_card(card_title):
            if rng_evs:
                df_rng = events_to_df(rng_evs)
                fc1, fc2, fc3 = st.columns(3)
                with fc1:
                    amb_f = st.multiselect("Ambiente:", df_rng["Ambiente"].dropna().unique().tolist(), key="ta_amb")
                with fc2:
                    est_f = st.multiselect("Estado:",   df_rng["Estado"].dropna().unique().tolist(),   key="ta_est")
                with fc3:
                    cli_f = st.multiselect("Cliente:",  df_rng["Cliente"].dropna().unique().tolist(),  key="ta_cli")
                if amb_f: df_rng = df_rng[df_rng["Ambiente"].isin(amb_f)]
                if est_f: df_rng = df_rng[df_rng["Estado"].isin(est_f)]
                if cli_f: df_rng = df_rng[df_rng["Cliente"].isin(cli_f)]
                st.dataframe(df_rng, use_container_width=True, hide_index=True)
                rng_label = "Semana" if tab_rng == "📅 Semana" else "Mes"
                _download_row(df_rng, f"Ventanas {rng_label}", f"cal_tabla_{rng_label.lower()}")
            else:
                st.info("Sin ventanas en este período.")

        st.markdown("---")

        # ── Day navigator + day detail ────────────────────
        nav1, nav2, nav3 = st.columns([1, 4, 1])
        with nav1:
            if st.button("◀ Día ant.", key="t_prev", use_container_width=True):
                _set_date(sel - timedelta(days=1))
                st.rerun()
        with nav2:
            cnt = len(day_evs)
            st.markdown(
                f'<div style="text-align:center;font-size:.95rem;font-weight:800;'
                f'color:#1E2330;padding:6px 0;">'
                f'📆 {sel.day} de {MONTH_NAMES_ES[sel.month]} de {sel.year} '
                f'<span style="font-size:.74rem;color:#8A95A3;font-weight:500;">'
                f'— {cnt} ventana{"s" if cnt!=1 else ""}</span></div>',
                unsafe_allow_html=True)
        with nav3:
            if st.button("Día sig. ▶", key="t_next", use_container_width=True):
                _set_date(sel + timedelta(days=1))
                st.rerun()

        with section_card(f"📋 Ventanas del {sel.day} de {MONTH_NAMES_ES[sel.month]}"):
            if not day_evs:
                if events_by_date:
                    st.info("Sin ventanas en este día. Días con ventanas:")
                    dias_con_evs = sorted(events_by_date.keys())
                    btns = st.columns(min(7, len(dias_con_evs)))
                    for col, dk in zip(btns, dias_con_evs[:7]):
                        d_obj = date.fromisoformat(dk)
                        with col:
                            if st.button(f"{d_obj.day}/{d_obj.month}",
                                         key=f"qd_{dk}", use_container_width=True):
                                _set_date(d_obj)
                                st.rerun()
                else:
                    st.info("Sin ventanas este mes.")
        _day_section(day_evs, sel, "tv", show_table=True)