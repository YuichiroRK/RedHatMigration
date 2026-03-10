"""
ui/tab_logs.py
Pestaña para agregar y consultar bitácoras (Logs) de las máquinas virtuales.
"""
import streamlit as st
import pandas as pd
import sqlite3
from logic.crud_operaciones import guardar_log_vm, obtener_historial_logs

def render():
    st.markdown("## 📝 Bitácora de Máquinas Virtuales (Logs)")
    
    # Obtener lista de clientes desde DATABASE
    conn = sqlite3.connect('migraciones.db')
    try:
        clientes = pd.read_sql_query('SELECT DISTINCT "CUSTOMER_Name_SCCD-TM" FROM DATABASE ORDER BY "CUSTOMER_Name_SCCD-TM"', conn)['CUSTOMER_Name_SCCD-TM'].tolist()
    except Exception:
        clientes = []
    
    cliente_sel = st.selectbox("1. Seleccione el Cliente:", [""] + clientes, key="log_cliente")
    
    if cliente_sel:
        # Traer VMs de ese cliente
        vms_df = pd.read_sql_query('SELECT "VM_ID_TM", "VM" FROM DATABASE WHERE "CUSTOMER_Name_SCCD-TM" = ?', conn, params=(cliente_sel,))
        vms_dict = dict(zip(vms_df["VM_ID_TM"], vms_df["VM"])) # Diccionario ID -> Nombre
        
        vm_sel = st.selectbox("2. Seleccione la Máquina Virtual:", [""] + list(vms_dict.keys()), 
                              format_func=lambda x: f"{x} - {vms_dict[x]}" if x else "", key="log_vm")
        
        if vm_sel:
            col1, col2 = st.columns([1, 1.2])
            
            with col1:
                st.markdown("### ✍️ Nuevo Log")
                with st.form("form_logs", clear_on_submit=True):
                    descripcion = st.text_area("Descripción de la novedad, fallo o seguimiento:")
                    submit = st.form_submit_button("💾 Guardar Log")
                    
                    if submit:
                        if descripcion.strip():
                            if guardar_log_vm(vm_sel, cliente_sel, descripcion.strip()):
                                st.success("Log guardado exitosamente.")
                                st.rerun()
                        else:
                            st.error("La descripción no puede estar vacía.")
            
            with col2:
                st.markdown("### 🗂️ Historial de Novedades")
                df_historial = obtener_historial_logs(vm_sel)
                if df_historial.empty:
                    st.info("No hay registros previos para esta máquina.")
                else:
                    st.dataframe(df_historial, use_container_width=True, hide_index=True)
    
    conn.close()