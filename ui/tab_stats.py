"""
ui/tab_stats.py
Weekly migration report — table + 4 charts + Excel/CSV export.
Mirrors the structure shown in the weekly report image.
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


# ─────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────
def _iso_week(dt_str: str):
    """Parse a datetime string and return (year, week) ISO tuple."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            d = pd.to_datetime(dt_str[:19], format=fmt[:len(dt_str[:19])])
            return d.isocalendar()[:2]  # (year, week)
        except Exception:
            pass
    return None, None


def _load_weekly_data(n_weeks: int = 12) -> pd.DataFrame:
    """
    Builds a weekly summary DataFrame for the last n_weeks.
    Columns mirror the weekly report:
      - Semana label
      - total_clientes
      - migrados_ok
      - rollback
      - notificados
      - agendados
      - en_revision  (Pendiente + En Seguimiento)
    """
    conn = sqlite3.connect(DB_PATH)

    # ── Total customers (static baseline) ────────────────
    try:
        total_cust = int(pd.read_sql_query(
            "SELECT COUNT(*) AS n FROM DATABASE", conn).iloc[0]["n"])
    except Exception:
        total_cust = 0

    # ── Migration results by week ─────────────────────────
    try:
        df_estado = pd.read_sql_query(
            'SELECT Estado_Migracion, Fecha_Finalizacion FROM ESTADO_VMS', conn)
    except Exception:
        df_estado = pd.DataFrame(columns=["Estado_Migracion","Fecha_Finalizacion"])

    # ── Notifications by week ─────────────────────────────
    try:
        df_notif = pd.read_sql_query(
            'SELECT "Fecha Notificación" AS fecha FROM NOTIFICACIONES_CLIENTES', conn)
    except Exception:
        df_notif = pd.DataFrame(columns=["fecha"])

    # ── Scheduled (VMs) by week ───────────────────────────
    try:
        df_vms = pd.read_sql_query(
            'SELECT StartDateTime FROM VMs WHERE StartDateTime IS NOT NULL', conn)
    except Exception:
        df_vms = pd.DataFrame(columns=["StartDateTime"])

    conn.close()

    # ── Build week buckets ────────────────────────────────
    today   = date.today()
    # Get ISO week start (Monday) for n_weeks back
    weeks = []
    current = today - timedelta(days=today.weekday())  # this Monday
    for _ in range(n_weeks):
        weeks.append(current)
        current -= timedelta(weeks=1)
    weeks.reverse()

    def week_label(d): return f"Sem {d.isocalendar()[1]}\n{d.strftime('%d/%m')}"

    rows = []
    cumulative_ok = 0

    for wstart in weeks:
        wend   = wstart + timedelta(days=6)
        wrange = pd.date_range(wstart, wend)
        label  = week_label(wstart)

        # migrados ok this week
        ok_wk = 0
        rb_wk = 0
        if not df_estado.empty:
            for _, r in df_estado.iterrows():
                try:
                    d = pd.to_datetime(str(r["Fecha_Finalizacion"])[:10])
                    if wstart <= d.date() <= wend:
                        est = str(r["Estado_Migracion"])
                        if est == "Éxito":   ok_wk += 1
                        if est == "RollBack": rb_wk += 1
                except Exception:
                    pass

        # notifications this week
        notif_wk = 0
        if not df_notif.empty:
            for _, r in df_notif.iterrows():
                try:
                    d = pd.to_datetime(str(r["fecha"])[:10])
                    if wstart <= d.date() <= wend:
                        notif_wk += 1
                except Exception:
                    pass

        # scheduled this week
        ag_wk = 0
        if not df_vms.empty:
            for _, r in df_vms.iterrows():
                try:
                    d = pd.to_datetime(str(r["StartDateTime"])[:10])
                    if wstart <= d.date() <= wend:
                        ag_wk += 1
                except Exception:
                    pass

        # pending/in-review (cumulative from estado)
        rev_wk = 0
        if not df_estado.empty:
            rev_wk = int(df_estado[
                df_estado["Estado_Migracion"].isin(["Pendiente","En Seguimiento"])
            ].shape[0])

        cumulative_ok += ok_wk

        rows.append({
            "Semana":          label,
            "week_start":      wstart,
            "Total Clientes":  total_cust,
            "Migrados OK (acum.)": cumulative_ok,
            "Migrados OK":     ok_wk,
            "RollBack":        rb_wk,
            "Notificados":     notif_wk,
            "Agendados":       ag_wk,
            "En Revisión":     rev_wk,
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# Charts
# ─────────────────────────────────────────────────────────────
def _chart_overall(df: pd.DataFrame):
    """Horizontal bar: Total customers vs migrated (cumulative) — top right."""
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
    """Grouped bars: notifications + scheduled + line for total."""
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
        x=df["Semana"], y=df["Agendados"],
        name="Agendados", mode="lines+markers",
        line=dict(color="#7B1FA2", width=2),
    ), secondary_y=True)
    fig.add_trace(go.Scatter(
        x=df["Semana"], y=df["En Revisión"],
        name="En Revisión", mode="lines+markers",
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
    """Grouped bar: migrated OK (green) + rollback (red) + cumulative line."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=df["Semana"], y=df["Migrados OK"],
        name="Migrados OK", marker_color="#2E7D32",
        text=df["Migrados OK"], textposition="inside", textfont_color="white",
    ), secondary_y=False)
    fig.add_trace(go.Bar(
        x=df["Semana"], y=df["RollBack"],
        name="RollBack", marker_color="#C62828",
        text=df["RollBack"], textposition="inside", textfont_color="white",
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
def _to_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        export = df.drop(columns=["week_start"], errors="ignore")
        export.to_excel(writer, index=False, sheet_name="Weekly Report")
        ws = writer.sheets["Weekly Report"]
        # Auto-width columns
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = max_len + 4
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────
# Main render
# ─────────────────────────────────────────────────────────────
def render():
    st.markdown("## 📊 Weekly Stats Report")

    # ── Controls ─────────────────────────────────────────
    c1, c2, _ = st.columns([1, 1, 3])
    with c1:
        n_weeks = st.selectbox("Cantidad de semanas a mostrar:", [4, 8, 12, 16, 24], index=2,
                                key="stats_nweeks")
    with c2:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh = st.button("🔄 Actualizar", key="stats_refresh")

    df = _load_weekly_data(n_weeks)

    if df.empty:
        st.info("Sin datos suficientes para generar el reporte.")
        return

    # ── Table ─────────────────────────────────────────────
    st.markdown("### 📋 Resumen Semanal")
    display_cols = [
        "Semana", "Total Clientes", "Migrados OK (acum.)",
        "Notificados", "Agendados", "En Revisión",
        "Migrados OK", "RollBack",
    ]
    st.dataframe(
        df[display_cols].set_index("Semana").T,
        use_container_width=True,
    )

    # ── Export buttons ────────────────────────────────────
    ec1, ec2, _ = st.columns([1, 1, 4])
    with ec1:
        excel_bytes = _to_excel(df)
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
    st.plotly_chart(_chart_overall(df), use_container_width=True)

    # Row 2: two charts side by side
    ch1, ch2 = st.columns(2)
    with ch1:
        st.plotly_chart(_chart_notif_sched(df), use_container_width=True)
    with ch2:
        st.plotly_chart(_chart_windows(df), use_container_width=True)