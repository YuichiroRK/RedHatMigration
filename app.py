"""
app.py
Orquestador principal — Liberty Networks Migration Tool.
"""
import streamlit as st

from ui import tab_calendario, tab_agendamiento, tab_agendados
from ui.styles import inject

# Optional tabs — safe import so missing files don't crash the app
try:
    from ui import tab_logs
    _has_logs = True
except ImportError:
    _has_logs = False

try:
    from ui import tab_notificaciones
    _has_notif = True
except ImportError:
    _has_notif = False

try:
    from ui import tab_historial_notificaciones
    _has_hist = True
except ImportError:
    _has_hist = False

try:
    from ui import tab_clientes
    _has_clientes = True
except ImportError:
    _has_clientes = False

st.set_page_config(page_title="Gestión Migraciones LN", layout="wide", page_icon="🏢")
inject()

# ── Redirect hook (must run before sidebar) ───────────────
if "redirect_to" in st.session_state:
    st.session_state["menu_principal"] = st.session_state.pop("redirect_to")

# ── Sidebar ───────────────────────────────────────────────
with st.sidebar:
    st.image(
        "https://mms.businesswire.com/media/20240312814173/es/2063244/5/LN_LOGO.jpg",
        use_container_width=True,
    )
    st.markdown("---")

    NAV_OPTIONS = [
        "📢 Notificaciones Clientes",
        "📅 Ver Calendario",
        "⏰ Ver Ventanas",
    ]
    if _has_logs:     NAV_OPTIONS.append("📝 Logs y Seguimiento")
    if _has_hist:     NAV_OPTIONS.append("📭 Ver Notificaciones")
    if _has_clientes: NAV_OPTIONS.append("👤 Clientes")

    opcion = st.radio(
        "Navegación Principal",
        NAV_OPTIONS,
        key="menu_principal",
    )

    st.markdown("---")
    st.caption("Liberty Networks - Migration Tool v2.0")

# ── Routing ───────────────────────────────────────────────
if opcion == "📅 Ver Calendario":
    tab_calendario.render()


elif opcion == "⏰ Ver Ventanas":
    tab_agendados.render()

elif opcion == "📢 Notificaciones Clientes":
    if _has_notif:
        tab_notificaciones.render()
    else:
        st.warning("Módulo de notificaciones no disponible.")

elif opcion == "📝 Logs y Seguimiento" and _has_logs:
    tab_logs.render()

elif opcion == "📭 Ver Notificaciones" and _has_hist:
    tab_historial_notificaciones.render()

elif opcion == "👤 Clientes" and _has_clientes:
    tab_clientes.render()