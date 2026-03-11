"""
ui/tab_stats.py
Weekly migration report — table + charts + Excel/CSV export.
Estadística de Clientes — client-level weekly summary.
"""
import io
import sqlite3
from datetime import date, timedelta

import pandas as pd
import streamlit as st

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    _has_plotly = True
except ImportError:
    _has_plotly = False

from ui.db_utils import DB_PATH

COL_CLIENTE_DB = "CUSTOMER_Name_SCCD-TM"

# ─────────────────────────────────────────────────────────────
# Client-level helpers
# ─────────────────────────────────────────────────────────────
def _get_client_status(vm_estados: list) -> str:
    """
    Explicit priority — Migrado OK ONLY when every VM is exactly Éxito.
    Rules:
      - Migrado OK  : ALL VMs = 'Éxito', no exceptions
      - Fallida     : any VM is Fallida
      - RollBack    : any VM is RollBack
      - En Seguimiento : any VM is En Seguimiento
      - Sin Agendar : any VM is Sin Agendar
      - Agendado    : rest (all have a state, but not yet Éxito)
    """
    if not vm_estados:
        return "Sin Agendar"
    s = set(str(e).strip() for e in vm_estados)
    if s == {"Éxito"}:
        return "Migrado OK"
    for estado in ("Fallida", "RollBack", "En Seguimiento", "Sin Agendar"):
        if estado in s:
            return estado
    return "Agendado"


def _load_client_snapshot() -> pd.DataFrame:
    """One row per client with current aggregated status and VM/notif counts."""
    conn = sqlite3.connect(DB_PATH)
    try:
        df_cli = pd.read_sql_query(
            'SELECT DISTINCT "Cliente" AS Cliente FROM DIRECTORIO_CLIENTE ORDER BY "Cliente"', conn)
    except Exception:
        try:
            df_cli = pd.read_sql_query(
                f'SELECT DISTINCT "{COL_CLIENTE_DB}" AS Cliente FROM DATABASE ORDER BY "{COL_CLIENTE_DB}"', conn)
        except Exception:
            df_cli = pd.DataFrame(columns=["Cliente"])

    try:
        df_vms = pd.read_sql_query("""
            SELECT v.Cliente,
                   COALESCE(e.Estado_Migracion, v.Estado, 'Sin Agendar') AS Estado
            FROM VMs v
            LEFT JOIN ESTADO_VMS e ON v.VM_ID_TM = e.VM_ID_TM
        """, conn)
    except Exception:
        df_vms = pd.DataFrame(columns=["Cliente", "Estado"])

    try:
        df_notif = pd.read_sql_query(
            'SELECT "Cliente", MAX("Fecha Notificación") AS ultima FROM NOTIFICACIONES_CLIENTES GROUP BY "Cliente"',
            conn)
    except Exception:
        df_notif = pd.DataFrame(columns=["Cliente", "ultima"])

    conn.close()

    rows = []
    for cli in df_cli["Cliente"].dropna().unique():
        vms_cli   = df_vms[df_vms["Cliente"] == cli]["Estado"].tolist() if not df_vms.empty else []
        total_vms = len(vms_cli)
        vms_ok    = vms_cli.count("Éxito")
        est_cli   = _get_client_status(vms_cli)
        nr        = df_notif[df_notif["Cliente"] == cli] if not df_notif.empty else pd.DataFrame()
        notificado = not nr.empty
        ultima     = nr.iloc[0]["ultima"] if notificado else None
        rows.append({
            "Cliente":        cli,
            "Estado_Cliente": est_cli,
            "Total VMs":      total_vms,
            "VMs Éxito":      vms_ok,
            "Notificado":     notificado,
            "Última Notif.":  ultima,
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────
def _load_weekly_data(n_weeks: int = 12) -> pd.DataFrame:
    """
    Builds a weekly summary DataFrame for the last n_weeks.
    All metrics are CLIENT-level counts:
      Total Clientes | Notificados | En Revisión | Migrados OK |
      En Seguimiento | RollBack | Fallido | Migrados OK (acum.)
    """
    conn = sqlite3.connect(DB_PATH)

    # ── Total unique clients (static baseline) ────────────
    try:
        df_all_cli = pd.read_sql_query(
            'SELECT DISTINCT "Cliente" AS c FROM DIRECTORIO_CLIENTE', conn)
        total_cli = len(df_all_cli)
    except Exception:
        try:
            df_all_cli = pd.read_sql_query(
                f'SELECT DISTINCT "{COL_CLIENTE_DB}" AS c FROM DATABASE', conn)
            total_cli = len(df_all_cli)
        except Exception:
            total_cli = 0

    # ── ESTADO_VMS joined with client ─────────────────────
    try:
        df_estado = pd.read_sql_query("""
            SELECT v.Cliente, e.Estado_Migracion, e.Fecha_Finalizacion
            FROM ESTADO_VMS e JOIN VMs v ON v.VM_ID_TM = e.VM_ID_TM
        """, conn)
    except Exception:
        df_estado = pd.DataFrame(columns=["Cliente", "Estado_Migracion", "Fecha_Finalizacion"])

    # ── Notifications per client ──────────────────────────
    try:
        df_notif = pd.read_sql_query(
            'SELECT "Cliente", "Fecha Notificación" AS fecha FROM NOTIFICACIONES_CLIENTES', conn)
    except Exception:
        df_notif = pd.DataFrame(columns=["Cliente", "fecha"])

    # ── Clients with any VM scheduled ─────────────────────
    try:
        df_ag = pd.read_sql_query(
            'SELECT DISTINCT Cliente FROM VMs WHERE StartDateTime IS NOT NULL', conn)
        ag_clients = set(df_ag["Cliente"].dropna())
    except Exception:
        ag_clients = set()

    conn.close()

    # ── Build week buckets ────────────────────────────────
    today   = date.today()
    weeks   = []
    current = today - timedelta(days=today.weekday())  # this Monday
    for _ in range(n_weeks):
        weeks.append(current)
        current -= timedelta(weeks=1)
    weeks.reverse()

    def week_label(d): return f"Sem {d.isocalendar()[1]}\n{d.strftime('%d/%m')}"

    # Current-state snapshots (not time-dependent — same for every week row)
    # En Revisión = clients with at least 1 VM "Sin Agendar"
    # Agendados   = clients with ALL VMs scheduled (no "Sin Agendar")
    try:
        conn2 = sqlite3.connect(DB_PATH)
        df_vm_states = pd.read_sql_query("""
            SELECT v.Cliente,
                   COALESCE(e.Estado_Migracion, v.Estado, 'Sin Agendar') AS Estado
            FROM VMs v
            LEFT JOIN ESTADO_VMS e ON v.VM_ID_TM = e.VM_ID_TM
        """, conn2)
        conn2.close()
        _rev_set: set = set()
        _ag_set:  set = set()
        for cli, grp in df_vm_states.groupby("Cliente"):
            estados = list(grp["Estado"].astype(str).str.strip())
            if "Sin Agendar" in estados:
                _rev_set.add(cli)
            else:
                _ag_set.add(cli)
        _snapshot_en_revision = len(_rev_set)
        _snapshot_agendados   = len(_ag_set)
    except Exception:
        _snapshot_en_revision = 0
        _snapshot_agendados   = 0

    # Pre-parse dates once to avoid repeated parsing inside loop
    def _parse_date(val):
        """Returns a Timestamp or NaT — never None — so the column dtype stays uniform."""
        try:
            return pd.to_datetime(str(val)[:10])
        except Exception:
            return pd.NaT

    if not df_notif.empty:
        df_notif = df_notif.copy()
        df_notif["_d"] = df_notif["fecha"].map(_parse_date)

    if not df_estado.empty:
        df_estado = df_estado.copy()
        df_estado["_d"] = df_estado["Fecha_Finalizacion"].map(_parse_date)

    rows = []
    cumulative_ok_clients: set = set()

    for wstart in weeks:
        wend  = wstart + timedelta(days=6)
        label = week_label(wstart)

        # Notificados esta semana (unique clients) — no closure, uses pre-parsed dates
        notif_cli: set = set()
        if not df_notif.empty and "_d" in df_notif.columns:
            mask = df_notif["_d"].apply(lambda d: pd.notna(d) and wstart <= d.date() <= wend)
            notif_cli = set(df_notif.loc[mask, "Cliente"].dropna())

        # Clients with ESTADO_VMS changes this week
        ok_cli_wk:   set = set()
        rb_cli_wk:   set = set()
        seg_cli_wk:  set = set()
        fall_cli_wk: set = set()
        if not df_estado.empty and "_d" in df_estado.columns:
            wk_mask = df_estado["_d"].apply(lambda d: pd.notna(d) and wstart <= d.date() <= wend)
            wk = df_estado[wk_mask]
            ok_cli_wk   = set(wk[wk["Estado_Migracion"] == "Éxito"]["Cliente"].dropna())
            rb_cli_wk   = set(wk[wk["Estado_Migracion"] == "RollBack"]["Cliente"].dropna())
            seg_cli_wk  = set(wk[wk["Estado_Migracion"] == "En Seguimiento"]["Cliente"].dropna())
            fall_cli_wk = set(wk[wk["Estado_Migracion"] == "Fallida"]["Cliente"].dropna())

        cumulative_ok_clients |= ok_cli_wk

        rows.append({
            "Semana":              label,
            "week_start":          wstart,
            "Total Clientes":      total_cli,
            "Notificados":         len(notif_cli),
            "En Revisión":         _snapshot_en_revision,   # current snapshot (clients with ≥1 Sin Agendar VM)
            "Agendados":           _snapshot_agendados,     # current snapshot (clients with all VMs scheduled)
            "Migrados OK":         len(ok_cli_wk),
            "En Seguimiento":      len(seg_cli_wk),
            "RollBack":            len(rb_cli_wk),
            "Fallido":             len(fall_cli_wk),
            "Migrados OK (acum.)": len(cumulative_ok_clients),
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# Charts
# ─────────────────────────────────────────────────────────────
_PLOTLY_CFG = {
    "displayModeBar": True,
    "toImageButtonOptions": {
        "format": "png",
        "filename": "liberty_estadistica",
        "height": 500,
        "width": 1400,
        "scale": 2,
    },
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}


def _chart_overall(df: pd.DataFrame):
    """Horizontal bar: Total clients vs migrated (cumulative)."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=df["Semana"], x=df["Total Clientes"],
        name="Total Clientes", orientation="h",
        marker_color="#9E9E9E", opacity=0.6,
    ))
    fig.add_trace(go.Bar(
        y=df["Semana"], x=df["Migrados OK (acum.)"],
        name="Migrados exitosamente", orientation="h",
        marker_color="#2E7D32",
    ))
    fig.update_layout(
        title="Overall status — Clientes migrados",
        barmode="overlay", height=380,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25),
        margin=dict(l=10, r=10, t=40, b=10),
        plot_bgcolor="#FAFAFA", paper_bgcolor="#FFFFFF",
    )
    return fig


def _chart_notif_sched(df: pd.DataFrame):
    """Grouped bars: notifications + en revisión + cumulative line."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=df["Semana"], y=df["Total Clientes"],
        name="Total Clientes", marker_color="#1565C0", opacity=0.35,
    ), secondary_y=False)
    fig.add_trace(go.Bar(
        x=df["Semana"], y=df["Notificados"],
        name="Notificados", marker_color="#0288D1",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=df["Semana"], y=df["En Revisión"],
        name="En Revisión", mode="lines+markers",
        line=dict(color="#7B1FA2", width=2),
    ), secondary_y=True)
    fig.add_trace(go.Scatter(
        x=df["Semana"], y=df["Migrados OK (acum.)"],
        name="Migrados OK Acum.", mode="lines+markers",
        line=dict(color="#2E7D32", width=2, dash="dot"),
    ), secondary_y=True)
    fig.update_layout(
        title="Notification & Scheduling",
        barmode="overlay", height=320,
        legend=dict(orientation="h", yanchor="bottom", y=-0.35, font_size=10),
        margin=dict(l=10, r=10, t=40, b=10),
        plot_bgcolor="#FAFAFA", paper_bgcolor="#FFFFFF",
    )
    return fig


def _chart_windows(df: pd.DataFrame):
    """Stacked bar: Migrados OK + RollBack + Fallido + cumulative line."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=df["Semana"], y=df["Migrados OK"],
        name="Migrados OK", marker_color="#2E7D32",
        text=df["Migrados OK"], textposition="inside", textfont_color="white",
    ), secondary_y=False)
    fig.add_trace(go.Bar(
        x=df["Semana"], y=df["En Seguimiento"],
        name="En Seguimiento", marker_color="#805AD5",
        text=df["En Seguimiento"], textposition="inside", textfont_color="white",
    ), secondary_y=False)
    fig.add_trace(go.Bar(
        x=df["Semana"], y=df["RollBack"],
        name="RollBack", marker_color="#C62828",
        text=df["RollBack"], textposition="inside", textfont_color="white",
    ), secondary_y=False)
    fig.add_trace(go.Bar(
        x=df["Semana"], y=df["Fallido"],
        name="Fallido", marker_color="#6B0000",
        text=df["Fallido"], textposition="inside", textfont_color="white",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=df["Semana"], y=df["Migrados OK (acum.)"],
        name="Acumulado OK", mode="lines",
        line=dict(color="#FF7800", width=3),
    ), secondary_y=True)
    fig.update_layout(
        title="Maintenance windows weekly status",
        barmode="stack", height=320,
        legend=dict(orientation="h", yanchor="bottom", y=-0.35, font_size=10),
        margin=dict(l=10, r=10, t=40, b=10),
        plot_bgcolor="#FAFAFA", paper_bgcolor="#FFFFFF",
    )
    return fig


# ─────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────
def _to_excel(df_weekly: pd.DataFrame, df_clients: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        export_w = df_weekly.drop(columns=["week_start"], errors="ignore")
        export_w.to_excel(writer, index=False, sheet_name="Resumen Semanal")
        df_clients.to_excel(writer, index=False, sheet_name="Detalle Clientes")
        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────
# Client detail panel (shown inline below table)
# ─────────────────────────────────────────────────────────────
_ESTADO_COLOR = {
    "Migrado OK":     "#2E7D32",
    "Éxito":          "#38A169",
    "Agendado":       "#3182CE",
    "En Seguimiento": "#805AD5",
    "Sin Agendar":    "#D69E2E",
    "RollBack":       "#E53E3E",
    "Fallida":        "#C53030",
}

# Maps each table metric → which Estado_Cliente values to show
_FILT_MAP = {
    "Total Clientes":      None,                           # all
    "Notificados":         "__notif__",                    # has notif
    "En Revisión":         ["Sin Agendar"],                # has at least 1 Sin Agendar VM
    "Agendados":           ["Agendado"],                   # all VMs scheduled, not yet migrated
    "Migrados OK":         ["Migrado OK"],
    "En Seguimiento":      ["En Seguimiento"],
    "RollBack":            ["RollBack"],
    "Fallido":             ["Fallida"],
    "Migrados OK (acum.)": ["Migrado OK"],
}


def _client_detail(metric: str, df_clients: pd.DataFrame):
    filt = _FILT_MAP.get(metric)
    if filt is None:
        df_show = df_clients.copy()
    elif filt == "__notif__":
        df_show = df_clients[df_clients["Notificado"] == True].copy()
    else:
        df_show = df_clients[df_clients["Estado_Cliente"].isin(filt)].copy()

    if df_show.empty:
        st.info(f"Sin clientes en **{metric}** actualmente.")
        return

    count = len(df_show)
    with st.expander(f"👥 {count} cliente(s) — {metric}", expanded=False):
        for _, row in df_show.iterrows():
            est   = row["Estado_Cliente"]
            color = _ESTADO_COLOR.get(est, "#9E9E9E")
            vms_s = (f"{row['VMs Éxito']}/{row['Total VMs']} VMs migradas"
                     if row["Total VMs"] > 0 else "Sin VMs registradas")
            notif_s = (f"Última notif: {str(row['Última Notif.'])[:10]}"
                       if row["Notificado"] else "Sin notificación")
            st.markdown(
                f'<div style="background:#fff;border:1px solid #E8ECF1;border-radius:10px;'
                f'padding:9px 14px;margin-bottom:5px;border-left:4px solid {color};'
                f'display:flex;align-items:center;gap:12px;">'
                f'<div style="flex:1;">'
                f'<div style="font-size:.82rem;font-weight:700;color:#1E2330;">{row["Cliente"]}</div>'
                f'<div style="font-size:.7rem;color:#8A95A3;margin-top:2px;">{vms_s} · {notif_s}</div>'
                f'</div>'
                f'<span style="background:{color};color:#fff;padding:2px 10px;'
                f'border-radius:20px;font-size:.7rem;font-weight:700;white-space:nowrap;">'
                f'{est}</span>'
                f'</div>',
                unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# Main render
# ─────────────────────────────────────────────────────────────
METRIC_ORDER = [
    "Total Clientes", "Notificados", "En Revisión", "Agendados",
    "Migrados OK", "En Seguimiento", "RollBack", "Fallido", "Migrados OK (acum.)",
]


def render():
    st.markdown("## 👥 Estadística de Clientes")

    # Migrate legacy state names on first load
    try:
        conn = sqlite3.connect(DB_PATH)
        for old, new in [("Pendiente","Sin Agendar"),("Asignada","Agendado"),("Asignadas","Agendado")]:
            conn.execute('UPDATE VMs SET "Estado"=? WHERE "Estado"=?', (new, old))
            conn.execute('UPDATE ESTADO_VMS SET "Estado_Migracion"=? WHERE "Estado_Migracion"=?', (new, old))
        conn.commit()
        conn.close()
    except Exception:
        pass

    # ── Controls (keep original labels) ──────────────────
    c1, c2, _ = st.columns([1, 1, 3])
    with c1:
        n_weeks = st.selectbox("Cantidad de semanas a mostrar:", [4, 8, 12, 16, 24], index=2,
                               key="stats_nweeks")
    with c2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Actualizar", key="stats_refresh"):
            st.session_state["stats_cache_bust"] = st.session_state.get("stats_cache_bust", 0) + 1
            st.rerun()

    _ = st.session_state.get("stats_cache_bust", 0)  # read to register dependency
    df = _load_weekly_data(n_weeks)

    if df.empty:
        st.info("Sin datos suficientes para generar el reporte.")
        return

    df_clients = _load_client_snapshot()

    # ── Table ─────────────────────────────────────────────
    st.markdown("### 📋 Resumen Semanal")
    display_cols = ["Semana"] + [m for m in METRIC_ORDER if m in df.columns]
    df_table = df[display_cols].set_index("Semana").T

    # Style: highlight rows with orange header
    st.dataframe(df_table, use_container_width=True)

    # ── Drill-down: one expander per metric, all start collapsed ──
    st.markdown("#### 🔍 Detalle de clientes por categoría")
    if df_clients.empty:
        st.info("Sin datos de clientes.")
    else:
        for metric in METRIC_ORDER:
            if metric in df.columns or metric == "Total Clientes":
                _client_detail(metric, df_clients)

    # ── Export buttons ────────────────────────────────────
    st.markdown("---")
    ec1, ec2, _ = st.columns([1, 1, 4])
    with ec1:
        excel_bytes = _to_excel(df, df_clients)
        st.download_button(
            "📥 Exportar Excel",
            data=excel_bytes,
            file_name=f"weekly_report_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_excel",
        )
    with ec2:
        csv_bytes = df.drop(columns=["week_start"], errors="ignore").to_csv(index=False).encode()
        st.download_button(
            "📥 Exportar CSV",
            data=csv_bytes,
            file_name=f"weekly_report_{date.today()}.csv",
            mime="text/csv",
            key="dl_csv",
        )

    st.markdown("---")

    # ── Charts ────────────────────────────────────────────
    if not _has_plotly:
        st.warning("Instala plotly para ver los gráficos: `pip install plotly`")
        return

    # Row 1: overall (full width)
    st.plotly_chart(_chart_overall(df), use_container_width=True, config=_PLOTLY_CFG)

    # Row 2: two charts side by side
    ch1, ch2 = st.columns(2)
    with ch1:
        st.plotly_chart(_chart_notif_sched(df), use_container_width=True, config=_PLOTLY_CFG)
    with ch2:
        st.plotly_chart(_chart_windows(df), use_container_width=True, config=_PLOTLY_CFG)