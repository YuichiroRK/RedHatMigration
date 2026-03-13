"""
ui/tab_historial_notificaciones.py
Historial de notificaciones + editor de estado/notas de una notificación.
Solo toca NOTIFICACIONES_CLIENTES — no mezcla con VMs ni ESTADO_VMS.
"""

import sqlite3
import pandas as pd
import streamlit as st
from ui.components import section_card

DB_PATH = "migraciones.db"

ESTADOS_NOTIF = ["Enviado", "Recibido", "Sin Respuesta", "Rebotado"]
CANALES       = ["Email", "Teléfono", "Reunión Teams", "WhatsApp", "Otro"]


def _load_notificaciones() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(
            'SELECT * FROM NOTIFICACIONES_CLIENTES ORDER BY "Fecha Notificación" DESC', conn
        )
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


def _update_notificacion(rowid: int, nuevo_estado: str, nuevo_canal: str,
                          nuevas_notas: str) -> tuple[bool, str]:
    """
    Updates Estado_Notificacion, Canal_Notificacion and Notas for a given rowid.
    Only touches NOTIFICACIONES_CLIENTES.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """UPDATE NOTIFICACIONES_CLIENTES
               SET "Estado_Notificacion" = ?,
                   "Canal_Notificacion"  = ?,
                   "Notas"               = ?
               WHERE rowid = ?""",
            (nuevo_estado, nuevo_canal, nuevas_notas, rowid),
        )
        conn.commit()
        conn.close()
        return True, ""
    except Exception as e:
        return False, str(e)


def render():
    st.markdown("## 📭 Historial de Notificaciones")

    df = _load_notificaciones()

    if df.empty:
        st.info("ℹ️ Aún no hay notificaciones registradas en el sistema.")
        return

    # ── Filtros ───────────────────────────────────────────
    with section_card("🔍 Filtros de Búsqueda"):
        c1, c2, c3 = st.columns(3)
        with c1:
            clientes    = sorted(df["Cliente"].dropna().unique().tolist())
            cliente_sel = st.selectbox("Filtrar por Cliente:", ["— Todos —"] + clientes,
                                        key="hist_cli")
        with c2:
            estados_col = df["Estado_Notificacion"].dropna().unique().tolist()
            estado_sel  = st.multiselect("Estado del Envío:", estados_col, key="hist_est")
        with c3:
            canales_col = df["Canal_Notificacion"].dropna().unique().tolist()
            canal_sel   = st.multiselect("Canal:", canales_col, key="hist_can")

    # ── Aplicar filtros ───────────────────────────────────
    df_view = df.copy()
    if cliente_sel != "— Todos —":
        df_view = df_view[df_view["Cliente"] == cliente_sel]
    if estado_sel:
        df_view = df_view[df_view["Estado_Notificacion"].isin(estado_sel)]
    if canal_sel:
        df_view = df_view[df_view["Canal_Notificacion"].isin(canal_sel)]

    # ── Métricas ──────────────────────────────────────────
    with section_card("📊 Resumen"):
        if not df_view.empty:
            m1, m2, m3, m4 = st.columns(4)
            total      = len(df_view)
            exitosos   = len(df_view[df_view["Estado_Notificacion"].isin(["Enviado","Recibido"])])
            fallidos   = len(df_view[df_view["Estado_Notificacion"].isin(["Rebotado","Sin Respuesta"])])
            canal_fav  = df_view["Canal_Notificacion"].mode()[0] if not df_view["Canal_Notificacion"].empty else "N/A"
            m1.metric("Total Registros",        total)
            m2.metric("✅ Enviados/Recibidos",   exitosos)
            m3.metric("⚠️ Rebotados/Sin Resp.", fallidos)
            m4.metric("📱 Canal Principal",      canal_fav)
        else:
            st.warning("No hay resultados para los filtros seleccionados.")

    # ── Tabla ─────────────────────────────────────────────
    st.markdown("### 📋 Detalle de Registros")
    if not df_view.empty:
        busqueda = st.text_input("🔍 Buscar en notas o creador:", key="hist_busq")
        if busqueda:
            mask    = df_view.astype(str).apply(
                lambda x: x.str.contains(busqueda, case=False, na=False)).any(axis=1)
            df_view = df_view[mask]
        st.markdown(
            f'<div style="font-size:.76rem;color:#8A95A3;margin-bottom:8px;">'
            f'Mostrando {len(df_view)} registros</div>', unsafe_allow_html=True)
        st.dataframe(df_view, use_container_width=True, hide_index=True)