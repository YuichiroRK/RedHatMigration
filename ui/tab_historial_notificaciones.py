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


# ── Estado badge ─────────────────────────────────────────
ESTADO_COLORS = {
    "Enviado":       "#38A169",
    "Recibido":      "#3182CE",
    "Sin Respuesta": "#D69E2E",
    "Rebotado":      "#E53E3E",
}

def _badge(estado: str) -> str:
    c = ESTADO_COLORS.get(estado, "#8A95A3")
    return (f'<span style="background:{c};color:#fff;padding:2px 10px;'
            f'border-radius:20px;font-size:.72rem;font-weight:700;">{estado}</span>')


def _notif_editor(df_view: pd.DataFrame):
    """
    Section to select a notification record and edit its estado/canal/notas.
    Completely isolated to NOTIFICACIONES_CLIENTES.
    """
    with section_card("✏️ Editar Notificación"):
        st.markdown("""
        <div style="background:#EBF8FF;border:1.5px solid #90CDF4;border-radius:10px;
             padding:10px 16px;margin-bottom:14px;display:flex;gap:10px;align-items:center;">
          <span style="font-size:1.1rem;">ℹ️</span>
          <span style="font-size:.77rem;font-weight:600;color:#2A4365;">
            Solo modifica <b>Estado</b>, <b>Canal</b> y <b>Notas</b> de la notificación.
            No afecta ventanas de mantenimiento ni estados de migración.
          </span>
        </div>""", unsafe_allow_html=True)

        if "rowid" not in df_view.columns:
            # Re-load with rowid
            conn = sqlite3.connect(DB_PATH)
            try:
                df_with_id = pd.read_sql_query(
                    'SELECT rowid, * FROM NOTIFICACIONES_CLIENTES', conn
                )
            except Exception:
                df_with_id = pd.DataFrame()
            finally:
                conn.close()
            # Merge rowid into df_view by index alignment if same query
            if not df_with_id.empty:
                df_view = df_view.merge(
                    df_with_id[["rowid","Cliente","Fecha Notificación"]],
                    on=["Cliente","Fecha Notificación"], how="left"
                )

        if df_view.empty or "rowid" not in df_view.columns:
            st.info("No hay registros disponibles para editar con los filtros actuales.")
            return

        # Build a display label: "Cliente — fecha — estado"
        def _label(row):
            fecha = str(row.get("Fecha Notificación",""))[:16]
            cli   = str(row.get("Cliente",""))
            est   = str(row.get("Estado_Notificacion",""))
            return f"{cli}  ·  {fecha}  ·  {est}"

        opciones = {_label(r): r for _, r in df_view.iterrows()}
        sel_label = st.selectbox("Seleccionar registro:", list(opciones.keys()),
                                  key="hist_notif_sel")

        if not sel_label:
            return

        row = opciones[sel_label]
        rowid = int(row["rowid"]) if pd.notna(row.get("rowid")) else None
        if rowid is None:
            st.warning("No se pudo identificar el registro.")
            return

        cur_estado = str(row.get("Estado_Notificacion","Enviado"))
        cur_canal  = str(row.get("Canal_Notificacion","Email"))
        cur_notas  = str(row.get("Notas",""))
        if cur_notas in ("nan","None"): cur_notas = ""

        # Current badge
        st.markdown(
            f'<div style="margin:8px 0 14px;">Estado actual: {_badge(cur_estado)}</div>',
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns(2)
        with c1:
            est_idx   = ESTADOS_NOTIF.index(cur_estado) if cur_estado in ESTADOS_NOTIF else 0
            new_estado = st.selectbox("Nuevo Estado de la Notificación:", ESTADOS_NOTIF,
                                       index=est_idx, key="hist_new_estado")
        with c2:
            can_idx   = CANALES.index(cur_canal) if cur_canal in CANALES else 0
            new_canal  = st.selectbox("Nuevo Canal de la Notificación:", CANALES,
                                       index=can_idx, key="hist_new_canal")

        new_notas = st.text_area("Notas / Observaciones:", value=cur_notas,
                                  height=90, key="hist_new_notas",
                                  placeholder="Agrega detalles del seguimiento…")

        if st.button("💾 Guardar cambios en notificación", key="hist_save_btn",
                     type="primary", use_container_width=True):
            ok, err = _update_notificacion(rowid, new_estado, new_canal, new_notas.strip())
            if ok:
                st.success("✅ Notificación actualizada correctamente.")
                st.rerun()
            else:
                st.error(f"❌ Error: {err}")


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

    # ── Editor ────────────────────────────────────────────
    st.markdown("---")
    _notif_editor(df_view)