"""
ui/tab_notificaciones.py
Pestaña para registrar notificaciones masivas enviadas a los clientes.
"""
import streamlit as st
import pandas as pd
import sqlite3
from logic.crud_operaciones import guardar_notificaciones_masivas

def render():
    st.markdown("## 📢 Registro de Notificaciones a Clientes")
    
    conn = sqlite3.connect('migraciones.db')
    try:
        # Traemos clientes del directorio
        clientes_lista = pd.read_sql_query('SELECT DISTINCT "Cliente" FROM DIRECTORIO_CLIENTE ORDER BY "Cliente"', conn)['Cliente'].tolist()
    except Exception:
        clientes_lista = []
    finally:
        conn.close()

    col_form, col_info = st.columns([1.5, 1])

    with col_form:
        with st.form("form_notificaciones", clear_on_submit=True):
            st.markdown("### ✉️ Detalles del Envío")
            
            # Selector múltiple para inyección masiva
            clientes_sel = st.multiselect("Clientes notificados (Selecciona uno o varios):", clientes_lista)
            
            c1, c2 = st.columns(2)
            with c1:
                creado_por = st.text_input("Ingeniero / Registrado por:")
                canal = st.selectbox("Canal de Notificación:", ["Email", "Teléfono", "Reunión Teams", "WhatsApp", "Otro"])
            with c2:
                estado = st.selectbox("Estado:", ["Enviado", "Recibido", "Sin Respuesta", "Rebotado"])
                cantidad = st.number_input("Cantidad de intentos/mensajes:", min_value=1, value=1)
                
            notas = st.text_area("Notas / Asunto / Observaciones:")
            
            submit = st.form_submit_button("🚀 Registrar Notificaciones")
            
            if submit:
                if not clientes_sel:
                    st.error("Debes seleccionar al menos un cliente.")
                elif not creado_por.strip():
                    st.error("Debes indicar quién creó la notificación.")
                else:
                    # cantidad se pasa como string porque tu columna es TEXT
                    if guardar_notificaciones_masivas(clientes_sel, creado_por.strip(), estado, canal, str(cantidad), notas.strip()):
                        st.success(f"¡Éxito! Notificación registrada en la base de datos para {len(clientes_sel)} cliente(s).")
                        st.balloons()

    with col_info:
        st.info(
            "**💡 Tip de uso masivo:**\n\n"
            "Usa esta herramienta cuando envíes un correo general o invites a múltiples clientes a una reunión de mantenimiento. "
            "El sistema creará una fila individual para cada cliente seleccionado de forma automática en la tabla `NOTIFICACIONES_CLIENTES`."
        )