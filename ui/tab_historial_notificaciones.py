"""
ui/tab_historial_notificaciones.py
Historial de notificaciones + editor de estado/notas de una notificación.
Solo toca NOTIFICACIONES_CLIENTES — no mezcla con VMs ni ESTADO_VMS.
"""

import io
import sqlite3
from datetime import date
import pandas as pd
import streamlit as st
from ui.components import section_card

DB_PATH = "migraciones.db"

ESTADOS_POR_CANAL = {
    "Email": [
        "Correo Enviado",
        "Correo Rebotado",
        "Cliente por Contactar",
        "Agenda Confirmada",
        "Sin Respuesta",
    ],
    "Contacto Directo": [
        "Cliente por Contactar",
        "Agenda Confirmada",
    ],
}

# ── Estado badge ─────────────────────────────────────────
ESTADO_COLORS = {
    "Correo Enviado":        "#38A169",
    "Correo Rebotado":       "#E53E3E",
    "Cliente por Contactar": "#D69E2E",
    "Agenda Confirmada":     "#3182CE",
    "Sin Respuesta":         "#718096",
}

def _badge(estado: str) -> str:
    c = ESTADO_COLORS.get(estado, "#8A95A3")
    return (f'<span style="background:{c};color:#fff;padding:2px 10px;'
            f'border-radius:20px;font-size:.72rem;font-weight:700;">{estado}</span>')


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

        cur_estado = str(row.get("Estado_Notificacion", "Correo Enviado"))
        cur_canal  = str(row.get("Canal_Notificacion", "Email"))
        cur_notas  = str(row.get("Notas",""))
        if cur_notas in ("nan","None"): cur_notas = ""

        # Validate channel against available options, default to Email if invalid
        if cur_canal not in ESTADOS_POR_CANAL:
            cur_canal = "Email"

        # Current badge
        st.markdown(
            f'<div style="margin:8px 0 14px;">Estado actual: {_badge(cur_estado)}</div>',
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns(2)
        
        with c2:
            canales_disponibles = list(ESTADOS_POR_CANAL.keys())
            can_idx = canales_disponibles.index(cur_canal) if cur_canal in canales_disponibles else 0
            new_canal = st.selectbox("Nuevo Canal de la Notificación:", canales_disponibles,
                                     index=can_idx, key="hist_new_canal")

        with c1:
            estados_disponibles = ESTADOS_POR_CANAL[new_canal]
            # Try to keep the current state if it's valid for the new channel, otherwise select the first one
            est_idx = estados_disponibles.index(cur_estado) if cur_estado in estados_disponibles else 0
            new_estado = st.selectbox("Nuevo Estado de la Notificación:", estados_disponibles,
                                      index=est_idx, key="hist_new_estado")

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
    st.markdown("## 📭 Seguimiento de Notificaciones")

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
            exitosos   = len(df_view[df_view["Estado_Notificacion"].isin(["Correo Enviado", "Agenda Confirmada"])])
            fallidos   = len(df_view[df_view["Estado_Notificacion"].isin(["Correo Rebotado", "Sin Respuesta", "Cliente por Contactar"])])
            canal_fav  = df_view["Canal_Notificacion"].mode()[0] if not df_view["Canal_Notificacion"].empty else "N/A"
            m1.metric("Total Registros",        total)
            m2.metric("✅ Enviados/Confirmados",  exitosos)
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
        
        # Opciones de descarga y conteo
        col_txt, col_csv, col_xlsx = st.columns([6, 2, 2])
        
        with col_txt:
            st.markdown(
                f'<div style="font-size:.76rem;color:#8A95A3;margin-top:10px;">'
                f'Mostrando {len(df_view)} registros</div>', unsafe_allow_html=True)
                
        with col_xlsx:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                # Removemos rowid si por alguna razón se unió al df
                export_df = df_view.drop(columns=["rowid"], errors="ignore")
                export_df.to_excel(writer, index=False, sheet_name="Historial_Notificaciones")
                # Auto-ajuste simple de columnas
                for column in writer.sheets["Historial_Notificaciones"].columns:
                    max_length = 0
                    column = [cell for cell in column]
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = (max_length + 2)
                    writer.sheets["Historial_Notificaciones"].column_dimensions[column[0].column_letter].width = adjusted_width

            st.download_button("📥 Excel", data=buf.getvalue(),
                               file_name=f"historial_notificaciones_{date.today()}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
                               
        with col_csv:
            export_df = df_view.drop(columns=["rowid"], errors="ignore")
            csv_data = export_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV", data=csv_data,
                               file_name=f"historial_notificaciones_{date.today()}.csv",
                               mime="text/csv",
                               use_container_width=True)

        st.dataframe(df_view, use_container_width=True, hide_index=True)

    # ── Editor ────────────────────────────────────────────
    st.markdown("---")
    _notif_editor(df_view)