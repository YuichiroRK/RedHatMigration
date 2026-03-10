"""
app.py
Orquestador principal de la aplicación Liberty Networks.
"""
import streamlit as st

# Importamos todas las pestañas de la carpeta UI
from ui import (
    tab_calendario, 
    tab_logs, 
    tab_notificaciones, 
    tab_agendamiento, 
    tab_agendados, 
    tab_historial_notificaciones,
    tab_clientes
)

st.set_page_config(page_title="Gestión Migraciones LN", layout="wide", page_icon="🏢")

# --- MAGIA DE REDIRECCIÓN ---
# Si un formulario pidió cambiar de menú, lo actualizamos ANTES de dibujar el sidebar
if "redirect_to" in st.session_state:
    st.session_state["menu_principal"] = st.session_state["redirect_to"]
    del st.session_state["redirect_to"] # Borramos la nota para no quedarnos en un bucle

# --- MENÚ LATERAL (SIDEBAR) ---
with st.sidebar:
    # Logo actualizado de Liberty Networks
    st.image("https://mms.businesswire.com/media/20240312814173/es/2063244/5/LN_LOGO.jpg", use_container_width=True)
    st.markdown("---")
    
    opcion = st.radio(
        "Navegación Principal",
        [
            "📅 Ver Calendario",
            "➕ Agendar Ventana",
            "⏰ Ver Ventanas",
            "📝 Logs y Seguimiento",
            "📢 Notificaciones Clientes",
            "📭 Ver Notificaciones",
            "👤 Clientes"
        ],
        key="menu_principal"
    )
    
    st.markdown("---")
    st.caption("Liberty Networks - Migration Tool v2.0")

# --- ENRUTAMIENTO ---
if opcion == "📅 Ver Calendario":
    tab_calendario.render()

elif opcion == "➕ Agendar Ventana":
    tab_agendamiento.render()

elif opcion == "⏰ Ver Ventanas":
    tab_agendados.render()

elif opcion == "📝 Logs y Seguimiento":
    tab_logs.render()

elif opcion == "📢 Notificaciones Clientes":
    tab_notificaciones.render()

elif opcion == "📭 Ver Notificaciones":
    tab_historial_notificaciones.render()

elif opcion == "👤 Clientes":
    tab_clientes.render()