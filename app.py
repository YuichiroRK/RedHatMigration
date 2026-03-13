"""
app.py
Orquestador principal — Liberty Networks Migration Tool.
"""
import streamlit as st

from ui import tab_calendario, tab_agendamiento, tab_agendados
from ui.styles import inject

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

try:
    from ui import tab_stats
    _has_stats = True
except ImportError:
    _has_stats = False

_ADMIN_PASSWORD = "liberty2025"


def _check_password(gate_key: str) -> bool:
    auth_key = f"_auth_{gate_key}"
    if st.session_state.get(auth_key):
        return True
    st.markdown("### 🔒 Acceso restringido")
    pwd = st.text_input("Contraseña:", type="password", key=f"_pwd_{gate_key}")
    if st.button("Entrar", key=f"_btn_{gate_key}"):
        if pwd == _ADMIN_PASSWORD:
            st.session_state[auth_key] = True
            st.rerun()
        else:
            st.error("❌ Contraseña incorrecta.")
    return False


st.set_page_config(page_title="Gestión Migraciones LN", layout="wide", page_icon="🏢")
inject()

if "redirect_to" in st.session_state:
    st.session_state["menu_principal"] = st.session_state.pop("redirect_to")

with st.sidebar:
    st.image(
        "https://mms.businesswire.com/media/20240312814173/es/2063244/5/LN_LOGO.jpg",
        use_container_width=True,
    )
    st.markdown("---")

    NAV_OPTIONS = [
        "📢 Notificaciones Clientes",
        "📭 Seguimiento de Notificaciones",
        "📊 Informes",
        "📅 Ver Calendario"
       # "📊 Estadística de Ventanas",
    ]
   # if _has_logs:     NAV_OPTIONS.append("📝 Logs y Seguimiento")
    if _has_clientes: NAV_OPTIONS.append("👤 Clientes")

    opcion = st.radio(
        "Navegación Principal",
        NAV_OPTIONS,
        key="menu_principal",
    )

    st.markdown("---")
    st.caption("Liberty Networks - Migration Tool v2.0")

if opcion == "📅 Ver Calendario":
    tab_calendario.render()

elif opcion == "📊 Estadística de Ventanas":
    tab_agendados.render()

elif opcion == "📢 Notificaciones Clientes":
    if _has_notif:
        tab_notificaciones.render()
    else:
        st.warning("Módulo de notificaciones no disponible.")

elif opcion == "📊 Informes" and _has_stats:
    tab_stats.render()

elif opcion == "📝 Logs y Seguimiento" and _has_logs:
    tab_logs.render()

elif opcion == "📭 Seguimiento de Notificaciones" and _has_hist:
    tab_historial_notificaciones.render()

elif opcion == "👤 Clientes" and _has_clientes:
    if _check_password("clientes"):
        tab_clientes.render()