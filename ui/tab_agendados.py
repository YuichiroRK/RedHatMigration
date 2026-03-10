"""
ui/tab_agendados.py
Tab de visualización — dashboard global + progreso por cliente + detalle/edición de VM.
"""

import sqlite3
import streamlit as st
import pandas as pd

from ui.components import section_card
from ui.db_utils import build_column_map, safe_get, DB_PATH
from ui.status_widget import render_status_editor, STATE_META as ESTADO_COLOR_MAP
from ui.vm_editor import render_vm_editor, render_vm_selector_and_editor

COL_VM_ID = "VM_ID_TM"

TURNO_HORAS = {"Mañana":"06:00–14:00","Tarde":"14:00–22:00","Noche":"22:00–06:00"}

# Orden y metadatos de todos los estados posibles
ESTADOS_META = {
    "Asignada":       {"icon":"🔵","color":"#3182CE","label":"Asignadas"},
    "Éxito":          {"icon":"✅","color":"#38A169","label":"Éxito"},
    "Pendiente":      {"icon":"⏳","color":"#D69E2E","label":"Pendientes"},
    "En Seguimiento": {"icon":"🔍","color":"#805AD5","label":"Seguimiento"},
    "RollBack":       {"icon":"↩️","color":"#E53E3E","label":"RollBack"},
    "Fallida":        {"icon":"❌","color":"#C53030","label":"Fallidas"},
}


# ─────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────
def _load_all() -> pd.DataFrame:
    """
    Carga VMs y hace LEFT JOIN con ESTADO_VMS para traer
    Estado_Migracion, Fecha_Ejecucion, Fecha_Finalizacion, Observaciones_Fallo.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query("""
            SELECT
                v.*,
                COALESCE(e.Estado_Migracion, v.Estado, 'Asignada') AS Estado_Migracion,
                e.Fecha_Ejecucion,
                e.Fecha_Finalizacion,
                e.Observaciones_Fallo
            FROM VMs v
            LEFT JOIN ESTADO_VMS e ON v.VM_ID_TM = e.VM_ID_TM
            ORDER BY v.rowid DESC
        """, conn)
    except:
        # Fallback si ESTADO_VMS no existe aún
        try:
            return pd.read_sql_query("SELECT * FROM VMs ORDER BY rowid DESC", conn)
        except:
            return pd.DataFrame()
    finally:
        conn.close()


def _col_estado(df: pd.DataFrame) -> str | None:
    # Prefer the joined ESTADO_VMS column, fallback to VMs.Estado
    for c in ["Estado_Migracion", "Estado", "estado"]:
        if c in df.columns: return c
    return None


def _fmt_ventana(row: pd.Series, cm: dict) -> str:
    tipo = str(row.get(cm.get("tipo_ventana",""),"")).strip()
    if tipo == "Horario Específico":
        s = str(row.get(cm.get("start_dt",""),""))[:16]
        e = str(row.get(cm.get("end_dt",""),""))[:16]
        return f"{s} → {e}"
    elif tipo == "Rango de Horario":
        turno = str(row.get(cm.get("turno_rango",""),"")).strip()
        sems  = str(row.get(cm.get("semanas_rango",""),"")).strip()
        dias  = str(row.get(cm.get("dias_rango",""),"")).strip()
        return f"Sem {sems} | {dias} | {turno} ({TURNO_HORAS.get(turno,'')})"
    elif tipo == "Horario Semi-específico":
        sems = str(row.get(cm.get("semanas_rango",""),"")).strip()
        dias = str(row.get(cm.get("dias_rango",""),"")).strip()
        ts   = str(row.get(cm.get("start_dt",""),""))[:5]
        te   = str(row.get(cm.get("end_dt",""),""))[:5]
        return f"Sem {sems} | {dias} | {ts}–{te}"
    return tipo or "—"


# ─────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────
def _css():
    st.markdown("""<style>
    .mc{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;}
    .mc-card{
        background:#fff;border:1px solid #E2E6ED;border-radius:12px;
        padding:16px 14px;box-shadow:0 2px 6px rgba(0,0,0,.05);
        flex:1;min-width:130px;text-align:center;
        transition:transform .15s,box-shadow .15s;
    }
    .mc-card:hover{transform:translateY(-3px);box-shadow:0 6px 14px rgba(255,120,0,.13);}
    .mc-icon{font-size:1.5rem;margin-bottom:6px;}
    .mc-label{color:#8A95A3;font-size:.72rem;font-weight:700;
              text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px;}
    .mc-val{font-size:2rem;font-weight:800;line-height:1.15;}
    .mc-card.total .mc-val{color:#FF7800;}
    .prog-bar-wrap{margin:6px 0 12px;}
    .prog-label{font-size:.74rem;font-weight:600;color:#4A5568;margin-bottom:4px;}
    .prog-track{height:9px;background:#E2E6ED;border-radius:99px;overflow:hidden;}
    .prog-fill{height:100%;border-radius:99px;transition:width .4s ease;}
    .sec-title{color:#FF7800;font-size:.82rem;font-weight:800;letter-spacing:.1em;
               text-transform:uppercase;margin-bottom:14px;
               border-bottom:2px solid #F0F2F6;padding-bottom:7px;}
    </style>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# Dashboard global
# ─────────────────────────────────────────────────────────────
def _dashboard_global(df_all: pd.DataFrame):
    conn = sqlite3.connect(DB_PATH)
    try:    total_sistema = int(pd.read_sql_query("SELECT COUNT(*) AS n FROM DATABASE",conn).iloc[0]["n"])
    except: total_sistema = len(df_all)
    finally: conn.close()

    total_ag = len(df_all)
    col_e    = _col_estado(df_all)

    # Conteos por estado
    counts = {}
    for est in ESTADOS_META:
        counts[est] = int((df_all[col_e]==est).sum()) if col_e else 0

    pct_ag    = round(total_ag/total_sistema*100, 1) if total_sistema else 0
    pct_exito = round(counts["Éxito"]/total_ag*100, 1) if total_ag else 0

    st.markdown('<div class="sec-title">🌐 Estadísticas Globales del Proyecto</div>',
                unsafe_allow_html=True)

    # Fila 1: totales grandes
    cards_top = f"""
    <div class="mc">
      <div class="mc-card total">
        <div class="mc-icon">🗃️</div>
        <div class="mc-label">Total en Sistema</div>
        <div class="mc-val">{total_sistema}</div>
      </div>
      <div class="mc-card total">
        <div class="mc-icon">📅</div>
        <div class="mc-label">Agendadas</div>
        <div class="mc-val">{total_ag}</div>
      </div>
      <div class="mc-card total">
        <div class="mc-icon">⏸️</div>
        <div class="mc-label">Sin Agendar</div>
        <div class="mc-val">{total_sistema - total_ag}</div>
      </div>
    </div>"""
    st.markdown(cards_top, unsafe_allow_html=True)

    # Fila 2: un card por estado
    estado_cards = '<div class="mc">'
    for est, meta in ESTADOS_META.items():
        cnt = counts[est]
        pct = round(cnt/total_ag*100,1) if total_ag else 0
        estado_cards += f"""
        <div class="mc-card" style="border-bottom:4px solid {meta['color']};">
          <div class="mc-icon">{meta['icon']}</div>
          <div class="mc-label">{meta['label']}</div>
          <div class="mc-val" style="color:{meta['color']};font-size:1.7rem;">{cnt}</div>
          <div style="font-size:.68rem;color:#A0AEC0;margin-top:2px;">{pct}% de agendadas</div>
        </div>"""
    estado_cards += "</div>"
    st.markdown(estado_cards, unsafe_allow_html=True)

    # Barras de progreso
    def prog(label, pct, color):
        return f"""
        <div class="prog-bar-wrap">
          <div class="prog-label">{label} ({pct}%)</div>
          <div class="prog-track">
            <div class="prog-fill" style="width:{min(pct,100)}%;background:{color};"></div>
          </div>
        </div>"""

    st.markdown(
        prog(f"📅 Agendamiento — {total_ag} de {total_sistema}", pct_ag, "#FF7800")
        + prog(f"✅ Migración completada — {counts['Éxito']} de {total_ag}", pct_exito, "#38A169"),
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# Progreso por cliente
# ─────────────────────────────────────────────────────────────
def _cliente_progress(df_cli: pd.DataFrame, total_sistema: int, col_e: str | None):
    total_ag = len(df_cli)
    counts   = {}
    for est in ESTADOS_META:
        counts[est] = int((df_cli[col_e]==est).sum()) if col_e else 0

    pct_ag    = round(total_ag/total_sistema*100,1) if total_sistema else 0
    pct_exito = round(counts["Éxito"]/total_ag*100,1) if total_ag else 0

    cards = '<div class="mc">'
    for est, meta in ESTADOS_META.items():
        cards += f"""
        <div class="mc-card" style="padding:10px 8px;border-bottom:3px solid {meta['color']};">
          <div style="font-size:.68rem;color:#8A95A3;font-weight:700;
               text-transform:uppercase;margin-bottom:2px;">{meta['icon']} {meta['label']}</div>
          <div style="font-size:1.6rem;font-weight:800;color:{meta['color']};">{counts[est]}</div>
        </div>"""
    cards += "</div>"
    st.markdown(cards, unsafe_allow_html=True)

    def prog(label, pct, color):
        return f"""
        <div class="prog-bar-wrap">
          <div class="prog-label">{label} ({pct}%)</div>
          <div class="prog-track">
            <div class="prog-fill" style="width:{min(pct,100)}%;background:{color};"></div>
          </div>
        </div>"""

    st.markdown(
        prog(f"Agendamiento vs sistema ({total_ag}/{total_sistema})", pct_ag, "#FF7800")
        + prog(f"Migración completada ({counts['Éxito']}/{total_ag})", pct_exito, "#38A169"),
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# VM Detail (inline — sin cambio de página)
# ─────────────────────────────────────────────────────────────
def _vm_detail_inline(vm_id: str, cm: dict, estado_actual: str, cliente: str = ""):
    """Panel expandible de detalle + editor de estado para una VM en tab_agendados."""
    # Info de infraestructura desde DATABASE
    col_vm = cm.get("vm_id","VM_ID_TM")
    conn   = sqlite3.connect(DB_PATH)
    try:
        df_db = pd.read_sql_query(
            f'SELECT * FROM DATABASE WHERE "{col_vm}"=?', conn, params=(vm_id,))
    except:
        df_db = pd.DataFrame()
    finally:
        conn.close()

    row_db = df_db.iloc[0] if not df_db.empty else pd.Series(dtype=object)
    def gd(col, default="—"):
        if col not in row_db.index: return default
        v = str(row_db[col])
        return default if v in ("nan","None","","<NA>") else v

    def _mb(v):
        try: return f"{int(v)/1024:.1f} GB"
        except: return v

    ip  = gd("Primary IP Address")
    dns = gd("DNS Name")
    ip_str = ip if ip=="—" else (f"{ip} ({dns})" if dns!="—" else ip)

    # Info cards
    col1, col2 = st.columns(2, gap="medium")
    def irow(k,v,color=None):
        vs = f"color:{color};font-weight:700;" if color else "color:#1E2330;font-weight:600;"
        return (f'<div style="display:flex;justify-content:space-between;padding:7px 0;'
                f'border-bottom:1px solid #F4F5F7;">'
                f'<span style="font-size:.74rem;color:#8A95A3;font-weight:600;">{k}</span>'
                f'<span style="font-size:.78rem;{vs}">{v or "—"}</span></div>')

    AMB = {"PROD":"#E53E3E","DEV":"#38A169","QA":"#D69E2E"}
    amb = safe_get(row_db, "Ambiente","—") if "Ambiente" in row_db.index else "—"

    with col1:
        st.markdown(
            f'<div style="background:#fff;border:1px solid #E8ECF1;border-radius:10px;'
            f'padding:12px 14px;">'
            + irow("🌐 IP Address", ip_str)
            + irow("💻 VM", gd("VM"))
            + irow("💿 Sistema Op.", gd("OS according to the configuration file"))
            + irow("⚡ vCPUs", gd("CPUs"))
            + irow("🧠 RAM", _mb(gd("Memory")))
            + irow("💾 Almacenamiento", _mb(gd("Total disk capacity MiB")))
            + '</div>', unsafe_allow_html=True)

    with col2:
        st.markdown(
            f'<div style="background:#fff;border:1px solid #E8ECF1;border-radius:10px;'
            f'padding:12px 14px;">'
            + irow("🏢 Datacenter", gd("DATACENTER"))
            + irow("🔗 Cluster", gd("Cluster"))
            + irow("⚡ Powerstate", gd("VM Powerstate"))
            + irow("💿 Discos", gd("Disks"))
            + irow("🔌 NICs", gd("NICs"))
            + irow("📦 Solución", gd("SOLUTION"))
            + '</div>', unsafe_allow_html=True)

    # Estado editor
    render_status_editor(vm_id, cliente, estado_actual, key_suffix="ag")


# ─────────────────────────────────────────────────────────────
# Main render
# ─────────────────────────────────────────────────────────────
def render():
    _css()

    df_all = _load_all()
    if df_all.empty:
        st.info("ℹ️  Aún no hay registros en la tabla de agendamiento.")
        return

    cm      = build_column_map()
    col_cli = cm.get("cliente","Cliente")
    col_e   = _col_estado(df_all)

    # ── Dashboard global ──────────────────────────────────
    _dashboard_global(df_all)
    st.markdown("---")

    # ── Progreso por cliente ──────────────────────────────
    with section_card("👤 Progreso por Cliente"):
        clientes = (sorted(df_all[col_cli].dropna().unique().tolist())
                    if col_cli in df_all.columns else [])
        cliente_sel = st.selectbox(
            "Seleccione un cliente:",
            ["— Ver todos —"] + clientes,
            key="ag_cliente_filter",
        )
        if cliente_sel and cliente_sel != "— Ver todos —":
            df_cli = df_all[df_all[col_cli] == cliente_sel]
            conn = sqlite3.connect(DB_PATH)
            try:
                total_sis = int(pd.read_sql_query(
                    f'SELECT COUNT(*) AS n FROM DATABASE WHERE "CUSTOMER_Name_SCCD-TM"=?',
                    conn, params=(cliente_sel,)).iloc[0]["n"])
            except:
                total_sis = len(df_cli)
            finally:
                conn.close()
            st.markdown(
                f'<div style="font-size:.8rem;color:#4A5568;margin-bottom:10px;">'
                f'<strong>{cliente_sel}</strong> — {total_sis} VMs en el sistema</div>',
                unsafe_allow_html=True)
            _cliente_progress(df_cli, total_sis, col_e)

    # ── Tabla de VMs agendadas ────────────────────────────
    with section_card("📋 Detalle de VMs Agendadas"):
        df_view = df_all.copy()
        if "cliente_sel" in dir() and cliente_sel != "— Ver todos —" and col_cli in df_view.columns:
            df_view = df_view[df_view[col_cli] == cliente_sel]

        df_view["Ventana"] = df_view.apply(lambda r: _fmt_ventana(r, cm), axis=1)

        # Búsqueda + filtros
        busqueda = st.text_input("🔍 Buscar VM, cliente, detalle…", key="ag_busq")
        if busqueda:
            mask = df_view.astype(str).apply(
                lambda x: x.str.contains(busqueda, case=False, na=False)).any(axis=1)
            df_view = df_view[mask]

        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            col_a = cm.get("ambiente")
            amb_f = (st.multiselect("Ambiente:", df_view[col_a].dropna().unique().tolist(), key="ag_f_amb")
                     if col_a and col_a in df_view.columns else [])
        with fc2:
            col_c = cm.get("criticidad")
            crit_f = (st.multiselect("Criticidad:", df_view[col_c].dropna().unique().tolist(), key="ag_f_crit")
                      if col_c and col_c in df_view.columns else [])
        with fc3:
            est_f = (st.multiselect("Estado:", df_view[col_e].dropna().unique().tolist(), key="ag_f_est")
                     if col_e else [])

        if col_a  and amb_f:  df_view = df_view[df_view[col_a].isin(amb_f)]
        if col_c  and crit_f: df_view = df_view[df_view[col_c].isin(crit_f)]
        if col_e  and est_f:  df_view = df_view[df_view[col_e].isin(est_f)]

        st.markdown(
            f'<div style="font-size:.74rem;color:#8A95A3;margin-bottom:8px;">'
            f'{len(df_view)} registros</div>', unsafe_allow_html=True)
        st.dataframe(df_view, use_container_width=True, hide_index=True)

    # ── Selección de VM ──────────────────────────────────
    with section_card("🖥️ Gestionar VM"):
        col_vm_id = cm.get("vm_id","VM_ID_TM")
        vm_ids    = (sorted(df_view[col_vm_id].dropna().unique().tolist())
                     if col_vm_id in df_view.columns else [])

        if not vm_ids:
            st.info("Sin VMs en la selección actual.")
        else:
            vm_sel = st.selectbox("Seleccionar VM:", vm_ids, key="ag_vm_sel")

            if vm_sel:
                row_vm = df_view[df_view[col_vm_id]==vm_sel]
                estado_actual = "Asignada"
                if not row_vm.empty and col_e and col_e in row_vm.columns:
                    estado_actual = str(row_vm.iloc[0][col_e])

                # VM header badge
                color_vm = ESTADO_COLOR_MAP.get(estado_actual,{"color":"#FF7800","icon":"🟠"})["color"]
                icon_vm  = ESTADO_COLOR_MAP.get(estado_actual,{"color":"#FF7800","icon":"🟠"})["icon"]
                st.markdown(f"""
                <div style="background:#fff;border-radius:12px;border-left:4px solid {color_vm};
                     padding:12px 18px;margin:10px 0;box-shadow:0 1px 4px rgba(0,0,0,.05);
                     display:flex;align-items:center;gap:12px;">
                  <div style="font-size:1.4rem;">🖥️</div>
                  <div style="font-size:.95rem;font-weight:800;color:#1E2330;">{vm_sel}</div>
                  <div style="margin-left:auto;">
                    <span style="background:{color_vm};color:#fff;padding:3px 12px;
                          border-radius:20px;font-size:.75rem;font-weight:700;">
                      {icon_vm} {estado_actual}
                    </span>
                  </div>
                </div>""", unsafe_allow_html=True)

                # ── Two clearly separated action tabs ────────
                t_estado, t_agend = st.tabs([
                    "📊 Estado de Migración (ESTADO_VMS)",
                    "✏️ Editar Agendamiento (VMs)",
                ])

                cliente_vm = ""
                if not row_vm.empty and col_cli in row_vm.columns:
                    cliente_vm = str(row_vm.iloc[0][col_cli])

                with t_estado:
                    st.caption("Modifica el estado de migración, fechas y observaciones. "
                               "Escribe en la tabla **ESTADO_VMS** — no toca el agendamiento.")
                    _vm_detail_inline(vm_sel, cm, estado_actual, cliente_vm)

                with t_agend:
                    st.caption("Modifica los datos de agendamiento: VM ID, cliente, horario, etc. "
                               "Escribe en la tabla **VMs** — no toca el estado de migración.")
                    render_vm_selector_and_editor(key_suffix="ag_tab")