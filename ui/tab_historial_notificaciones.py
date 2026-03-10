"""
ui/tab_historial_notificaciones.py
Pestaña para visualizar el historial de las notificaciones enviadas a los clientes.
"""

import sqlite3
import pandas as pd
import streamlit as st
from ui.components import section_card

def _load_notificaciones() -> pd.DataFrame:
    """Carga todos los registros de notificaciones desde la base de datos."""
    conn = sqlite3.connect("migraciones.db")
    try:
        # Ordenamos por fecha descendente para ver las más recientes primero
        df = pd.read_sql_query('SELECT * FROM NOTIFICACIONES_CLIENTES ORDER BY "Fecha Notificación" DESC', conn)
        return df
    except Exception as e:
        return pd.DataFrame()
    finally:
        conn.close()

def render():
    st.markdown("## 📭 Historial de Notificaciones")
    
    df = _load_notificaciones()

    if df.empty:
        st.info("ℹ️ Aún no hay notificaciones registradas en el sistema.")
        return

    # ── 1. Filtros de Búsqueda ──
    with section_card("🔍 Filtros de Búsqueda"):
        c1, c2, c3 = st.columns(3)
        
        with c1:
            clientes = sorted(df["Cliente"].dropna().unique().tolist())
            cliente_sel = st.selectbox("Filtrar por Cliente:", ["— Todos —"] + clientes)
            
        with c2:
            estados = df["Estado_Notificacion"].dropna().unique().tolist()
            estado_sel = st.multiselect("Estado del Envío:", estados)
            
        with c3:
            canales = df["Canal_Notificacion"].dropna().unique().tolist()
            canal_sel = st.multiselect("Canal de Comunicación:", canales)

    # ── 2. Aplicar Filtros al DataFrame ──
    df_view = df.copy()
    if cliente_sel != "— Todos —":
        df_view = df_view[df_view["Cliente"] == cliente_sel]
    if estado_sel:
        df_view = df_view[df_view["Estado_Notificacion"].isin(estado_sel)]
    if canal_sel:
        df_view = df_view[df_view["Canal_Notificacion"].isin(canal_sel)]

    # ── 3. Tarjetas de Resumen (Métricas) ──
    with section_card("📊 Resumen de Notificaciones"):
        if not df_view.empty:
            m1, m2, m3, m4 = st.columns(4)
            
            total_registros = len(df_view)
            exitosos = len(df_view[df_view["Estado_Notificacion"].isin(["Enviado", "Recibido"])])
            fallidos = len(df_view[df_view["Estado_Notificacion"].isin(["Rebotado", "Sin Respuesta"])])
            canal_fav = df_view["Canal_Notificacion"].mode()[0] if not df_view["Canal_Notificacion"].empty else "N/A"
            
            m1.metric("Total Registros", total_registros)
            m2.metric("✅ Enviados/Recibidos", exitosos)
            m3.metric("⚠️ Rebotados/Sin Resp.", fallidos)
            m4.metric("📱 Canal Principal", canal_fav)
        else:
            st.warning("No hay resultados para los filtros seleccionados.")

    # ── 4. Tabla de Datos ──
    st.markdown("### 📋 Detalle de Registros")
    
    if not df_view.empty:
        # Buscador de texto libre para buscar palabras clave en las notas o creador
        busqueda = st.text_input("🔍 Buscar en notas o creador:")
        if busqueda:
            mask = df_view.astype(str).apply(lambda x: x.str.contains(busqueda, case=False, na=False)).any(axis=1)
            df_view = df_view[mask]
            
        st.markdown(
            f'<div style="font-size:.76rem;color:#8A95A3;margin-bottom:8px;">'
            f'Mostrando {len(df_view)} registros</div>',
            unsafe_allow_html=True
        )
        # Mostrar el dataframe adaptado al ancho de la pantalla
        st.dataframe(df_view, use_container_width=True, hide_index=True)