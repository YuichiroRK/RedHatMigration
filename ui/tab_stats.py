"""
ui/tab_stats.py
Estadística de Clientes + Estadística de Máquinas — dos tabs separados.
Reordenado: Históricos primero, luego tarjetas, luego detalles.
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

# ── Global rollback name sets — used by classify AND by vm_detail ──
_RB_INM = {"Rollback Inmediato", "Fallida", "RollbackInmediato"}
_RB_SEG = {"Rollback Tras Seguimiento", "RollBack", "RollbackTrasSeguimiento"}


# ──────────────────────────────────────────────────────────────
# HISTORICO SEMANAL (para VMs)
# ──────────────────────────────────────────────────────────────
def _init_historico_vms_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS HISTORICO_VMS_SEMANAL (
            week_start TEXT PRIMARY KEY, Semana TEXT,
            "Total Maquinas" INTEGER,
            "Sin Agendar" INTEGER,
            Agendadas INTEGER,
            "En Seguimiento" INTEGER,
            "Migradas OK" INTEGER,
            Fallido INTEGER,
            "Rollback Inmediato" INTEGER,
            "Rollback Tras Seguimiento" INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def _save_weekly_vms(snap: dict, week_start, label: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('''
            INSERT OR REPLACE INTO HISTORICO_VMS_SEMANAL
            (week_start, Semana, "Total Maquinas", "Sin Agendar", Agendadas,
             "En Seguimiento", "Migradas OK", Fallido,
             "Rollback Inmediato", "Rollback Tras Seguimiento")
            VALUES (?,?,?,?,?,?,?,?,?,?)
        ''', (str(week_start), label,
               snap["total"], snap["sin_agendar"], snap["agendadas"],
               snap["en_seguimiento"], snap["migradas_ok"], snap["fallido"],
               snap.get("rb_inmediato",0), snap.get("rb_seguimiento",0)))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error guardando VMs: {e}")
        return False
    finally:
        conn.close()

def _load_historical_vms(n_weeks: int) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            f'SELECT * FROM HISTORICO_VMS_SEMANAL ORDER BY week_start DESC LIMIT {n_weeks}', conn)
        if not df.empty:
            df = df.sort_values("week_start")
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

def _auto_save_week_vms():
    today      = date.today()
    week_start = today - timedelta(days=today.weekday())
    def week_label(d): return f"Sem {d.isocalendar()[1]}\n{d.strftime('%d/%m')}"
    snap = _load_vm_snapshot()
    _save_weekly_vms(snap, week_start, week_label(week_start))


# ──────────────────────────────────────────────────────────────
# HISTORICO SEMANAL (para Clientes)
# ──────────────────────────────────────────────────────────────
def _init_historico_table():
    conn = sqlite3.connect(DB_PATH)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(HISTORICO_SEMANAL)").fetchall()]
        if cols and "Sin Contactar" not in cols:
            conn.execute("DROP TABLE IF EXISTS HISTORICO_SEMANAL")
            conn.commit()
        elif cols and "Sin Respuesta" not in cols:
            conn.execute('ALTER TABLE HISTORICO_SEMANAL ADD COLUMN "Sin Respuesta" INTEGER DEFAULT 0')
            conn.commit()
    except Exception:
        pass

    conn.execute('''
        CREATE TABLE IF NOT EXISTS HISTORICO_SEMANAL (
            week_start TEXT PRIMARY KEY, Semana TEXT,
            "Total Clientes" INTEGER, Notificados INTEGER,
            "Sin Contactar" INTEGER, "Sin Respuesta" INTEGER, Agendados INTEGER,
            "Migrados OK" INTEGER, "En Seguimiento" INTEGER,
            RollBack INTEGER, Fallido INTEGER,
            "Migrados OK (acum.)" INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def _save_weekly_data_to_db(df: pd.DataFrame) -> bool:
    if df.empty:
        return False
    df_save = df.copy()
    df_save["week_start"] = df_save["week_start"].astype(str)
    conn = sqlite3.connect(DB_PATH)
    try:
        for _, row in df_save.iterrows():
            cols   = list(row.index)
            vals   = list(row.values)
            ph     = ", ".join("?" * len(vals))
            colstr = ", ".join(f'"{c}"' for c in cols)
            conn.execute(
                f'INSERT OR REPLACE INTO HISTORICO_SEMANAL ({colstr}) VALUES ({ph})',
                vals)
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error al guardar: {e}")
        return False
    finally:
        conn.close()

def _load_historical_data(n_weeks: int) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            f'SELECT * FROM HISTORICO_SEMANAL ORDER BY week_start DESC LIMIT {n_weeks}', conn)
        if not df.empty:
            df["week_start"] = pd.to_datetime(df["week_start"]).dt.date
            df = df.sort_values("week_start")
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df


# ──────────────────────────────────────────────────────────────
# CLIENT SNAPSHOT (NUEVA LÓGICA ESTRICTA DE HISTORIAL)
# ──────────────────────────────────────────────────────────────
def _load_client_snapshot() -> pd.DataFrame:
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
            FROM VMs v LEFT JOIN ESTADO_VMS e ON v.VM_ID_TM = e.VM_ID_TM
        """, conn)
    except Exception:
        df_vms = pd.DataFrame(columns=["Cliente", "Estado", "Fecha_Finalizacion"])

    try:
        df_notif = pd.read_sql_query(
            'SELECT "Cliente", "Fecha Notificación", "Estado_Notificacion" FROM NOTIFICACIONES_CLIENTES', conn)
        df_notif['Fecha Notificación'] = pd.to_datetime(df_notif['Fecha Notificación'], errors='coerce')
        df_notif_latest = df_notif.sort_values('Fecha Notificación').groupby('Cliente').last().reset_index()
        dict_latest_notif = df_notif_latest.set_index('Cliente')['Estado_Notificacion'].to_dict()
        dict_all_notifs = df_notif.groupby('Cliente')['Estado_Notificacion'].apply(lambda x: set(x.dropna())).to_dict()
    except Exception:
        dict_latest_notif = {}
        dict_all_notifs = {}

    conn.close()

    rows = []
    for cli in df_cli["Cliente"].dropna().unique():
        vms_cli   = df_vms[df_vms["Cliente"] == cli] if not df_vms.empty else pd.DataFrame()
        estados   = vms_cli["Estado"].dropna().tolist()
        total_vms = len(estados)
        vms_ok    = estados.count("Migrada OK") + estados.count("Éxito")

        estados_notif_set = dict_all_notifs.get(cli, set())
        latest_notif_est  = dict_latest_notif.get(cli)

        respuestas_efectivas = {"Agenda Confirmada", "Cliente por Contactar", "Recibido"}
        envios_realizados    = {"Correo Enviado", "Sin Respuesta", "Enviado"}

        tiene_respuesta    = bool(estados_notif_set.intersection(respuestas_efectivas))
        tiene_enviado      = bool(estados_notif_set.intersection(envios_realizados))
        sin_respuesta_flag = tiene_enviado and not tiene_respuesta
        notificado_flag    = (latest_notif_est is not None) and (latest_notif_est not in ("Correo Rebotado", "Rebotado"))
        sin_contactar_flag = (not estados_notif_set) or (latest_notif_est in ("Correo Rebotado", "Rebotado") and not sin_respuesta_flag and not tiene_respuesta)

        agendado_flag   = "Agendado" in estados
        migrado_ok_flag = (total_vms > 0) and all(e in ("Migrada OK", "Éxito") for e in estados)

        if migrado_ok_flag:
            est_cli = "Migrado OK"
        elif agendado_flag:
            est_cli = "Agendado"
        elif any(e in ("Rollback Inmediato", "Rollback Tras Seguimiento", "En Seguimiento", "Fallido", "Fallida") for e in estados):
            est_cli = "Fallido"
            for e in ("Rollback Inmediato", "Rollback Tras Seguimiento", "En Seguimiento"):
                if e in estados:
                    est_cli = e
                    break
        elif sin_respuesta_flag:
            est_cli = "Sin Respuesta"
        elif notificado_flag or tiene_respuesta:
            est_cli = "Notificado"
        else:
            est_cli = "Sin Contactar"

        fecha_resolucion = pd.NaT
        if not vms_cli.empty and "Fecha_Finalizacion" in vms_cli.columns:
            fechas = pd.to_datetime(vms_cli["Fecha_Finalizacion"].astype(str).str[:10], errors="coerce")
            if est_cli == "Migrado OK":
                fecha_resolucion = fechas.max()
            elif est_cli in ("Rollback Inmediato", "Rollback Tras Seguimiento", "En Seguimiento"):
                mask = vms_cli["Estado"] == est_cli
                if mask.any():
                    fecha_resolucion = fechas[mask].max()

        rows.append({
            "Cliente":          cli,
            "Estado_Cliente":   est_cli,
            "Total VMs":        total_vms,
            "VMs Éxito":        vms_ok,
            "Notificado":       notificado_flag,
            "Sin Contactar":    sin_contactar_flag,
            "Sin Respuesta":    sin_respuesta_flag,
            "Agendado_Flag":    agendado_flag,
            "Migrado_OK_Flag":  migrado_ok_flag,
            "Última Notif.":    latest_notif_est,
            "Fecha_Resolucion": fecha_resolucion,
        })
    return pd.DataFrame(rows)


def _get_current_week_ok_metrics(df_clients: pd.DataFrame):
    today      = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end   = week_start + timedelta(days=6)

    def _in_week(d):
        try:
            if pd.isna(d): return False
            return week_start <= d.date() <= week_end
        except: return False

    ok_wk = (len(df_clients[(df_clients["Migrado_OK_Flag"] == True) &
              df_clients["Fecha_Resolucion"].apply(_in_week)])
             if "Fecha_Resolucion" in df_clients.columns else 0)

    conn = sqlite3.connect(DB_PATH)
    try:
        r = conn.execute('SELECT "Migrados OK (acum.)" FROM HISTORICO_SEMANAL WHERE week_start=?',
                         (str(week_start - timedelta(weeks=1)),)).fetchone()
        prev_acum = int(r[0] or 0) if r else 0
    except:
        prev_acum = 0
    finally:
        conn.close()

    return ok_wk, prev_acum + ok_wk


def _calculate_weekly_data_live(n_weeks: int, df_clients: pd.DataFrame) -> pd.DataFrame:
    if df_clients.empty:
        return pd.DataFrame()

    today   = date.today()
    current = today - timedelta(days=today.weekday())
    weeks   = []
    for _ in range(n_weeks):
        weeks.append(current)
        current -= timedelta(weeks=1)
    weeks.reverse()

    def week_label(d): return f"Sem {d.isocalendar()[1]}\n{d.strftime('%d/%m')}"

    df_c               = df_clients.copy()
    total_cli          = len(df_c)
    snap_notificados   = int(df_c["Notificado"].sum())
    snap_sin_contactar = int(df_c["Sin Contactar"].sum())
    snap_sin_resp      = int(df_c["Sin Respuesta"].sum())
    snap_agendados     = int(df_c["Agendado_Flag"].sum())

    rows = []
    for wstart in weeks:
        wend  = wstart + timedelta(days=6)
        label = week_label(wstart)

        def _in_window(d):
            try: return wstart <= d.date() <= wend
            except: return False

        def _cum_window(d):
            try: return d.date() <= wend
            except: return False

        ok_wk  = len(df_c[(df_c["Migrado_OK_Flag"] == True) & df_c["Fecha_Resolucion"].apply(_in_window)])
        cum_ok = len(df_c[(df_c["Migrado_OK_Flag"] == True) & df_c["Fecha_Resolucion"].apply(_cum_window)])

        rows.append({
            "week_start":          wstart,
            "Semana":              label,
            "Total Clientes":      total_cli,
            "Notificados":         snap_notificados,
            "Sin Contactar":       snap_sin_contactar,
            "Sin Respuesta":       snap_sin_resp,
            "Agendados":           snap_agendados,
            "Migrados OK":         ok_wk,
            "Migrados OK (acum.)": cum_ok,
        })
    return pd.DataFrame(rows)


def _auto_save_week(df_clients: pd.DataFrame):
    if df_clients.empty:
        return
    today      = date.today()
    week_start = today - timedelta(days=today.weekday())
    ok_wk, ok_acum = _get_current_week_ok_metrics(df_clients)
    def week_label(d): return f"Sem {d.isocalendar()[1]}\n{d.strftime('%d/%m')}"
    row_data = pd.DataFrame([{
        "week_start":          str(week_start),
        "Semana":              week_label(week_start),
        "Total Clientes":      len(df_clients),
        "Notificados":         int(df_clients["Notificado"].sum()),
        "Sin Contactar":       int(df_clients["Sin Contactar"].sum()),
        "Sin Respuesta":       int(df_clients["Sin Respuesta"].sum()),
        "Agendados":           int(df_clients["Agendado_Flag"].sum()),
        "Migrados OK":         ok_wk,
        "Migrados OK (acum.)": ok_acum,
    }])
    _save_weekly_data_to_db(row_data)


# ──────────────────────────────────────────────────────────────
# VM SNAPSHOT
# ──────────────────────────────────────────────────────────────
def _load_vm_snapshot(fase_filter: str = None) -> dict:
    today = date.today()
    conn  = sqlite3.connect(DB_PATH)

    try:
        if fase_filter:
            total_sistema = int(pd.read_sql_query(
                'SELECT COUNT(*) AS n FROM DATABASE WHERE "Fase"=?', conn, params=(fase_filter,)
            ).iloc[0]["n"])
        else:
            total_sistema = int(pd.read_sql_query("SELECT COUNT(*) AS n FROM DATABASE", conn).iloc[0]["n"])
    except Exception:
        total_sistema = 0

    try:
        fases = pd.read_sql_query(
            'SELECT DISTINCT "Fase" FROM DATABASE WHERE "Fase" IS NOT NULL AND "Fase" != "" ORDER BY "Fase"', conn
        )["Fase"].tolist()
    except Exception:
        fases = []

    try:
        df = pd.read_sql_query("""
            SELECT v.VM_ID_TM, v.Cliente, v.StartDateTime,
                   COALESCE(e.Estado_Migracion, v.Estado, 'Sin Agendar') AS Estado,
                   e.Fecha_Ejecucion, e.Fecha_Finalizacion
            FROM VMs v LEFT JOIN ESTADO_VMS e ON v.VM_ID_TM = e.VM_ID_TM
        """, conn)
    except Exception:
        df = pd.DataFrame()

    conn.close()

    def _classify(row):
        est = str(row.get("Estado", "Sin Agendar")).strip()
        if est in ("Sin Agendar", "nan", "None", ""): return "Sin Agendar"
        if est == "Agendado": return "Agendado"
        if est in _RB_INM or est in _RB_SEG: return "Fallido"
        if est == "En Seguimiento":
            try:
                fecha_ej = pd.to_datetime(str(row["Fecha_Ejecucion"])[:10]).date()
                if today >= fecha_ej + timedelta(days=10): return "Migrada OK"
            except: pass
            return "En Seguimiento"
        if est in ("Migrada OK", "Éxito"):
            try:
                fecha_fin = pd.to_datetime(str(row["Fecha_Finalizacion"])[:10]).date()
                return "Migrada OK" if today >= fecha_fin + timedelta(days=10) else "En Seguimiento"
            except: return "Migrada OK"
        return est

    if not df.empty:
        df["_clase"] = df.apply(_classify, axis=1)
    else:
        df["_clase"] = []

    vms_en_tabla    = len(df)
    sin_agendar_ext = max(0, total_sistema - vms_en_tabla)
    sin_agendar_int = int((df["_clase"] == "Sin Agendar").sum()) if not df.empty else 0

    if not df.empty and "_clase" in df.columns:
        df_fall = df[df["_clase"] == "Fallido"]
        rb_inm  = int(df_fall["Estado"].apply(lambda e: str(e).strip() in _RB_INM).sum())
        rb_seg  = int(df_fall["Estado"].apply(lambda e: str(e).strip() in _RB_SEG).sum())
        rb_inm += int(df_fall["Estado"].apply(
            lambda e: str(e).strip() not in _RB_INM and str(e).strip() not in _RB_SEG
        ).sum())
    else:
        rb_inm = 0
        rb_seg = 0

    return {
        "total":          total_sistema,
        "sin_agendar":    sin_agendar_ext + sin_agendar_int,
        "agendadas":      int((df["_clase"] == "Agendado").sum())        if not df.empty else 0,
        "en_seguimiento": int((df["_clase"] == "En Seguimiento").sum())  if not df.empty else 0,
        "migradas_ok":    int((df["_clase"] == "Migrada OK").sum())      if not df.empty else 0,
        "fallido":        int((df["_clase"] == "Fallido").sum())         if not df.empty else 0,
        "rb_inmediato":   rb_inm,
        "rb_seguimiento": rb_seg,
        "fases":          fases,
        "df":             df,
    }


# ──────────────────────────────────────────────────────────────
# CHARTS
# ──────────────────────────────────────────────────────────────
_PLOTLY_CFG = {
    "displayModeBar": True,
    "toImageButtonOptions": {"format": "png", "filename": "stats", "height": 500, "width": 1400, "scale": 2},
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}

def _chart_overall(df):
    fig = go.Figure()
    fig.add_trace(go.Bar(y=df["Semana"], x=df["Total Clientes"], name="Total", orientation="h", marker_color="#9E9E9E", opacity=0.5))
    fig.add_trace(go.Bar(y=df["Semana"], x=df["Migrados OK (acum.)"], name="Migrados OK Acum.", orientation="h", marker_color="#1B5E20", opacity=0.85))
    fig.add_trace(go.Bar(y=df["Semana"], x=df["Migrados OK"], name="Migrados OK (semana)", orientation="h", marker_color="#4CAF50"))
    fig.update_layout(title="Overall — Clientes migrados por semana y acumulado", barmode="overlay", height=340,
                      legend=dict(orientation="h", y=-0.25), margin=dict(l=10,r=10,t=40,b=10),
                      plot_bgcolor="#FAFAFA", paper_bgcolor="#FFFFFF")
    return fig

def _chart_notif(df):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=df["Semana"], y=df["Total Clientes"], name="Total", marker_color="#1565C0", opacity=0.3), secondary_y=False)
    fig.add_trace(go.Bar(x=df["Semana"], y=df["Notificados"], name="Notificados", marker_color="#0288D1"), secondary_y=False)
    _sc_y  = df["Sin Contactar"] if "Sin Contactar" in df.columns else pd.Series([0]*len(df), index=df.index)
    _mig_wk = df["Migrados OK"] if "Migrados OK" in df.columns else pd.Series([0]*len(df), index=df.index)
    _mig_ac = df["Migrados OK (acum.)"] if "Migrados OK (acum.)" in df.columns else pd.Series([0]*len(df), index=df.index)
    fig.add_trace(go.Scatter(x=df["Semana"], y=_sc_y, name="Sin Contactar", mode="lines+markers", line=dict(color="#E53E3E", width=2)), secondary_y=True)
    fig.add_trace(go.Bar(x=df["Semana"], y=_mig_wk, name="Migrados OK (semana)", marker_color="#4CAF50", opacity=0.7), secondary_y=False)
    fig.add_trace(go.Scatter(x=df["Semana"], y=_mig_ac, name="Migrados OK Acum.", mode="lines+markers", line=dict(color="#1B5E20", width=2, dash="dot")), secondary_y=True)
    fig.update_layout(title="Notificaciones & Seguimiento", barmode="overlay", height=300,
                      legend=dict(orientation="h", y=-0.35, font_size=10), margin=dict(l=10,r=10,t=40,b=10),
                      plot_bgcolor="#FAFAFA", paper_bgcolor="#FFFFFF")
    return fig

def _chart_vm_donut(snap):
    labels = ["Sin Agendar", "Agendadas", "En Seguimiento", "Migradas OK", "Fallido"]
    values = [snap["sin_agendar"], snap["agendadas"], snap["en_seguimiento"], snap["migradas_ok"], snap["fallido"]]
    colors = ["#D69E2E", "#3182CE", "#805AD5", "#2E7D32", "#C53030"]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.55,
        marker=dict(colors=colors),
        textinfo="label+percent", hoverinfo="label+value",
    ))
    fig.update_layout(title="Distribución de VMs", height=320,
                      legend=dict(orientation="h", y=-0.15, font_size=10),
                      margin=dict(l=10,r=10,t=40,b=10), paper_bgcolor="#FFFFFF")
    return fig


# ──────────────────────────────────────────────────────────────
# EXPORT
# ──────────────────────────────────────────────────────────────

# Columnas semanales a exportar (sin basura interna)
_WEEKLY_KEEP = ["Semana", "Total Clientes", "Notificados", "Sin Contactar",
                "Sin Respuesta", "Agendados", "Migrados OK", "Migrados OK (acum.)"]
# Columnas internas a eliminar del detalle de clientes
_CLI_DROP    = ["_d_res", "Fecha_Resolucion", "Agendado_Flag", "Migrado_OK_Flag",
                "En Seguimiento", "RollBack", "Fallido"]

# Labels de display para estados de VM (col. C de la imagen)
_VM_STATE_LABELS = {
    "Sin Agendar":               "Sin Agendar",
    "Agendado":                  "Agendada",
    "En Seguimiento":            "Ventana exitosa — En Seguimiento (10 días)",
    "Migrada OK":                "Migrada OK (ya pasaron los 10 días)",
    "Fallido":                   "Fallido",
    "Rollback Inmediato":        "Ventana NO exitosa — Rollback Inmediato (vuelve a cola)",
    "Rollback Tras Seguimiento": "Rollback durante seguimiento (10 días) (vuelve a cola)",
}


def _build_vm_detail_df(df_vms: pd.DataFrame) -> pd.DataFrame:
    """Construye df de VMs con Estado_Display legible para exportar."""
    df = df_vms.copy()
    if "_clase" in df.columns:
        df["Estado_Display"] = df["_clase"].map(lambda c: _VM_STATE_LABELS.get(c, c))
        mask_f = df["_clase"] == "Fallido"
        df.loc[mask_f & df["Estado"].apply(lambda e: str(e).strip() in _RB_INM),
               "Estado_Display"] = _VM_STATE_LABELS["Rollback Inmediato"]
        df.loc[mask_f & df["Estado"].apply(lambda e: str(e).strip() in _RB_SEG),
               "Estado_Display"] = _VM_STATE_LABELS["Rollback Tras Seguimiento"]
        df.drop(columns=["_clase"], inplace=True, errors="ignore")
    prio = ["VM_ID_TM", "Cliente", "Estado_Display", "Fecha_Ejecucion", "Fecha_Finalizacion"]
    rest = [c for c in df.columns if c not in prio and c != "Estado"]
    return df[[c for c in prio + rest if c in df.columns]]


def _to_excel(df_weekly, df_clients, df_vms=None):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Semanal — solo columnas relevantes
        keep_wk = [c for c in _WEEKLY_KEEP if c in df_weekly.columns]
        df_weekly[keep_wk].to_excel(writer, index=False, sheet_name="Clientes Semanal")

        # Detalle clientes — sin columnas internas/legacy
        df_clients.drop(columns=_CLI_DROP, errors="ignore").to_excel(
            writer, index=False, sheet_name="Detalle Clientes")

        # Detalle VMs con labels legibles
        if df_vms is not None and not df_vms.empty:
            _build_vm_detail_df(df_vms).to_excel(writer, index=False, sheet_name="Detalle VMs")

        for sn in writer.sheets:
            ws = writer.sheets[sn]
            for col in ws.columns:
                max_len = max(len(str(c.value or "")) for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 52)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────
# UI HELPERS / DRILL-DOWN
# ──────────────────────────────────────────────────────────────
_ESTADO_COLOR = {
    "Migrado OK": "#2E7D32", "Agendado": "#3182CE",
    "En Seguimiento": "#805AD5", "Sin Agendar": "#D69E2E",
    "Rollback Tras Seguimiento": "#E53E3E", "Rollback Inmediato": "#C53030",
    "Sin Respuesta": "#718096", "Notificado": "#0288D1", "Sin Contactar": "#E53E3E"
}

def _metric_card(icon, label, value, color, subtitle=""):
    sub = f'<div style="font-size:.62rem;color:#A0AEC0;margin-top:1px;">{subtitle}</div>' if subtitle else ""
    return (
        f'<div style="background:#fff;border:1px solid #E2E6ED;border-radius:12px;'
        f'padding:14px 12px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,.05);'
        f'border-bottom:4px solid {color};">'
        f'<div style="font-size:1.3rem;">{icon}</div>'
        f'<div style="font-size:.68rem;color:#8A95A3;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:.05em;margin:4px 0 2px;">{label}</div>'
        f'<div style="font-size:1.8rem;font-weight:800;color:{color};line-height:1.1;">{value}</div>'
        f'{sub}</div>'
    )

def _prog(label, pct, color):
    return (
        f'<div style="margin:5px 0 10px;">'
        f'<div style="font-size:.74rem;font-weight:600;color:#4A5568;margin-bottom:3px;">'
        f'{label} ({pct}%)</div>'
        f'<div style="height:8px;background:#E2E6ED;border-radius:99px;overflow:hidden;">'
        f'<div style="width:{min(pct,100)}%;height:100%;background:{color};border-radius:99px;"></div>'
        f'</div></div>'
    )

def _cli_row(row, color: str):
    vms_s   = (f"{row['VMs Éxito']}/{row['Total VMs']} VMs migradas"
               if row["Total VMs"] > 0 else "Sin VMs registradas")
    notif_s = (f"Última notif: {row['Última Notif.']}"
               if pd.notna(row["Última Notif."]) else "Sin notificación")
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
        f'{row["Estado_Cliente"]}</span></div>',
        unsafe_allow_html=True)

def _client_detail(metric: str, df_clients: pd.DataFrame):
    if metric == "Total Clientes":
        df_show = df_clients.copy()
    elif metric == "Notificados":
        df_show = df_clients[df_clients["Notificado"] == True].copy()
    elif metric == "Sin Contactar":
        df_show = df_clients[df_clients["Sin Contactar"] == True].copy()
    elif metric == "Sin Respuesta":
        df_show = df_clients[df_clients["Sin Respuesta"] == True].copy()
    elif metric == "Agendados":
        df_show = df_clients[df_clients["Agendado_Flag"] == True].copy()
    elif metric == "Migrados OK":
        df_show = df_clients[df_clients["Migrado_OK_Flag"] == True].copy()
    else:
        df_show = df_clients[df_clients["Estado_Cliente"] == metric].copy()

    if df_show.empty:
        st.info(f"Sin clientes en **{metric}** actualmente.")
        return

    with st.expander(f"👥 {len(df_show)} cliente(s) — {metric}", expanded=False):
        for _, row in df_show.iterrows():
            est   = row["Estado_Cliente"]
            color = _ESTADO_COLOR.get(est, "#9E9E9E")
            _cli_row(row, color)


# ──────────────────────────────────────────────────────────────
# VM DETAIL HELPERS
# ──────────────────────────────────────────────────────────────

# Labels y metadatos para el detalle por estado de VMs
_VM_META = {
    "Sin Agendar":               {"color": "#D69E2E", "icon": "⏳",
                                  "label": "Sin Agendar"},
    "Agendado":                  {"color": "#3182CE", "icon": "🔵",
                                  "label": "Agendada"},
    "En Seguimiento":            {"color": "#805AD5", "icon": "🔍",
                                  "label": "Ventana exitosa — En Seguimiento (10 días)"},
    "Migrada OK":                {"color": "#2E7D32", "icon": "✅",
                                  "label": "Migrada OK (ya pasaron los 10 días)"},
    "Fallido":                   {"color": "#C53030", "icon": "❌",
                                  "label": "Fallido"},
    "Rollback Inmediato":        {"color": "#E53E3E", "icon": "⚡",
                                  "label": "Ventana NO exitosa — Rollback Inmediato"},
    "Rollback Tras Seguimiento": {"color": "#DD6B20", "icon": "↩️",
                                  "label": "Rollback durante seguimiento (10 días)"},
}


def _reset_vm_to_queue(vm_id: str) -> bool:
    """Borra ESTADO_VMS y resetea VMs.Estado=Sin Agendar → VM vuelve a cola de agendamiento."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('DELETE FROM ESTADO_VMS WHERE "VM_ID_TM"=?', (vm_id,))
        conn.execute('UPDATE VMs SET "Estado"=? WHERE "VM_ID_TM"=?', ("Sin Agendar", vm_id))
        conn.commit()
        return True
    except Exception as ex:
        st.error(f"Error al reingresar VM: {ex}")
        return False
    finally:
        conn.close()


def _load_sin_agendar_vms() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        df_db = pd.read_sql_query(
            'SELECT "VM_ID_TM", "CUSTOMER_Name_SCCD-TM" AS Cliente FROM DATABASE', conn)
        try:
            df_vms = pd.read_sql_query('SELECT VM_ID_TM, Cliente, Estado FROM VMs', conn)
            vms_ids   = set(df_vms["VM_ID_TM"].dropna().tolist())
            df_not_in = df_db[~df_db["VM_ID_TM"].isin(vms_ids)].copy()
            df_not_in["Motivo"] = "No en tabla VMs"
            df_not_in["Estado"] = "Sin Agendar"
            df_in_sa  = df_vms[df_vms["Estado"].isin(["Sin Agendar","","nan","None"]) |
                                df_vms["Estado"].isna()].copy()
            df_in_sa["Motivo"] = "Sin Agendar en VMs"
            combined = pd.concat([
                df_not_in[["VM_ID_TM","Cliente","Estado","Motivo"]],
                df_in_sa[["VM_ID_TM","Cliente","Estado","Motivo"]]
            ], ignore_index=True).drop_duplicates("VM_ID_TM")
            return combined
        except:
            df_db["Motivo"] = "No en tabla VMs"
            df_db["Estado"] = "Sin Agendar"
            return df_db
    except:
        return pd.DataFrame()
    finally:
        conn.close()


def _vm_detail(clase: str, df: pd.DataFrame):
    meta  = _VM_META.get(clase, {"color": "#9E9E9E", "icon": "•", "label": clase})
    label = meta.get("label", clase)
    is_rb = clase in ("Rollback Inmediato", "Rollback Tras Seguimiento")

    if clase == "Sin Agendar":
        df_show = _load_sin_agendar_vms()
    elif clase == "Rollback Inmediato":
        if df.empty: st.info(f"Sin VMs en **{label}**."); return
        df_show = df[df["_clase"] == "Fallido"].copy()
        df_show = df_show[df_show["Estado"].apply(lambda e: str(e).strip() in _RB_INM)]
    elif clase == "Rollback Tras Seguimiento":
        if df.empty: st.info(f"Sin VMs en **{label}**."); return
        df_show = df[df["_clase"] == "Fallido"].copy()
        df_show = df_show[df_show["Estado"].apply(lambda e: str(e).strip() in _RB_SEG)]
    else:
        if df.empty: st.info(f"Sin VMs en **{label}**."); return
        df_show = df[df["_clase"] == clase] if "_clase" in df.columns else df

    if df_show.empty:
        st.info(f"Sin VMs en **{label}** actualmente."); return

    exp_title = f"{meta['icon']} {len(df_show)} VM(s) — {label}"
    if is_rb:
        exp_title += "  ↪ vuelve a cola"

    with st.expander(exp_title, expanded=False):
        if is_rb:
            st.markdown(
                '<div style="background:#FFF5F5;border:1px solid #FC8181;border-radius:8px;'
                'padding:8px 12px;font-size:.75rem;color:#C53030;margin-bottom:8px;">'
                '🔄 Estas VMs <b>vuelven a entrar en cola de agendamiento</b>. '
                'Presiona ↩️ para limpiar el estado y permitir re-agendar.</div>',
                unsafe_allow_html=True)

        show_cols = [c for c in ["VM_ID_TM","Cliente","Estado","Motivo",
                                  "Fecha_Ejecucion","Fecha_Finalizacion"]
                     if c in df_show.columns]
        st.dataframe(df_show[show_cols] if show_cols else df_show,
                     use_container_width=True, hide_index=True)

        if is_rb and "VM_ID_TM" in df_show.columns:
            st.markdown("**↩️ Reingresar a cola de agendamiento:**")
            vm_list = df_show["VM_ID_TM"].tolist()
            for i in range(0, len(vm_list), 4):
                q_cols = st.columns(min(4, len(vm_list) - i))
                for q_col, vid in zip(q_cols, vm_list[i:i+4]):
                    with q_col:
                        if st.button(f"↩️ {vid}", key=f"rq_{clase[:3]}_{vid}",
                                     use_container_width=True,
                                     help="Limpiar rollback y volver a agendar"):
                            if _reset_vm_to_queue(str(vid)):
                                st.success(f"✅ {vid} lista para re-agendarse.")
                                st.rerun()


# ──────────────────────────────────────────────────────────────
# TABS RENDER
# ──────────────────────────────────────────────────────────────
def _render_clientes(df_clients: pd.DataFrame):
    # ========================================================
    # 1. HISTÓRICO Y GRÁFICOS
    # ========================================================
    st.markdown("### 📈 Histórico semanal y gráficos")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        n_weeks = st.selectbox("Semanas a mostrar:", [4, 8, 12, 16, 24], index=2, key="stats_nweeks")
    with c2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("⚠️ Recalcular todo", key="stats_recalc"):
            df_rc = _calculate_weekly_data_live(n_weeks, df_clients)
            if _save_weekly_data_to_db(df_rc):
                st.success("¡Historial recalculado!")
                st.rerun()
    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Actualizar vista", key="stats_refresh"):
            st.rerun()

    df_hist = _load_historical_data(n_weeks)

    if df_hist.empty:
        st.info("Sin datos históricos aún. Se guardará automáticamente al final de cada semana.")
    else:
        TABLE_COLS = ["Semana", "Total Clientes", "Notificados", "Sin Contactar", "Sin Respuesta",
                      "Agendados", "Migrados OK", "Migrados OK (acum.)"]
        disp_cols = [c for c in TABLE_COLS if c in df_hist.columns]
        st.dataframe(df_hist[disp_cols].set_index("Semana").T, use_container_width=True)

        if _has_plotly:
            c_ch1, c_ch2 = st.columns(2)
            with c_ch1:
                st.plotly_chart(_chart_overall(df_hist), use_container_width=True, config=_PLOTLY_CFG)
            with c_ch2:
                st.plotly_chart(_chart_notif(df_hist), use_container_width=True, config=_PLOTLY_CFG)

        ec1, ec2, _ = st.columns([1, 1, 4])
        with ec1:
            st.download_button("📥 Excel", data=_to_excel(df_hist, df_clients),
                               file_name=f"clientes_{date.today()}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with ec2:
            keep_wk = [c for c in _WEEKLY_KEEP if c in df_hist.columns]
            csv = df_hist[keep_wk].to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV", data=csv, file_name=f"clientes_{date.today()}.csv", mime="text/csv")

    st.markdown("---")

    # ========================================================
    # 2. TARJETAS DE MÉTRICAS
    # ========================================================
    st.markdown("### 📊 Resumen Actual")

    total    = len(df_clients)
    notif    = int(df_clients["Notificado"].sum())
    sin_c    = int(df_clients["Sin Contactar"].sum())
    sin_resp = int(df_clients["Sin Respuesta"].sum())
    agend    = int(df_clients["Agendado_Flag"].sum())
    ok_wk, ok_acum = _get_current_week_ok_metrics(df_clients)

    cards = [
        ("🏢", "Total Clientes",      total,    "#FF7800", "en sistema"),
        ("📨", "Notificados",         notif,    "#0288D1", "último estado ≠ rebotado"),
        ("⚠️", "Sin Contactar",       sin_c,    "#E53E3E", "sin notif. o rebotado"),
        ("🔕", "Sin Respuesta",       sin_resp, "#718096", "enviado sin respuesta firme"),
        ("📅", "Agendados",           agend,    "#3182CE", "≥1 VM con ventana"),
        ("✅", "Migrados OK",         ok_wk,    "#2E7D32", "concluidos esta semana"),
        ("📈", "Migrados OK (Acum.)", ok_acum,  "#1B5E20", "total histórico"),
    ]

    cols = st.columns(len(cards))
    for col, (icon, label, val, color, sub) in zip(cols, cards):
        col.markdown(_metric_card(icon, label, val, color, sub), unsafe_allow_html=True)

    pct_notif = round(notif / total * 100, 1) if total else 0
    pct_ok    = round(ok_acum / total * 100, 1) if total else 0
    st.markdown(
        _prog(f"📨 Notificados — {notif}/{total}", pct_notif, "#0288D1")
        + _prog(f"✅ Migrados OK (Total) — {ok_acum}/{total}", pct_ok, "#2E7D32"),
        unsafe_allow_html=True,
    )

    # ========================================================
    # 3. DRILL-DOWN DETALLES
    # ========================================================
    st.markdown("#### 🔍 Detalle de clientes")
    _client_detail("Sin Contactar", df_clients)
    _client_detail("Sin Respuesta", df_clients)
    _client_detail("Agendados", df_clients)
    _client_detail("Notificados", df_clients)
    _client_detail("Migrados OK", df_clients)


def _render_maquinas():
    snap_all = _load_vm_snapshot()
    fase_sel = None
    if snap_all["fases"]:
        col_fase, _ = st.columns([1, 3])
        with col_fase:
            fase_sel = st.selectbox("🔖 Filtrar por Fase:", ["— Todas las fases —"] + snap_all["fases"],
                                    key="vm_fase_filter")
            if fase_sel == "— Todas las fases —":
                fase_sel = None

    snap   = _load_vm_snapshot(fase_sel) if fase_sel else snap_all
    total  = snap["total"]
    sin_ag = snap["sin_agendar"]
    agend  = snap["agendadas"]
    en_seg = snap["en_seguimiento"]
    mig_ok = snap["migradas_ok"]
    fall   = snap["fallido"]
    rb_inm = snap.get("rb_inmediato", 0)
    rb_seg = snap.get("rb_seguimiento", 0)
    df_vms = snap["df"]

    # ========================================================
    # 1. HISTÓRICO Y GRÁFICOS
    # ========================================================
    st.markdown("### 📈 Histórico semanal de Máquinas")
    hc1, hc2, _ = st.columns([1.5, 1, 3])
    with hc1:
        n_wk_vm = st.selectbox("Semanas:", [4, 8, 12, 16, 24], index=2, key="vm_nweeks")
    with hc2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Actualizar", key="vm_hist_refresh"):
            st.rerun()

    df_vh = _load_historical_vms(n_wk_vm)

    if df_vh.empty:
        st.info("Sin datos históricos aún. Se guarda automáticamente cada vez que visitas esta página.")
    else:
        VM_TABLE_COLS = ["Semana", "Total Maquinas", "Sin Agendar", "Agendadas",
                         "En Seguimiento", "Migradas OK", "Fallido",
                         "Rollback Inmediato", "Rollback Tras Seguimiento"]
        disp = [c for c in VM_TABLE_COLS if c in df_vh.columns]
        st.dataframe(df_vh[disp].set_index("Semana").T, use_container_width=True)

        if _has_plotly and not df_vh.empty:
            fig_vm = go.Figure()
            fig_vm.add_trace(go.Bar(x=df_vh["Semana"], y=df_vh.get("Sin Agendar",               pd.Series()), name="Sin Agendar",      marker_color="#D69E2E"))
            fig_vm.add_trace(go.Bar(x=df_vh["Semana"], y=df_vh.get("Agendadas",                 pd.Series()), name="Agendadas",        marker_color="#3182CE"))
            fig_vm.add_trace(go.Bar(x=df_vh["Semana"], y=df_vh.get("En Seguimiento",            pd.Series()), name="En Seguimiento",   marker_color="#805AD5"))
            fig_vm.add_trace(go.Bar(x=df_vh["Semana"], y=df_vh.get("Migradas OK",               pd.Series()), name="Migradas OK",      marker_color="#2E7D32"))
            fig_vm.add_trace(go.Bar(x=df_vh["Semana"], y=df_vh.get("Rollback Inmediato",        pd.Series()), name="RB Inmediato",     marker_color="#E53E3E"))
            fig_vm.add_trace(go.Bar(x=df_vh["Semana"], y=df_vh.get("Rollback Tras Seguimiento", pd.Series()), name="RB Tras Seg.",     marker_color="#DD6B20"))
            fig_vm.update_layout(
                title="Estado de Máquinas por Semana",
                barmode="stack", height=360,
                legend=dict(orientation="h", y=-0.3, font_size=10),
                margin=dict(l=10,r=10,t=40,b=10),
                plot_bgcolor="#FAFAFA", paper_bgcolor="#FFFFFF",
            )
            st.plotly_chart(fig_vm, use_container_width=True, config=_PLOTLY_CFG)

        # Download: histórico + detalle VMs con labels legibles
        hd1, hd2, _ = st.columns([1,1,4])
        with hd1:
            _buf_h = io.BytesIO()
            with pd.ExcelWriter(_buf_h, engine="openpyxl") as _w:
                df_vh[disp].to_excel(_w, index=False, sheet_name="Histórico VMs")
                if not df_vms.empty:
                    _build_vm_detail_df(df_vms).to_excel(_w, index=False, sheet_name="Detalle VMs Actual")
                for _sn in _w.sheets:
                    _ws = _w.sheets[_sn]
                    for _c in _ws.columns:
                        _ws.column_dimensions[_c[0].column_letter].width = min(
                            max(len(str(_x.value or "")) for _x in _c) + 4, 52)
            st.download_button("📥 Excel (histórico + detalle)", data=_buf_h.getvalue(),
                               file_name=f"historico_vms_{date.today()}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with hd2:
            st.download_button("📥 CSV histórico", data=df_vh[disp].to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"historico_vms_{date.today()}.csv", mime="text/csv")

    st.markdown("---")

    # ========================================================
    # 2. TARJETAS DE MÉTRICAS
    # ========================================================
    st.markdown("### 📊 Resumen Actual")
    cards = [
        ("🗃️", "Total Máquinas",  total,  "#FF7800", "en DATABASE"),
        ("⏳", "Sin Agendar",     sin_ag, "#D69E2E", "sin fecha de ventana"),
        ("📅", "Agendadas",       agend,  "#3182CE", "con ventana registrada"),
        ("🔍", "En Seguimiento",  en_seg, "#805AD5", "estabilización ≤10 días"),
        ("✅", "Migradas OK",     mig_ok, "#2E7D32", "exitosa, +10 días"),
    ]
    cols = st.columns(len(cards))
    for col, (icon, label, val, color, sub) in zip(cols, cards):
        col.markdown(_metric_card(icon, label, val, color, sub), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    _, _, _, _, fall_col = st.columns(5)
    fall_col.markdown(_metric_card("❌", "Fallido", fall, "#C53030", "total rollbacks"), unsafe_allow_html=True)

    sb1, sb2, sb3, sb4, sb_fall = st.columns(5)
    with sb_fall:
        st.markdown(
            f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:4px;">'
            f'<div style="background:#FFF5F5;border:1.5px solid #FC8181;border-radius:10px;'
            f'padding:8px 6px;text-align:center;">'
            f'<div style="font-size:.58rem;color:#C53030;font-weight:700;text-transform:uppercase;letter-spacing:.04em;">Rollback\nInmediato</div>'
            f'<div style="font-size:1.4rem;font-weight:800;color:#C53030;">{rb_inm}</div>'
            f'<div style="font-size:.58rem;color:#A0AEC0;">migración</div></div>'
            f'<div style="background:#FFF5F5;border:1.5px solid #ED8936;border-radius:10px;'
            f'padding:8px 6px;text-align:center;">'
            f'<div style="font-size:.58rem;color:#DD6B20;font-weight:700;text-transform:uppercase;letter-spacing:.04em;">Rollback\nTras Seg.</div>'
            f'<div style="font-size:1.4rem;font-weight:800;color:#DD6B20;">{rb_seg}</div>'
            f'<div style="font-size:.58rem;color:#A0AEC0;">seguimiento</div></div>'
            f'</div>',
            unsafe_allow_html=True)

    def pct(v): return round(v / total * 100, 1) if total else 0
    st.markdown(
        _prog(f"📅 Agendadas — {agend}/{total}", pct(agend), "#3182CE")
        + _prog(f"✅ Migradas OK — {mig_ok}/{total}", pct(mig_ok), "#2E7D32")
        + _prog(f"❌ Fallido total — {fall}/{total}", pct(fall), "#C53030"),
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div style="background:#EBF8FF;border:1px solid #90CDF4;border-radius:8px;'
        'padding:8px 14px;font-size:.75rem;color:#2B6CB0;margin:6px 0 12px;">'
        '📌 <b>En Seguimiento</b>: migración exitosa dentro de los 10 días de estabilización. '
        'Pasa automáticamente a <b>Migrada OK</b> al cumplirse el plazo. '
        '<b>Rollback Inmediato</b>: fallo durante la migración. '
        '<b>Rollback Tras Seguimiento</b>: fallo durante la estabilización.</div>',
        unsafe_allow_html=True,
    )

    # ========================================================
    # 3. DRILL-DOWN DETALLES
    # ========================================================
    if _has_plotly and total > 0:
        col_pie, col_drill = st.columns([1, 1.4])
        with col_pie:
            st.plotly_chart(_chart_vm_donut(snap), use_container_width=True, config=_PLOTLY_CFG)
        with col_drill:
            st.markdown("#### 🔍 Detalle por estado")
            for clase in ["Sin Agendar", "Agendado", "En Seguimiento", "Migrada OK",
                          "Rollback Inmediato", "Rollback Tras Seguimiento"]:
                _vm_detail(clase, df_vms)
    else:
        st.markdown("#### 🔍 Detalle por estado")
        for clase in ["Sin Agendar", "Agendado", "En Seguimiento", "Migrada OK",
                      "Rollback Inmediato", "Rollback Tras Seguimiento"]:
            _vm_detail(clase, df_vms)


# ──────────────────────────────────────────────────────────────
# MAIN RENDER
# ──────────────────────────────────────────────────────────────
def render():
    st.markdown("## 📊 Informes de Migración")

    _init_historico_table()
    _init_historico_vms_table()

    try:
        conn = sqlite3.connect(DB_PATH)
        for old, new in [("Pendiente","Sin Agendar"),("Asignada","Agendado"),("Asignadas","Agendado")]:
            conn.execute('UPDATE VMs SET "Estado"=? WHERE "Estado"=?', (new, old))
            conn.execute('UPDATE ESTADO_VMS SET "Estado_Migracion"=? WHERE "Estado_Migracion"=?', (new, old))
        conn.commit()
        conn.close()
    except Exception:
        pass

    df_clients = _load_client_snapshot()
    _auto_save_week(df_clients)
    _auto_save_week_vms()

    tab_cli, tab_vm = st.tabs(["👥 Informes de Clientes", "🖥️ Informes de Máquinas Virtuales"])

    with tab_cli:
        if df_clients.empty:
            st.info("Sin datos de clientes.")
        else:
            _render_clientes(df_clients)

    with tab_vm:
        _render_maquinas()