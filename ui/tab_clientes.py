import streamlit as st
import pandas as pd
import sqlite3
from ui.components import section_card

DB_PATH = 'migraciones.db'

def _get_db_connection():
    return sqlite3.connect(DB_PATH)

def _obtener_nombres_clientes():
    """Trae los nombres únicos de clientes desde la tabla maestra."""
    conn = _get_db_connection()
    try:
        df = pd.read_sql_query('SELECT DISTINCT "CUSTOMER_Name_SCCD-TM" FROM DATABASE ORDER BY 1', conn)
        return df["CUSTOMER_Name_SCCD-TM"].tolist()
    except:
        return []
    finally:
        conn.close()

def _obtener_id_y_datos_existentes(nombre_cliente):
    """
    Busca el ID en DATABASE y verifica si ya hay info en DIRECTORIO_CLIENTE.
    """
    conn = _get_db_connection()
    datos = {
        "id": "No encontrado",
        "asignado": "— Seleccione —",
        "contactos": "",
        "email": "",
        "tel": "",
        "cel": "",
        "tipo": "Sencillo",
        "existe": False
    }
    try:
        # 1. Obtener ID de la tabla maestra (DATABASE)
        query_id = 'SELECT "CUSTOMER_ID_SCCD-TM" FROM DATABASE WHERE "CUSTOMER_Name_SCCD-TM" = ? LIMIT 1'
        res_id = conn.execute(query_id, (nombre_cliente,)).fetchone()
        if res_id:
            datos["id"] = res_id[0]

        # 2. Buscar si ya existe en el directorio para autocompletar
        # Usamos comillas dobles para "Contacto(s)" por los paréntesis en el nombre de la columna
        query_dir = 'SELECT * FROM DIRECTORIO_CLIENTE WHERE "Cliente" = ? LIMIT 1'
        df_existente = pd.read_sql_query(query_dir, conn, params=(nombre_cliente,))
        
        if not df_existente.empty:
            row = df_existente.iloc[0]
            datos["asignado"] = str(row.get("Asignado_a", "— Seleccione —"))
            datos["contactos"] = str(row.get("Contacto(s)", ""))
            datos["email"] = str(row.get("Email", ""))
            datos["tel"] = str(row.get("Telefono", ""))
            datos["cel"] = str(row.get("Celular", ""))
            datos["tipo"] = str(row.get("Tipo_Cliente", "Sencillo"))
            datos["existe"] = True
            
    except Exception as e:
        print(f"Error al recuperar datos: {e}")
    finally:
        conn.close()
    return datos

def _obtener_ingenieros():
    """Trae la lista de ingenieros disponibles."""
    conn = _get_db_connection()
    try:
        df = pd.read_sql_query('SELECT Nombre FROM TEAM_MIGRACION WHERE Estado = "Disponible" ORDER BY Nombre', conn)
        return df["Nombre"].tolist()
    except:
        return []
    finally:
        conn.close()

def render():
    st.markdown("## 👤 Directorio de Clientes e Ingenieros")

    # --- SECCIÓN: AGREGAR INGENIERO ---
    with st.expander("➕ Gestionar Equipo de Migración"):
        with st.form("nuevo_ingeniero"):
            c1, c2 = st.columns(2)
            new_name = c1.text_input("Nombre Completo:")
            new_mail = c2.text_input("Correo:")
            new_rol  = c1.text_input("Rol (Texto libre):")
            new_est  = c2.selectbox("Estado:", ["Disponible", "No disponible"])
            if st.form_submit_button("Guardar Integrante"):
                if new_name:
                    conn = _get_db_connection()
                    try:
                        conn.execute('INSERT INTO TEAM_MIGRACION (Nombre, Correo, Estado, Rol) VALUES (?,?,?,?)', 
                                     (new_name, new_mail, new_est, new_rol))
                        conn.commit()
                        st.success(f"✅ {new_name} agregado al equipo.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")
                    finally:
                        conn.close()

    # --- SECCIÓN: ASIGNACIÓN (CON AUTO-COMPLETADO) ---
    clientes_db = _obtener_nombres_clientes()
    ingenieros_db = _obtener_ingenieros()

    with section_card("🏢 Ficha de Cliente"):
        # Selector de cliente
        cliente_sel = st.selectbox("Seleccione el Cliente para editar/asignar:", ["— Seleccione —"] + clientes_db, key="main_cliente_sel")
        
        if cliente_sel != "— Seleccione —":
            # Traemos los datos para autocompletar automáticamente
            info = _obtener_id_y_datos_existentes(cliente_sel)
            
            # Formulario con valores pre-cargados
            with st.form("form_directorio"):
                st.subheader(f"Editando: {cliente_sel}")
                st.info(f"🆔 **ID Cliente (SCCD):** {info['id']}")
                
                col1, col2 = st.columns(2)
                with col1:
                    # Buscamos el índice del ingeniero si ya existe en la lista de disponibles
                    idx_ing = 0
                    if info['asignado'] in ingenieros_db:
                        idx_ing = ingenieros_db.index(info['asignado']) + 1
                    
                    ing_asignado = st.selectbox("Ingeniero Responsable:", ["— Seleccione —"] + ingenieros_db, index=idx_ing)
                    tipo_c = st.radio("Tipo de Cliente:", ["Sencillo", "Complejo"], 
                                      index=0 if info['tipo'] == "Sencillo" else 1, horizontal=True)
                
                with col2:
                    # Campo de contactos (Nombre exacto de columna: Contacto(s))
                    cont_val = st.text_area("Contacto(s) en el Cliente:", value=info['contactos'])
                
                c3, c4, c5 = st.columns(3)
                mail_val = c3.text_input("Email:", value=info['email'])
                tel_val = c4.text_input("Teléfono:", value=info['tel'])
                cel_val = c5.text_input("Celular:", value=info['cel'])
                
                btn_label = "Actualizar Datos" if info['existe'] else "Guardar Nueva Asignación"
                if st.form_submit_button(f"💾 {btn_label}"):
                    if ing_asignado != "— Seleccione —":
                        conn = _get_db_connection()
                        try:
                            # Importante usar comillas dobles para la columna "Contacto(s)" por los paréntesis
                            conn.execute(f"""
                                INSERT OR REPLACE INTO DIRECTORIO_CLIENTE 
                                (Cliente, ID_Cliente, Asignado_a, "Contacto(s)", Email, Telefono, Celular, Tipo_Cliente)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (cliente_sel, info['id'], ing_asignado, cont_val, mail_val, tel_val, cel_val, tipo_c))
                            conn.commit()
                            st.success("✅ Datos actualizados correctamente.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error en base de datos: {e}")
                        finally:
                            conn.close()
                    else:
                        st.warning("Debe seleccionar un Ingeniero Responsable.")

    # --- VISTA GENERAL ---
    st.markdown("---")
    st.markdown("### 📋 Listado Maestro de Clientes")
    conn = _get_db_connection()
    try:
        df_final = pd.read_sql_query("SELECT * FROM DIRECTORIO_CLIENTE", conn)
        if not df_final.empty:
            # Buscador rápido
            busqueda = st.text_input("🔍 Buscar en el directorio:", key="search_dir")
            if busqueda:
                mask = df_final.astype(str).apply(lambda x: x.str.contains(busqueda, case=False, na=False)).any(axis=1)
                df_final = df_final[mask]
            st.dataframe(df_final, use_container_width=True, hide_index=True)
        else:
            st.info("No hay asignaciones registradas.")
    except Exception as e:
        st.error("No se pudo cargar la tabla. Asegúrate de que la tabla DIRECTORIO_CLIENTE exista.")
    finally:
        conn.close()