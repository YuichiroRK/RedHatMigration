"""
ui/tab_clientes.py
Admin panel: manage DIRECTORIO_CLIENTE + TEAM_MIGRACION (password-protected via app.py).
"""
import sqlite3
import pandas as pd
import streamlit as st
from ui.components import section_card

DB_PATH = "migraciones.db"

TIPO_CLIENTE_OPTS = ["Estándar", "Prioritario", "Gobierno", "Corporativo", "PYME", "Otro"]


def _conn():
    return sqlite3.connect(DB_PATH)


def _ensure_schema():
    conn = _conn()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS DIRECTORIO_CLIENTE (
            "Cliente"      TEXT PRIMARY KEY,
            "ID_Cliente"   TEXT,
            "Asignado_a"   TEXT,
            "Contacto(s)"  TEXT,
            "Email"        TEXT,
            "Telefono"     TEXT,
            "Celular"      TEXT,
            "Tipo_Cliente" TEXT DEFAULT "Estándar"
        )
    ''')
    cols = [r[1] for r in conn.execute("PRAGMA table_info(DIRECTORIO_CLIENTE)").fetchall()]
    migrations = [
        ("Tipo_Cliente",  '"Estándar"'),
        ("ID_Cliente",    "NULL"),
        ("Asignado_a",    "NULL"),
        ("Email",         "NULL"),
        ("Telefono",      "NULL"),
        ("Celular",       "NULL"),
    ]
    for col, default in migrations:
        if col not in cols:
            try:
                conn.execute(f'ALTER TABLE DIRECTORIO_CLIENTE ADD COLUMN "{col}" TEXT DEFAULT {default}')
            except Exception:
                pass
    # Contacto(s) special case
    if "Contacto(s)" not in cols:
        try:
            conn.execute('ALTER TABLE DIRECTORIO_CLIENTE ADD COLUMN "Contacto(s)" TEXT DEFAULT NULL')
        except Exception:
            pass
    conn.commit()
    conn.close()


def _load_clientes() -> pd.DataFrame:
    conn = _conn()
    try:
        return pd.read_sql_query('SELECT * FROM DIRECTORIO_CLIENTE ORDER BY "Cliente"', conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


def _load_clientes_db() -> list:
    conn = _conn()
    try:
        df = pd.read_sql_query('SELECT DISTINCT "CUSTOMER_Name_SCCD-TM" FROM DATABASE ORDER BY 1', conn)
        return df["CUSTOMER_Name_SCCD-TM"].dropna().tolist()
    except Exception:
        return []
    finally:
        conn.close()


def _get_cliente_data(nombre: str) -> dict:
    conn = _conn()
    datos = {"id": "", "asignado": "", "contactos": "", "email": "",
             "tel": "", "cel": "", "tipo": "Estándar", "existe": False}
    try:
        r = conn.execute(
            'SELECT "CUSTOMER_ID_SCCD-TM" FROM DATABASE WHERE "CUSTOMER_Name_SCCD-TM"=? LIMIT 1',
            (nombre,)).fetchone()
        if r:
            datos["id"] = str(r[0] or "")
        df = pd.read_sql_query(
            'SELECT * FROM DIRECTORIO_CLIENTE WHERE "Cliente"=? LIMIT 1', conn, params=(nombre,))
        if not df.empty:
            row = df.iloc[0]
            datos["asignado"]  = str(row.get("Asignado_a", "") or "")
            datos["contactos"] = str(row.get("Contacto(s)", "") or "")
            datos["email"]     = str(row.get("Email", "") or "")
            datos["tel"]       = str(row.get("Telefono", "") or "")
            datos["cel"]       = str(row.get("Celular", "") or "")
            datos["tipo"]      = str(row.get("Tipo_Cliente", "Estándar") or "Estándar")
            datos["existe"]    = True
    except Exception as e:
        st.error(f"Error: {e}")
    finally:
        conn.close()
    return datos


def _upsert_cliente(nombre, id_cli, asignado, contactos, email, tel, cel, tipo) -> bool:
    conn = _conn()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO DIRECTORIO_CLIENTE
            (Cliente, ID_Cliente, Asignado_a, "Contacto(s)", Email, Telefono, Celular, Tipo_Cliente)
            VALUES (?,?,?,?,?,?,?,?)
        ''', (nombre, id_cli, asignado, contactos, email, tel, cel, tipo))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False
    finally:
        conn.close()


def _delete_cliente(nombre: str) -> bool:
    conn = _conn()
    try:
        conn.execute('DELETE FROM DIRECTORIO_CLIENTE WHERE "Cliente"=?', (nombre,))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False
    finally:
        conn.close()


def _load_ingenieros() -> list:
    conn = _conn()
    try:
        df = pd.read_sql_query('SELECT Nombre FROM TEAM_MIGRACION WHERE Nombre IS NOT NULL ORDER BY Nombre', conn)
        return df["Nombre"].tolist()
    except Exception:
        return []
    finally:
        conn.close()


def _import_from_database() -> int:
    conn = _conn()
    try:
        df = pd.read_sql_query(
            'SELECT DISTINCT "CUSTOMER_Name_SCCD-TM" AS cli FROM DATABASE WHERE "CUSTOMER_Name_SCCD-TM" IS NOT NULL',
            conn)
        ok = 0
        for cli in df["cli"].dropna():
            try:
                conn.execute(
                    'INSERT OR IGNORE INTO DIRECTORIO_CLIENTE (Cliente, Tipo_Cliente) VALUES (?,?)',
                    (str(cli).strip(), "Estándar"))
                ok += 1
            except Exception:
                pass
        conn.commit()
        return ok
    except Exception as e:
        st.error(f"Error: {e}")
        return 0
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────
# Render
# ──────────────────────────────────────────────────────────
def render():
    st.markdown("## 👤 Directorio de Clientes e Ingenieros")
    _ensure_schema()

    df_all   = _load_clientes()
    total    = len(df_all)
    ing_list = _load_ingenieros()

    # Summary bar
    tipo_counts = df_all["Tipo_Cliente"].value_counts().to_dict() if not df_all.empty and "Tipo_Cliente" in df_all.columns else {}
    badges = "".join(
        f'<span style="background:#EBF8FF;color:#2B6CB0;padding:3px 12px;'
        f'border-radius:20px;font-size:.74rem;font-weight:700;margin-right:4px;">{t}: {c}</span>'
        for t, c in tipo_counts.items()
    )
    st.markdown(
        f'<div style="background:#fff;border:1px solid #E2E6ED;border-radius:10px;'
        f'padding:12px 18px;margin-bottom:16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;">'
        f'<div><span style="font-size:1.6rem;font-weight:800;color:#FF7800;">{total}</span>'
        f'<span style="font-size:.78rem;color:#8A95A3;margin-left:6px;">clientes registrados</span></div>'
        f'{badges}</div>',
        unsafe_allow_html=True)

    tab_ficha, tab_lista, tab_team, tab_import = st.tabs([
        "🏢 Ficha de Cliente", "📋 Listado", "👷 Equipo de Migración", "📥 Importar"
    ])

    # ── TAB 1: Ficha ─────────────────────────────────────
    with tab_ficha:
        clientes_db = _load_clientes_db()
        cli_dir = df_all["Cliente"].dropna().tolist() if not df_all.empty else []
        all_opts = sorted(set(clientes_db + cli_dir))

        cliente_sel = st.selectbox(
            "Seleccionar cliente:", ["— Seleccione —"] + all_opts, key="cli_ficha_sel")

        if cliente_sel and cliente_sel != "— Seleccione —":
            info = _get_cliente_data(cliente_sel)

            with section_card(f"🏢 {cliente_sel}"):
                if info["id"]:
                    st.info(f"🆔 **ID SCCD:** {info['id']}")

                col1, col2 = st.columns(2)
                with col1:
                    tipo_idx = TIPO_CLIENTE_OPTS.index(info["tipo"]) if info["tipo"] in TIPO_CLIENTE_OPTS else 0
                    nuevo_tipo = st.selectbox("Tipo de cliente:", TIPO_CLIENTE_OPTS,
                                              index=tipo_idx, key="cli_tipo_ed")

                    ing_opts = ["— Sin asignar —"] + ing_list
                    ing_idx  = ing_opts.index(info["asignado"]) if info["asignado"] in ing_opts else 0
                    nuevo_ing = st.selectbox("Ingeniero responsable:", ing_opts,
                                             index=ing_idx, key="cli_ing_ed")

                with col2:
                    nuevo_cont = st.text_area("Contacto(s) en el cliente:",
                                              value=info["contactos"], height=100, key="cli_cont_ed")

                c3, c4, c5 = st.columns(3)
                nuevo_email = c3.text_input("Email:", value=info["email"], key="cli_email_ed")
                nuevo_tel   = c4.text_input("Teléfono:", value=info["tel"], key="cli_tel_ed")
                nuevo_cel   = c5.text_input("Celular:", value=info["cel"], key="cli_cel_ed")

                st.markdown("<br>", unsafe_allow_html=True)
                btn_lbl = "💾 Actualizar" if info["existe"] else "💾 Guardar nuevo"
                if st.button(btn_lbl, key="cli_save_ficha", type="primary", use_container_width=True):
                    ing_val = "" if nuevo_ing == "— Sin asignar —" else nuevo_ing
                    if _upsert_cliente(cliente_sel, info["id"], ing_val, nuevo_cont,
                                       nuevo_email, nuevo_tel, nuevo_cel, nuevo_tipo):
                        st.success("✅ Datos guardados correctamente.")
                        st.rerun()

    # ── TAB 2: Listado ────────────────────────────────────
    with tab_lista:
        if df_all.empty:
            st.info("No hay clientes registrados aún.")
        else:
            c_search, c_fil = st.columns([2, 1])
            busq     = c_search.text_input("🔍 Buscar:", key="cli_busq")
            tipo_fil = c_fil.multiselect("Filtrar tipo:", TIPO_CLIENTE_OPTS, key="cli_tipo_fil")

            df_show = df_all[df_all["Cliente"].notna() & (df_all["Cliente"].str.strip() != "")].copy()
            if busq:
                df_show = df_show[df_show.astype(str).apply(
                    lambda x: x.str.contains(busq, case=False, na=False)).any(axis=1)]
            if tipo_fil:
                df_show = df_show[df_show["Tipo_Cliente"].isin(tipo_fil)]

            st.caption(f"{len(df_show)} cliente(s)")

            for idx, (_, row) in enumerate(df_show.iterrows()):
                cli_name = str(row["Cliente"]).strip()
                c1, c2, c3, c4, c5 = st.columns([2.5, 1.2, 1.5, 1.8, 0.5])
                with c1:
                    st.markdown(
                        f'<div style="padding:5px 0;font-size:.83rem;font-weight:600;">{cli_name}</div>',
                        unsafe_allow_html=True)
                with c2:
                    tipo = str(row.get("Tipo_Cliente", "") or "")
                    st.markdown(
                        f'<div style="padding:5px 0;">'
                        f'<span style="background:#EBF8FF;color:#2B6CB0;padding:2px 9px;'
                        f'border-radius:20px;font-size:.7rem;font-weight:700;">{tipo}</span></div>',
                        unsafe_allow_html=True)
                with c3:
                    st.markdown(
                        f'<div style="padding:5px 0;font-size:.78rem;color:#4A5568;">'
                        f'{row.get("Asignado_a","") or ""}</div>', unsafe_allow_html=True)
                with c4:
                    st.markdown(
                        f'<div style="padding:5px 0;font-size:.75rem;color:#718096;">'
                        f'{row.get("Email","") or ""}</div>', unsafe_allow_html=True)
                with c5:
                    if st.button("🗑", key=f"cli_del_{idx}", help=f"Eliminar {cli_name}"):
                        if _delete_cliente(cli_name):
                            st.success(f"'{cli_name}' eliminado.")
                            st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)
            buf = df_show.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 Exportar CSV", data=buf,
                               file_name="directorio_clientes.csv", mime="text/csv")

    # ── TAB 3: Equipo ─────────────────────────────────────
    with tab_team:
        with section_card("➕ Agregar integrante"):
            with st.form("form_nuevo_ing"):
                c1, c2 = st.columns(2)
                new_name = c1.text_input("Nombre completo:")
                new_mail = c2.text_input("Correo:")
                new_rol  = c1.text_input("Rol:")
                new_est  = c2.selectbox("Estado:", ["Disponible", "No disponible"])
                if st.form_submit_button("💾 Guardar integrante"):
                    if new_name.strip():
                        conn = _conn()
                        try:
                            conn.execute(
                                'INSERT INTO TEAM_MIGRACION (Nombre, Correo, Estado, Rol) VALUES (?,?,?,?)',
                                (new_name.strip(), new_mail.strip(), new_est, new_rol.strip()))
                            conn.commit()
                            st.success(f"✅ {new_name} agregado.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                        finally:
                            conn.close()
                    else:
                        st.error("El nombre no puede estar vacío.")

        st.markdown("#### 👷 Equipo actual")
        conn = _conn()
        try:
            df_team = pd.read_sql_query("SELECT * FROM TEAM_MIGRACION ORDER BY Nombre", conn)
            if df_team.empty:
                st.info("No hay integrantes registrados.")
            else:
                for idx, (_, row) in enumerate(df_team.iterrows()):
                    nombre = str(row.get("Nombre", "") or "")
                    estado = str(row.get("Estado", "") or "")
                    color  = "#38A169" if estado == "Disponible" else "#C53030"
                    t1, t2, t3, t4, t5 = st.columns([2, 2, 1.2, 1.5, 0.5])
                    t1.markdown(f'<div style="padding:4px 0;font-size:.83rem;font-weight:600;">{nombre}</div>',
                                unsafe_allow_html=True)
                    t2.markdown(f'<div style="padding:4px 0;font-size:.76rem;color:#4A5568;">{row.get("Correo","") or ""}</div>',
                                unsafe_allow_html=True)
                    t3.markdown(f'<div style="padding:4px 0;font-size:.74rem;color:#718096;">{row.get("Rol","") or ""}</div>',
                                unsafe_allow_html=True)
                    t4.markdown(
                        f'<div style="padding:4px 0;">'
                        f'<span style="background:{color}22;color:{color};padding:2px 9px;'
                        f'border-radius:20px;font-size:.7rem;font-weight:700;">{estado}</span></div>',
                        unsafe_allow_html=True)
                    with t5:
                        if st.button("🗑", key=f"team_del_{idx}", help=f"Eliminar {nombre}"):
                            c2 = _conn()
                            c2.execute("DELETE FROM TEAM_MIGRACION WHERE Nombre=?", (nombre,))
                            c2.commit(); c2.close()
                            st.success(f"'{nombre}' eliminado.")
                            st.rerun()
        except Exception:
            st.info("La tabla TEAM_MIGRACION no existe aún.")
        finally:
            conn.close()

    # ── TAB 4: Import ─────────────────────────────────────
    with tab_import:
        st.info("Importa clientes únicos de la tabla **DATABASE**. Los ya existentes no serán sobreescritos.")
        if st.button("🔄 Importar desde DATABASE", key="cli_import", type="primary"):
            n = _import_from_database()
            st.success(f"✅ {n} cliente(s) procesados.")
            st.rerun()