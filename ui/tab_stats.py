"""
ui/tab_stats.py
Weekly migration report — table + charts + Excel/CSV export.
Estadística de Clientes — client-level weekly summary with SQLite snapshotting.
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
# Base de Datos: Histórico Semanal
# ─────────────────────────────────────────────────────────────
def _init_historico_table():
    """Crea la tabla de histórico si no existe."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS HISTORICO_SEMANAL (
            week_start TEXT PRIMARY KEY,
            Semana TEXT,
            "Total Clientes" INTEGER,
            Notificados INTEGER,
            "En Revisión" INTEGER,
            Agendados INTEGER,
            "Migrados OK" INTEGER,
            "En Seguimiento" INTEGER,
            RollBack INTEGER,
            Fallido INTEGER,
            "Migrados OK (acum.)" INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def _save_weekly_data_to_db(df: pd.DataFrame) -> bool:
    """Guarda un DataFrame de semanas en la tabla histórica, actualizando si ya existen."""
    if df.empty:
        return False
        
    df_save = df.copy()
    # Aseguramos que la fecha sea un string (YYYY-MM-DD) para SQLite
    df_save["week_start"] = df_save["week_start"].astype(str)
    
    conn = sqlite3.connect(DB_PATH)
    try:
        # Para evitar duplicados, borramos las semanas que vamos a insertar
        for wstart in df_save["week_start"].unique():
            conn.execute("DELETE FROM HISTORICO_SEMANAL WHERE week_start = ?", (wstart,))
            
        df_save.to_sql("HISTORICO_SEMANAL", conn, if_exists="append", index=False)
        conn.commit()
        exito = True
    except Exception as e:
        st.error(f"Error al guardar en BD: {e}")
        exito = False
    finally:
        conn.close()
    return exito

def _load_historical_data(n_weeks: int) -> pd.DataFrame:
    """Lee el histórico de la base de datos de manera súper rápida."""
    conn = sqlite3.connect(DB_PATH)
    try:
        df_hist = pd.read_sql_query(f"""
            SELECT * FROM HISTORICO_SEMANAL 
            ORDER BY week_start DESC 
            LIMIT {n_weeks}
        """, conn)
        
        if not df_hist.empty:
            # Convertimos el string a objeto de fecha para que los gráficos funcionen bien
            df_hist["week_start"] = pd.to_datetime(df_hist["week_start"]).dt.date
            # Ordenamos cronológicamente (de antigua a reciente)
            df_hist = df_hist.sort_values("week_start")
    except Exception:
        df_hist = pd.DataFrame()
    finally:
        conn.close()
    return df_hist

# ─────────────────────────────────────────────────────────────
# Client-level helpers (Para el panel de detalles actual)
# ─────────────────────────────────────────────────────────────
def _get_client_status(vm_estados: list) -> str:
    """
    Explicit priority — Migrado OK ONLY when every VM is exactly Éxito.
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
    """One row per client with current aggregated status and resolution date."""
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
                   COALESCE(e.Estado_Migracion, v.Estado, 'Sin Agendar') AS Estado,
                   e.Fecha_Finalizacion
            FROM VMs v
            LEFT JOIN ESTADO_VMS e ON v.VM_ID_TM = e.VM_ID_TM
        """, conn)
    except Exception:
        df_vms = pd.DataFrame(columns=["Cliente", "Estado", "Fecha_Finalizacion"])

    try:
        df_notif = pd.read_sql_query(
            'SELECT "Cliente", MAX("Fecha Notificación") AS ultima FROM NOTIFICACIONES_CLIENTES GROUP BY "Cliente"',
            conn)
    except Exception:
        df_notif = pd.DataFrame(columns=["Cliente", "ultima"])

    conn.close()

    rows = []
    for cli in df_cli["Cliente"].dropna().unique():
        vms_cli   = df_vms[df_vms["Cliente"] == cli] if not df_vms.empty else pd.DataFrame()
        estados   = vms_cli["Estado"].tolist() if not vms_cli.empty else []
        total_vms = len(estados)
        vms_ok    = estados.count("Éxito")
        est_cli   = _get_client_status(estados)
        
        fecha_resolucion = pd.NaT
        if not vms_cli.empty and "Fecha_Finalizacion" in vms_cli.columns:
            fechas = pd.to_datetime(vms_cli["Fecha_Finalizacion"].astype(str).str[:10], errors='coerce')
            if est_cli == "Migrado OK":
                fecha_resolucion = fechas.max()
            elif est_cli in ("Fallida", "RollBack", "En Seguimiento"):
                mask = vms_cli["Estado"] == est_cli
                if mask.any():
                    fecha_resolucion = fechas[mask].max()

        nr         = df_notif[df_notif["Cliente"] == cli] if not df_notif.empty else pd.DataFrame()
        notificado = not nr.empty
        ultima     = nr.iloc[0]["ultima"] if notificado else None
        
        rows.append({
            "Cliente":          cli,
            "Estado_Cliente":   est_cli,
            "Total VMs":        total_vms,
            "VMs Éxito":        vms_ok,
            "Notificado":       notificado,
            "Última Notif.":    ultima,
            "Fecha_Resolucion": fecha_resolucion
        })
    return pd.DataFrame(rows)

# ─────────────────────────────────────────────────────────────
# Live Calculation (Motor de cálculo pesado)
# ─────────────────────────────────────────────────────────────
def _calculate_weekly_data_live(n_weeks: int, df_clients: pd.DataFrame) -> pd.DataFrame:
    """Calcula el resumen semanal procesando el histórico en vivo."""
    if df_clients.empty:
        return pd.DataFrame()

    conn = sqlite3.connect(DB_PATH)
    try:
        df_notif = pd.read_sql_query(
            'SELECT "Cliente", "Fecha Notificación" AS fecha FROM NOTIFICACIONES_CLIENTES', conn)
    except Exception:
        df_notif = pd.DataFrame(columns=["Cliente", "fecha"])
    conn.close()

    today   = date.today()
    weeks   = []
    current = today - timedelta(days=today.weekday())  # this Monday
    for _ in range(n_weeks):
        weeks.append(current)
        current -= timedelta(weeks=1)
    weeks.reverse()

    def week_label(d): return f"Sem {d.isocalendar()[1]}\n{d.strftime('%d/%m')}"
    def _parse_date(val):
        try: return pd.to_datetime(str(val)[:10])
        except: return pd.NaT

    if not df_notif.empty:
        df_notif["_d"] = df_notif["fecha"].map(_parse_date)

    df_clients = df_clients.copy()
    if "Fecha_Resolucion" in df_clients.columns:
        df_clients["_d_res"] = pd.to_datetime(df_clients["Fecha_Resolucion"])
    else:
        df_clients["_d_res"] = pd.NaT

    _snapshot_en_revision = len(df_clients[df_clients["Estado_Cliente"] == "Sin Agendar"])
    _snapshot_agendados   = len(df_clients[df_clients["Estado_Cliente"] == "Agendado"])
    total_cli             = len(df_clients)

    rows = []
    for wstart in weeks:
        wend  = wstart + timedelta(days=6)
        label = week_label(wstart)

        notif_cli = set()
        if not df_notif.empty and "_d" in df_notif.columns:
            mask = df_notif["_d"].apply(lambda d: pd.notna(d) and wstart <= d.date() <= wend)
            notif_cli = set(df_notif.loc[mask, "Cliente"].dropna())

        wk_mask = df_clients["_d_res"].apply(lambda d: pd.notna(d) and wstart <= d.date() <= wend)
        df_wk = df_clients[wk_mask]

        ok_wk   = len(df_wk[df_wk["Estado_Cliente"] == "Migrado OK"])
        rb_wk   = len(df_wk[df_wk["Estado_Cliente"] == "RollBack"])
        seg_wk  = len(df_wk[df_wk["Estado_Cliente"] == "En Seguimiento"])
        fall_wk = len(df_wk[df_wk["Estado_Cliente"] == "Fallida"])

        cum_mask = df_clients["_d_res"].apply(lambda d: pd.isna(d) or d.date() <= wend)
        cum_ok = len(df_clients[(df_clients["Estado_Cliente"] == "Migrado OK") & cum_mask])

        rows.append({
            "week_start":          wstart,
            "Semana":              label,
            "Total Clientes":      total_cli,
            "Notificados":         len(notif_cli),
            "En Revisión":         _snapshot_en_revision,
            "Agendados":           _snapshot_agendados,
            "Migrados OK":         ok_wk,
            "En Seguimiento":      seg_wk,
            "RollBack":            rb_wk,
            "Fallido":             fall_wk,
            "Migrados OK (acum.)": cum_ok,
        })
    return pd.DataFrame(rows)

# ─────────────────────────────────────────────────────────────
# Charts
# ─────────────────────────────────────────────────────────────
_PLOTLY_CFG = {
    "displayModeBar": True,
    "toImageButtonOptions": {"format": "png", "filename": "liberty_estadistica", "height": 500, "width": 1400, "scale": 2},
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}

def _chart_overall(df: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Bar(y=df["Semana"], x=df["Total Clientes"], name="Total Clientes", orientation="h", marker_color="#9E9E9E", opacity=0.6))
    fig.add_trace(go.Bar(y=df["Semana"], x=df["Migrados OK (acum.)"], name="Migrados exitosamente", orientation="h", marker_color="#2E7D32"))
    fig.update_layout(title="Overall status — Clientes migrados", barmode="overlay", height=380, legend=dict(orientation="h", yanchor="bottom", y=-0.25), margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="#FAFAFA", paper_bgcolor="#FFFFFF")
    return fig

def _chart_notif_sched(df: pd.DataFrame):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=df["Semana"], y=df["Total Clientes"], name="Total Clientes", marker_color="#1565C0", opacity=0.35), secondary_y=False)
    fig.add_trace(go.Bar(x=df["Semana"], y=df["Notificados"], name="Notificados", marker_color="#0288D1"), secondary_y=False)
    fig.add_trace(go.Scatter(x=df["Semana"], y=df["En Revisión"], name="En Revisión", mode="lines+markers", line=dict(color="#7B1FA2", width=2)), secondary_y=True)
    fig.add_trace(go.Scatter(x=df["Semana"], y=df["Migrados OK (acum.)"], name="Migrados OK Acum.", mode="lines+markers", line=dict(color="#2E7D32", width=2, dash="dot")), secondary_y=True)
    fig.update_layout(title="Notification & Scheduling", barmode="overlay", height=320, legend=dict(orientation="h", yanchor="bottom", y=-0.35, font_size=10), margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="#FAFAFA", paper_bgcolor="#FFFFFF")
    return fig

def _chart_windows(df: pd.DataFrame):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=df["Semana"], y=df["Migrados OK"], name="Migrados OK", marker_color="#2E7D32", text=df["Migrados OK"], textposition="inside", textfont_color="white"), secondary_y=False)
    fig.add_trace(go.Bar(x=df["Semana"], y=df["En Seguimiento"], name="En Seguimiento", marker_color="#805AD5", text=df["En Seguimiento"], textposition="inside", textfont_color="white"), secondary_y=False)
    fig.add_trace(go.Bar(x=df["Semana"], y=df["RollBack"], name="RollBack", marker_color="#C62828", text=df["RollBack"], textposition="inside", textfont_color="white"), secondary_y=False)
    fig.add_trace(go.Bar(x=df["Semana"], y=df["Fallido"], name="Fallido", marker_color="#6B0000", text=df["Fallido"], textposition="inside", textfont_color="white"), secondary_y=False)
    fig.add_trace(go.Scatter(x=df["Semana"], y=df["Migrados OK (acum.)"], name="Acumulado OK", mode="lines", line=dict(color="#FF7800", width=3)), secondary_y=True)
    fig.update_layout(title="Maintenance windows weekly status", barmode="stack", height=320, legend=dict(orientation="h", yanchor="bottom", y=-0.35, font_size=10), margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="#FAFAFA", paper_bgcolor="#FFFFFF")
    return fig

# ─────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────
def _to_excel(df_weekly: pd.DataFrame, df_clients: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        export_w = df_weekly.drop(columns=["week_start"], errors="ignore")
        export_w.to_excel(writer, index=False, sheet_name="Resumen Semanal")
        export_c = df_clients.drop(columns=["_d_res", "Fecha_Resolucion"], errors="ignore")
        export_c.to_excel(writer, index=False, sheet_name="Detalle Clientes")
        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)
    return buf.getvalue()

# ─────────────────────────────────────────────────────────────
# Client detail panel
# ─────────────────────────────────────────────────────────────
_ESTADO_COLOR = {
    "Migrado OK":     "#2E7D32", "Éxito":          "#38A169",
    "Agendado":       "#3182CE", "En Seguimiento": "#805AD5",
    "Sin Agendar":    "#D69E2E", "RollBack":       "#E53E3E",
    "Fallida":        "#C53030",
}

_FILT_MAP = {
    "Total Clientes":      None,
    "Notificados":         "__notif__",
    "En Revisión":         ["Sin Agendar"],
    "Agendados":           ["Agendado"],
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
            vms_s = f"{row['VMs Éxito']}/{row['Total VMs']} VMs migradas" if row["Total VMs"] > 0 else "Sin VMs registradas"
            notif_s = f"Última notif: {str(row['Última Notif.'])[:10]}" if row["Notificado"] else "Sin notificación"
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
                f'{est}</span></div>',
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

    # Asegurar que existe la tabla de histórico
    _init_historico_table()

    # Actualizar nombres antiguos en BD (si aplica)
    try:
        conn = sqlite3.connect(DB_PATH)
        for old, new in [("Pendiente","Sin Agendar"),("Asignada","Agendado"),("Asignadas","Agendado")]:
            conn.execute('UPDATE VMs SET "Estado"=? WHERE "Estado"=?', (new, old))
            conn.execute('UPDATE ESTADO_VMS SET "Estado_Migracion"=? WHERE "Estado_Migracion"=?', (new, old))
        conn.commit()
        conn.close()
    except Exception:
        pass

    # 1. Cargamos el detalle de clientes SIEMPRE en vivo para los desplegables
    df_clients = _load_client_snapshot()

    # ── Controls ─────────────────────────────────────────
    st.markdown("### ⚙️ Controles de Histórico")
    col_sel, col_btn1, col_btn2, col_btn3 = st.columns([1.5, 1, 1.2, 1.2])
    
    with col_sel:
        n_weeks = st.selectbox("Cantidad de semanas a mostrar:", [4, 8, 12, 16, 24], index=2, key="stats_nweeks")
    
    with col_btn1:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Actualizar", key="stats_refresh"):
            st.rerun()
            
    with col_btn2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("💾 Guardar Semana", help="Guarda los datos de la semana actual en la base de datos"):
            # Calculamos solo la semana actual (1 semana) y la guardamos
            df_actual = _calculate_weekly_data_live(1, df_clients)
            if _save_weekly_data_to_db(df_actual):
                st.success("¡Semana actual guardada con éxito!")
                st.rerun()

    with col_btn3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("⚠️ Recalcular todo", help="Borra y recalcula todo el historial basado en el estado de hoy"):
            # Calculamos todas las semanas solicitadas en vivo y reescribimos la base de datos
            df_recalc = _calculate_weekly_data_live(n_weeks, df_clients)
            if _save_weekly_data_to_db(df_recalc):
                st.success("¡Historial recalculado exitosamente!")
                st.rerun()

    st.markdown("---")

    # 2. Leemos la tabla histórica para los gráficos y resumen
    df = _load_historical_data(n_weeks)

    # Si la base de datos histórica está completamente vacía (primera vez), hacemos un "Auto-Seed"
    if df.empty and not df_clients.empty:
        st.info("💡 Histórico vacío. Calculando datos históricos por primera vez...")
        df_seed = _calculate_weekly_data_live(n_weeks, df_clients)
        _save_weekly_data_to_db(df_seed)
        df = _load_historical_data(n_weeks)

    if df.empty:
        st.info("Sin datos suficientes para generar el reporte.")
        return

    # ── Table ─────────────────────────────────────────────
    st.markdown("### 📋 Resumen Semanal Histórico")
    display_cols = ["Semana"] + [m for m in METRIC_ORDER if m in df.columns]
    df_table = df[display_cols].set_index("Semana").T
    st.dataframe(df_table, use_container_width=True)

    # ── Drill-down ────────────────────────────────────────
    st.markdown("#### 🔍 Detalle de clientes en vivo (Estado actual)")
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
        st.download_button("📥 Exportar Excel", data=excel_bytes, file_name=f"weekly_report_{date.today()}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with ec2:
        export_csv = df.drop(columns=["week_start"], errors="ignore")
        csv_bytes = export_csv.to_csv(index=False).encode()
        st.download_button("📥 Exportar CSV", data=csv_bytes, file_name=f"weekly_report_{date.today()}.csv", mime="text/csv")

    st.markdown("---")

    # ── Charts ────────────────────────────────────────────
    if not _has_plotly:
        st.warning("Instala plotly para ver los gráficos: `pip install plotly`")
        return

    st.plotly_chart(_chart_overall(df), use_container_width=True, config=_PLOTLY_CFG)
    ch1, ch2 = st.columns(2)
    with ch1:
        st.plotly_chart(_chart_notif_sched(df), use_container_width=True, config=_PLOTLY_CFG)
    with ch2:
        st.plotly_chart(_chart_windows(df), use_container_width=True, config=_PLOTLY_CFG)
'''
DESCRIPCIÓN DE ESTADOS DE ESTADÍSTICAS
Estadísticas cliente: 

Total clientes: La totalidad de clientes acumulado según las fases que llevemos
Notificados: Clientes que efectivamente ( sin rebote de correo) han recibido una comunicación de parte de Liberty
En Revisión pasa ya Clientes sin contactar : Clientes que no han sido contactados ( Pestaña "Notificaciones Clientes" Estado "Correo Rebotado"
Agendados: Ya cuentan con un registro de fecha inicial para realizar ventana. EN caso que el cliente tenga al menos una máquina en este estado, se mantendrá como Agendados. 
Migrados OK: Clientes con  todas las máquinas migradas.
Migrados Ok ( Acumulado): Sumatoria de Migrados OK semanal. 
Estadísticas Máquinas

Total máquinas: La totalidad de máquinas acumuladas según las fases que llevemos
Sin agendar: Cantidad de máquinas que aún no cuentan con una fecha de ventada registrada
Agendadas: Cantidad de máquinas que ya cuentan con un registro de fecha inicial para realizar ventana.
Migradas Ok: Máquinas con migración  exitosa que ya pasaron los 10 días desde el momento del cierre de la migración.
En seguimiento: Máquinas con migración exitosa, pero que aún están dentro de los 10 de estabilización. Fórmula: Fecha de cierre de la migración exitosa+10 días calendario.
Fallido: Sumatoria de las máquinas que tuvieron Rollback tras seguimiento (dentro de los siguientes 10 días posteriores al cierre de la migración) + Rollback Inmediato ( Durante la migración como tal)

'''