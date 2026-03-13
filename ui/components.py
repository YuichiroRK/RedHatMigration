"""
ui/components.py
Componentes reutilizables: sección-card, chips, descripción de ambiente,
dashboard de agendados.

FIX CRÍTICO: Todo el dashboard se emite en UN SOLO st.markdown() para
evitar que Streamlit escape los divs anidados en llamadas separadas.
"""

import sqlite3
import streamlit as st
import pandas as pd

# ─────────────────────────────────────────────────────────────
# Descripciones de ambiente
# ─────────────────────────────────────────────────────────────
DESC_AMBIENTES = {
    "PRODUCCION (PROD)": ("🔴 Producción",       "Servicios críticos en vivo para el cliente. Cualquier cambio impacta directamente al usuario final.", "amb-prod"),
    "DESARROLLO (DEV)":  ("🟢 Desarrollo",       "Entorno de construcción y pruebas internas del equipo técnico. Sin impacto en producción.",          "amb-dev"),
    "CALIDAD (QA)":   ("🟡 Quality Assurance","Validación de calidad y pruebas de aceptación de usuario antes de subir a producción.",              "amb-qa"),
}

# ─────────────────────────────────────────────────────────────
# Section card — abre / cierra un div con título naranja
# Uso:
#   with section_card("🏢 Cliente"):
#       st.selectbox(...)
# ─────────────────────────────────────────────────────────────
class section_card:
    def __init__(self, title: str):
        self.title = title

    def __enter__(self):
        st.markdown(
            f'<div class="section-card"><div class="card-title">{self.title}</div>',
            unsafe_allow_html=True,
        )
        return self

    def __exit__(self, *_):
        st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# Descripción de ambiente (reactive, read-only)
# ─────────────────────────────────────────────────────────────
def ambiente_desc(ambiente: str):
    titulo, desc, css_cls = DESC_AMBIENTES.get(ambiente, ("", "", ""))
    st.markdown(
        f'<div style="font-size:0.79rem;font-weight:600;color:#4A5568;margin-bottom:4px;">Descripción del ambiente:</div>'
        f'<div class="amb-box {css_cls}"><div class="amb-title">{titulo}</div>{desc}</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# Chip input (texto libre → chips con ➕ y limpiar)
# ─────────────────────────────────────────────────────────────
def chip_input(label: str, session_key: str, placeholder: str = "Escribe y presiona Enter o ➕"):
    """Renderiza un campo con chips editables. Devuelve la lista actual."""
    if session_key not in st.session_state:
        st.session_state[session_key] = []

    input_key  = f"_input_{session_key}"
    clear_key  = f"_clear_input_{session_key}"

    # If a button-add was requested last run, absorb the value now
    # (before the text_input widget is instantiated)
    if st.session_state.get(f"_btn_pending_{session_key}"):
        pending_val = st.session_state.get(input_key, "").strip()
        if pending_val and pending_val not in st.session_state[session_key]:
            st.session_state[session_key].append(pending_val)
        st.session_state[input_key] = ""          # safe: widget not yet rendered
        st.session_state[f"_btn_pending_{session_key}"] = False

    # ── on_change: fires when user presses Enter ──────────
    def _add_chip():
        v = st.session_state.get(input_key, "").strip()
        if v and v not in st.session_state[session_key]:
            st.session_state[session_key].append(v)
        st.session_state[input_key] = ""   # safe inside on_change callback

    chips: list = st.session_state[session_key]

    st.markdown(
        f'<div style="font-size:0.82rem;font-weight:600;color:#4A5568;margin-bottom:6px;">{label}</div>',
        unsafe_allow_html=True,
    )

    # ── Chip display ──────────────────────────────────────
    if chips:
        chip_html = (
            '<div style="display:flex;flex-wrap:wrap;gap:6px;'
            'background:#F9FAFB;border:1.5px solid #E2E6ED;'
            'border-radius:10px;padding:10px 12px;margin-bottom:8px;">'
        )
        for item in chips:
            chip_html += (
                f'<span style="display:inline-flex;align-items:center;gap:5px;'
                f'background:linear-gradient(135deg,#FF7800,#FF9A3C);color:#fff;'
                f'padding:4px 12px;border-radius:20px;font-size:.76rem;font-weight:700;'
                f'box-shadow:0 1px 4px rgba(255,120,0,.3);">'
                f'⚙️ {item}</span>'
            )
        chip_html += "</div>"
    else:
        chip_html = (
            '<div style="background:#F9FAFB;border:1.5px dashed #CBD5E0;'
            'border-radius:10px;padding:10px 12px;margin-bottom:8px;'
            'font-size:.76rem;color:#A0AEC0;font-style:italic;">'
            f'Sin aplicaciones agregadas aún…'
            '</div>'
        )
    st.markdown(chip_html, unsafe_allow_html=True)

    # ── Input + button ────────────────────────────────────
    col_in, col_btn = st.columns([4, 1])
    with col_in:
        st.text_input(
            label, key=input_key,
            label_visibility="collapsed",
            placeholder=placeholder,
            on_change=_add_chip,
        )
    with col_btn:
        if st.button("➕", key=f"_btn_{session_key}", use_container_width=True):
            # Can't modify input widget state after instantiation.
            # Set a flag and rerun — the pending block above handles it next render.
            st.session_state[f"_btn_pending_{session_key}"] = True
            st.rerun()

    if chips:
        if st.button("🗑 Limpiar todo", key=f"_clear_{session_key}"):
            st.session_state[session_key] = []
            st.rerun()

    return st.session_state[session_key]


# ─────────────────────────────────────────────────────────────
# Helpers internos para el dashboard
# ─────────────────────────────────────────────────────────────
def _sc(icon: str, label: str, value, css: str) -> str:
    """Genera HTML de una stat-card."""
    return (
        f'<div class="stat-card {css}">'
        f'<div class="icon">{icon}</div>'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'</div>'
    )


def _prog(label: str, done: int, total: int, color: str = "#FF7800") -> str:
    pct = round((done / total * 100) if total > 0 else 0, 1)
    return (
        f'<div class="prog-wrap">'
        f'<div class="prog-label">{label}</div>'
        f'<div class="prog-bar-bg">'
        f'<div class="prog-bar-fill" style="width:{pct}%;background:{color}"></div>'
        f'</div>'
        f'<div class="prog-counter">{done} de {total} VMs &nbsp;&middot;&nbsp; {pct}%</div>'
        f'</div>'
    )


def _sec_titulo(texto: str) -> str:
    return (
        f'<div style="font-size:0.71rem;font-weight:700;letter-spacing:0.10em;'
        f'text-transform:uppercase;color:#FF7800;margin:22px 0 12px;'
        f'padding-bottom:8px;border-bottom:1.5px solid rgba(255,120,0,0.15);">'
        f'{texto}</div>'
    )


# ─────────────────────────────────────────────────────────────
# Dashboard principal — UN SOLO st.markdown()
# ─────────────────────────────────────────────────────────────
def dashboard_agendados(df_agendadas: pd.DataFrame):
    """
    Construye TODO el HTML del dashboard en una sola cadena y lo emite
    en UN SOLO st.markdown() para evitar que Streamlit escape los divs
    anidados al hacer llamadas separadas.
    """

    # ── Conteos desde VMs agendadas ─────────────────────────
    def _cnt(val: str) -> int:
        return int((df_agendadas["estado"] == val).sum()) if "estado" in df_agendadas.columns else 0

    total_ag    = len(df_agendadas)
    exito       = _cnt("Migrada OK")
    pendientes  = _cnt("Pendiente")
    rollback    = _cnt("Rollback Tras Seguimiento")
    asignadas   = _cnt("Asignada")
    fallidas    = _cnt("Rollback Inmediato")
    seguimiento = _cnt("En Seguimiento")

    # Si no hay columna estado, todas son pendientes
    if "estado" not in df_agendadas.columns:
        pendientes = total_ag

    # ── Totales globales desde DATABASE ─────────────────────
    try:
        conn = sqlite3.connect("migraciones.db")
        total_global = int(pd.read_sql_query("SELECT COUNT(*) AS n FROM DATABASE", conn).iloc[0]["n"])
        conn.close()
    except Exception:
        total_global = total_ag

    no_agendadas = max(total_global - total_ag, 0)

    # ── Construir HTML completo ──────────────────────────────
    html = ""

    # Bloque 1: Globales
    html += _sec_titulo("🌐 Estadísticas Globales del Proyecto")
    html += '<div class="stat-grid stat-grid-3">'
    html += _sc("🗃️", "Total VMs en el Sistema", total_global, "stat-total")
    html += _sc("📅", "VMs Agendadas",            total_ag,    "stat-orange")
    html += _sc("⏸️", "VMs Sin Agendar",          no_agendadas,"stat-pendiente")
    html += '</div>'
    html += _prog(
        "📊 Progreso de Agendamiento — VMs agendadas vs total del proyecto",
        total_ag, total_global, "#FF7800"
    )

    # Bloque 2: Estado de migraciones
    html += _sec_titulo("📋 Estado de Migraciones (VMs Agendadas)")
    html += '<div class="stat-grid">'
    html += _sc("🗄️", "Total Agendadas",              total_ag,             "stat-total")
    html += _sc("✅", "Migrada OK",                         exito,                "stat-exito")
    html += _sc("⏳", "Pendientes",                    pendientes,           "stat-pendiente")
    html += _sc("↩️", "Rollback Tras Seguimiento",                      rollback,             "stat-rollback")
    html += '</div>'
    html += '<div class="stat-grid">'
    html += _sc("⚙️", "Asignadas",                    asignadas,            "stat-asignada")
    html += _sc("❌", "Fallidas",                      fallidas,             "stat-fallida")
    html += _sc("🔍", "En Seguimiento",                seguimiento,          "stat-seguimiento")
    html += _sc("🟢", "Completadas + Seguimiento",     exito + seguimiento,  "stat-exito")
    html += '</div>'
    html += _prog(
        "🚀 Progreso de Migración — Éxito sobre VMs agendadas",
        exito, total_ag, "#38A169"
    )

    # ── Emitir TODO en un solo bloque ───────────────────────
    st.markdown(html, unsafe_allow_html=True)