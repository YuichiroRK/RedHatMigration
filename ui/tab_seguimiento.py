"""
ui/tab_seguimiento.py
Tab: Ver Máquinas En Seguimiento
Shows VMs currently in "En Seguimiento" state.
- Auto-promotes to "Migrada OK" after 10 days (with confirmation button)
- Allows manual "Rollback Tras Seguimiento" with mandatory reason
"""

from datetime import date, timedelta
import sqlite3

import pandas as pd
import streamlit as st

from ui.db_utils import DB_PATH

from ui.status_widget import render_status_editor

# ──────────────────────────────────────────────────────────────
# DATA
# ──────────────────────────────────────────────────────────────

def _load_en_seguimiento() -> pd.DataFrame:
    """Returns VMs with Estado_Migracion = 'En Seguimiento'."""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("""
            SELECT
                e.VM_ID_TM,
                e.Cliente,
                e.Estado_Migracion   AS Estado,
                e.Fecha_Ejecucion,
                e.Fecha_Finalizacion,
                e.Observaciones_Fallo,
                v."Ambiente",
                v."Apps y Servicios"
            FROM ESTADO_VMS e
            LEFT JOIN VMs v ON e.VM_ID_TM = v.VM_ID_TM
            WHERE e.Estado_Migracion = 'En Seguimiento'
            ORDER BY e.Fecha_Ejecucion ASC
        """, conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df


def _auto_promote(vm_id: str, cliente: str, fecha_ej_str: str) -> bool:
    """Promote VM to Migrada OK — called when 10-day period has elapsed."""
    from logic.update_status import upsert_vm_status
    today_str = date.today().strftime("%Y-%m-%d %H:%M:%S")
    ok, _ = upsert_vm_status(
        vm_id, cliente, "Migrada OK",
        fecha_ejecucion=fecha_ej_str,
        fecha_finalizacion=today_str,
        observaciones="Promovida automáticamente tras período de seguimiento de 10 días.",
    )
    return ok


def _days_since(fecha_str) -> int | None:
    try:
        d = pd.to_datetime(str(fecha_str)[:10]).date()
        return (date.today() - d).days
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
# VM CARD
# ──────────────────────────────────────────────────────────────

def _seguimiento_card(row: pd.Series, idx: int):
    vm_id    = str(row.get("VM_ID_TM", "—"))
    cliente  = str(row.get("Cliente",  "—"))
    fej      = row.get("Fecha_Ejecucion", "")
    obs      = str(row.get("Observaciones_Fallo", "") or "")
    ambiente = str(row.get("Ambiente", "") or "")
    apps     = str(row.get("Apps y Servicios", "") or "")

    days     = _days_since(fej)
    ready    = days is not None and days >= 10

    # ── Banner ────────────────────────────────────────────
    if ready:
        banner_bg   = "#F0FFF4"
        banner_bdr  = "#68D391"
        banner_txt  = "#276749"
        badge_html  = (
            f'<span style="background:#38A169;color:#fff;padding:2px 10px;'
            f'border-radius:20px;font-size:.68rem;font-weight:700;">✅ Lista para Migrada OK</span>'
        )
    else:
        remaining   = (10 - days) if days is not None else "?"
        banner_bg   = "#FAF5FF"
        banner_bdr  = "#B794F4"
        banner_txt  = "#44337A"
        badge_html  = (
            f'<span style="background:#805AD5;color:#fff;padding:2px 10px;'
            f'border-radius:20px;font-size:.68rem;font-weight:700;">'
            f'🔍 En Seguimiento — {remaining} día(s) restantes</span>'
        )

    st.markdown(
        f'<div style="background:{banner_bg};border:1.5px solid {banner_bdr};'
        f'border-radius:12px;padding:12px 18px;margin-bottom:6px;">'
        f'<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">'
        f'<div>'
        f'  <div style="font-size:.88rem;font-weight:800;color:#1E2330;">{vm_id}</div>'
        f'  <div style="font-size:.73rem;color:#718096;margin-top:2px;">'
        f'    Cliente: <b>{cliente}</b>'
        + (f' · Ambiente: <b>{ambiente}</b>' if ambiente and ambiente != "nan" else "") +
        f'  </div>'
        + (f'<div style="font-size:.7rem;color:#718096;margin-top:2px;">Apps: {apps}</div>'
           if apps and apps not in ("nan","—","") else "") +
        f'  <div style="font-size:.7rem;color:#A0AEC0;margin-top:4px;">'
        f'    Ejecución: {str(fej)[:16] if fej else "Sin fecha"}'
        + (f' · <b>{days} días</b> en seguimiento' if days is not None else "") +
        f'  </div>'
        + (f'<div style="font-size:.7rem;color:#718096;margin-top:3px;">📝 {obs}</div>'
           if obs and obs != "nan" else "") +
        f'</div>'
        f'<div>{badge_html}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ── Action section ────────────────────────────────────
    with st.expander(f"✏️ Modificar estado — {vm_id}", expanded=False):
        if ready:
            st.success(
                f"✅ Han pasado **{days} días** desde la ejecución. "
                f"Esta VM está lista para ser marcada como **Migrada OK**."
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Confirmar Migrada OK", key=f"auto_ok_{vm_id}_{idx}",
                             type="primary", use_container_width=True):
                    if _auto_promote(vm_id, cliente, str(fej)):
                        st.success(f"🎉 VM **{vm_id}** marcada como Migrada OK.")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error("Error al actualizar. Intenta de nuevo.")
            with c2:
                st.markdown("")  # spacer

        st.markdown("---")
        st.caption("Para marcar como **Rollback Tras Seguimiento**, el motivo es **obligatorio**.")
        render_status_editor(
            vm_id, cliente, "En Seguimiento",
            key_suffix=f"seg_{idx}",
            allowed_states=["Migrada OK", "Rollback Tras Seguimiento"],
        )


# ──────────────────────────────────────────────────────────────
# RENDER
# ──────────────────────────────────────────────────────────────

def render():
    st.markdown("## 🔍 Máquinas En Seguimiento")
    st.caption("VMs en período de estabilización post-migración (10 días)")

    df = _load_en_seguimiento()

    if df.empty:
        st.info("✅ No hay VMs en período de seguimiento actualmente.")
        return

    total     = len(df)
    listas    = sum(1 for _, r in df.iterrows()
                   if (_days_since(r.get("Fecha_Ejecucion")) or 0) >= 10)
    en_curso  = total - listas

    # ── Summary cards ─────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    c1.metric("🔍 En Seguimiento", total)
    c2.metric("✅ Listas (≥10 días)", listas)
    c3.metric("⏳ En curso (<10 días)", en_curso)

    st.markdown("---")

    # ── Filters ───────────────────────────────────────────
    fa, fb, _ = st.columns([1.5, 1.5, 3])
    with fa:
        cli_opts = ["— Todos —"] + sorted(df["Cliente"].dropna().unique().tolist())
        cli_f = st.selectbox("Cliente:", cli_opts, key="seg_cli_filter")
    with fb:
        estado_f = st.radio("Mostrar:", ["Todas", "Listas primero", "Solo listas"],
                            horizontal=True, key="seg_estado_filter")

    df_show = df.copy()
    if cli_f != "— Todos —":
        df_show = df_show[df_show["Cliente"] == cli_f]

    # Compute days for sort/filter
    df_show["_days"] = df_show["Fecha_Ejecucion"].apply(_days_since)
    df_show["_ready"] = df_show["_days"].apply(lambda d: (d or 0) >= 10)

    if estado_f == "Solo listas":
        df_show = df_show[df_show["_ready"]]
    elif estado_f == "Listas primero":
        df_show = df_show.sort_values("_ready", ascending=False)

    if df_show.empty:
        st.info("Sin VMs con los filtros seleccionados.")
        return

    st.caption(f"Mostrando **{len(df_show)}** VM(s)")

    for idx, (_, row) in enumerate(df_show.iterrows()):
        _seguimiento_card(row, idx)