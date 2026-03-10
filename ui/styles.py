"""
ui/styles.py
Toda la hoja de estilo CSS de la aplicación.
"""

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

:root {
    --orange:        #FF7800;
    --orange-hover:  #E86A00;
    --orange-light:  #FFF0E0;
    --orange-mid:    rgba(255,120,0,0.13);
    --orange-border: rgba(255,120,0,0.35);
    --bg:            #F2F4F7;
    --surface:       #FFFFFF;
    --surface-2:     #F8F9FB;
    --border:        #E2E6ED;
    --text:          #1E2330;
    --text-mid:      #4A5568;
    --text-dim:      #8A95A3;
    --radius:        12px;
    --shadow:        0 1px 4px rgba(0,0,0,0.07), 0 4px 18px rgba(0,0,0,0.05);
}

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    color: var(--text) !important;
}
.stApp { background: var(--bg) !important; }
.main .block-container { padding: 1.6rem 2rem; max-width: 1320px; }

/* ── App Header ───────────────────────────── */
.app-header {
    display:flex; align-items:center; gap:16px;
    padding: 18px 26px; margin-bottom: 22px;
    background: var(--surface);
    border-radius: 14px;
    border-left: 5px solid var(--orange);
    box-shadow: var(--shadow);
}
.app-header .logo {
    width:44px; height:44px;
    background: linear-gradient(135deg, #FF7800 0%, #FF9A3C 100%);
    border-radius: 10px;
    display:flex; align-items:center; justify-content:center;
    font-size:1.3rem; flex-shrink:0;
}
.app-header h1 { font-size:1.4rem; font-weight:800; margin:0; color:var(--text) !important; }
.app-header p  { color:var(--text-dim); font-size:0.81rem; margin:3px 0 0; }

/* ── Tabs ─────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap:4px; background:var(--surface) !important;
    padding:5px 6px; border-radius:10px;
    border:1px solid var(--border); width:fit-content;
    margin-bottom:18px; box-shadow:var(--shadow);
}
.stTabs [data-baseweb="tab"] {
    background:transparent !important; color:var(--text-mid) !important;
    border-radius:7px !important; padding:7px 22px !important;
    font-weight:600 !important; font-size:0.85rem !important;
    border:none !important; transition:all 0.18s;
}
.stTabs [aria-selected="true"] {
    background:var(--orange) !important; color:#fff !important;
    box-shadow:0 2px 8px rgba(255,120,0,0.30) !important;
}
.stTabs [data-baseweb="tab-panel"] { padding-top:0 !important; }

/* ── Section card ─────────────────────────── */
.section-card {
    background:var(--surface);
    border:1px solid var(--border);
    border-radius:var(--radius);
    padding:18px 22px 20px;
    margin-bottom:14px;
    box-shadow:var(--shadow);
}
.section-card .card-title {
    font-size:0.71rem; font-weight:700;
    letter-spacing:0.10em; text-transform:uppercase;
    color:var(--orange); margin-bottom:14px;
    padding-bottom:10px;
    border-bottom:1.5px solid var(--orange-mid);
    display:flex; align-items:center; gap:7px;
}

/* ── Selectbox ────────────────────────────── */
[data-baseweb="select"] > div {
    background:var(--surface-2) !important;
    border-color:var(--border) !important;
    color:var(--text) !important;
    border-radius:8px !important; font-size:0.88rem !important;
}
[data-baseweb="select"] > div:focus-within {
    border-color:var(--orange) !important;
    box-shadow:0 0 0 3px rgba(255,120,0,0.14) !important;
}
[data-baseweb="popover"] [data-baseweb="menu"] {
    background:var(--surface) !important;
    border:1px solid var(--border) !important;
    border-radius:8px !important; box-shadow:var(--shadow) !important;
}
[role="option"] { color:var(--text) !important; font-size:0.86rem !important; }
[role="option"]:hover { background:var(--orange-light) !important; }
[aria-selected="true"] { background:var(--orange-mid) !important; color:var(--orange) !important; font-weight:600 !important; }

/* ── Text / Textarea ──────────────────────── */
.stTextInput input, .stTextArea textarea {
    background:var(--surface-2) !important;
    border-color:var(--border) !important;
    color:var(--text) !important;
    border-radius:8px !important; font-size:0.88rem !important;
    font-family:'Plus Jakarta Sans',sans-serif !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color:var(--orange) !important;
    box-shadow:0 0 0 3px rgba(255,120,0,0.14) !important;
}

/* ── Date / Time ──────────────────────────── */
.stDateInput input, .stTimeInput input {
    background:var(--surface-2) !important;
    border-color:var(--border) !important;
    color:var(--text) !important; border-radius:8px !important;
}
.stDateInput input:focus, .stTimeInput input:focus {
    border-color:var(--orange) !important;
    box-shadow:0 0 0 3px rgba(255,120,0,0.14) !important;
}

/* ── Radio pills ──────────────────────────── */
.stRadio > div { gap:6px !important; flex-wrap:wrap; }
.stRadio label {
    background:var(--surface-2) !important;
    border:1.5px solid var(--border) !important;
    border-radius:8px !important; padding:7px 16px !important;
    color:var(--text-mid) !important; font-size:0.84rem !important;
    font-weight:500 !important; cursor:pointer; transition:all 0.15s;
}
.stRadio label:has(input:checked) {
    background:var(--orange-light) !important;
    border-color:var(--orange) !important;
    color:var(--orange-hover) !important; font-weight:700 !important;
}

/* ── Buttons ──────────────────────────────── */
.stButton > button, .stFormSubmitButton > button {
    background:linear-gradient(135deg,#FF7800 0%,#E86A00 100%) !important;
    color:#fff !important; border:none !important;
    border-radius:9px !important; font-weight:700 !important;
    font-size:0.88rem !important; padding:10px 26px !important;
    box-shadow:0 3px 12px rgba(255,120,0,0.33) !important;
    transition:all 0.18s !important;
}
.stButton > button:hover { transform:translateY(-1px) !important; box-shadow:0 6px 20px rgba(255,120,0,0.44) !important; }

/* ── Chips ────────────────────────────────── */
.chips-wrap {
    display:flex; flex-wrap:wrap; gap:6px;
    padding:9px 11px; min-height:42px;
    background:var(--surface-2);
    border:1.5px solid var(--border);
    border-radius:8px; margin-bottom:6px;
}
.chip {
    display:inline-flex; align-items:center; gap:5px;
    padding:4px 10px; background:var(--orange-mid);
    border:1px solid var(--orange-border);
    color:var(--orange-hover); border-radius:20px;
    font-size:0.78rem; font-weight:600;
}
.chips-empty { color:var(--text-dim); font-size:0.82rem; font-style:italic; }

/* ── Ambiente description box ─────────────── */
.amb-box {
    border-radius:9px; padding:11px 14px;
    font-size:0.83rem; line-height:1.6; font-weight:500;
    margin:4px 0 10px;
}
.amb-prod { background:#FFF5F5; border:1.5px solid #FC8181; color:#822727; }
.amb-dev  { background:#F0FFF4; border:1.5px solid #68D391; color:#22543D; }
.amb-qa   { background:#FFFFF0; border:1.5px solid #ECC94B; color:#744210; }
.amb-title { font-weight:700; margin-bottom:3px; font-size:0.84rem; }

/* ── Stat cards (Ver Agendados) ───────────── */
.stat-grid {
    display:grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 12px;
}
.stat-grid-3 {
    grid-template-columns: repeat(3, 1fr) !important;
}
.stat-card {
    background: var(--surface);
    border: 1.5px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 18px;
    display: flex; flex-direction:column;
    align-items: flex-start; gap: 6px;
    box-shadow: var(--shadow);
    position: relative;
    overflow: hidden;
    transition: transform 0.15s, box-shadow 0.15s;
}
.stat-card::before {
    content:''; position:absolute;
    top:0; left:0; right:0; height:3px;
}
.stat-card:hover { transform:translateY(-2px); box-shadow:0 6px 22px rgba(0,0,0,0.09); }
.stat-card .icon {
    font-size:1.4rem; width:38px; height:38px;
    border-radius:9px;
    display:flex; align-items:center; justify-content:center;
}
.stat-card .label {
    font-size:0.74rem; font-weight:700; letter-spacing:0.04em;
    text-transform:uppercase; color:var(--text-dim);
}
.stat-card .value {
    font-size:2rem; font-weight:800; line-height:1; color:var(--text);
}

/* Color variants */
.stat-total  { border-color:#CBD5E0; }
.stat-total::before { background:#A0AEC0; }
.stat-total .icon  { background:#EDF2F7; }

.stat-exito  { border-color:#9AE6B4; }
.stat-exito::before { background:#38A169; }
.stat-exito .icon  { background:#F0FFF4; }
.stat-exito .value { color:#276749; }

.stat-pendiente { border-color:#FBD38D; }
.stat-pendiente::before { background:#D69E2E; }
.stat-pendiente .icon   { background:#FFFFF0; }
.stat-pendiente .value  { color:#975A16; }

.stat-rollback { border-color:#FEB2B2; }
.stat-rollback::before { background:#E53E3E; }
.stat-rollback .icon   { background:#FFF5F5; }
.stat-rollback .value  { color:#9B2C2C; }

.stat-asignada { border-color:#D6BCFA; }
.stat-asignada::before { background:#805AD5; }
.stat-asignada .icon   { background:#FAF5FF; }
.stat-asignada .value  { color:#553C9A; }

.stat-fallida { border-color:#FEB2B2; }
.stat-fallida::before { background:#C53030; }
.stat-fallida .icon   { background:#FFF5F5; }
.stat-fallida .value  { color:#C53030; }

.stat-seguimiento { border-color:#90CDF4; }
.stat-seguimiento::before { background:#3182CE; }
.stat-seguimiento .icon   { background:#EBF8FF; }
.stat-seguimiento .value  { color:#2B6CB0; }

.stat-orange { border-color:var(--orange-border); }
.stat-orange::before { background:var(--orange); }
.stat-orange .icon   { background:var(--orange-light); }
.stat-orange .value  { color:var(--orange-hover); }

/* ── Progress bar ─────────────────────────── */
.prog-wrap {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); padding:14px 20px;
    margin-bottom:16px; box-shadow:var(--shadow);
}
.prog-label { font-size:0.78rem; font-weight:600; color:var(--text-mid); margin-bottom:8px; }
.prog-bar-bg {
    height:10px; background:var(--surface-2);
    border-radius:99px; overflow:hidden;
    border:1px solid var(--border);
}
.prog-bar-fill {
    height:100%; border-radius:99px;
    background:linear-gradient(90deg,#FF7800,#FF9A3C);
    transition:width 0.5s ease;
}
.prog-counter { font-size:0.78rem; color:var(--text-dim); margin-top:5px; text-align:right; }

/* ── Dataframe ────────────────────────────── */
.stDataFrame { border-radius:var(--radius) !important; overflow:hidden; box-shadow:var(--shadow); }

/* ── Labels ───────────────────────────────── */
label, .stSelectbox label, .stMultiSelect label,
.stTextInput label, .stTextArea label,
.stDateInput label, .stTimeInput label {
    color:var(--text-mid) !important; font-size:0.82rem !important; font-weight:600 !important;
}

/* ── Alerts ───────────────────────────────── */
.stAlert, [data-testid="stNotification"] { border-radius:9px !important; }

/* ── Divider ──────────────────────────────── */
hr { border-color:var(--border) !important; margin:16px 0 !important; }

/* ── Scrollbar ────────────────────────────── */
::-webkit-scrollbar { width:6px; height:6px; }
::-webkit-scrollbar-track { background:var(--bg); }
::-webkit-scrollbar-thumb { background:#CBD5E0; border-radius:99px; }
::-webkit-scrollbar-thumb:hover { background:var(--orange); }
</style>
"""


def inject():
    """Inyecta el CSS global en la app Streamlit."""
    import streamlit as st
    st.markdown(CSS, unsafe_allow_html=True)


def page_header():
    import streamlit as st
    st.markdown("""
    <div class="app-header">
        <div class="logo">⚙️</div>
        <div>
            <h1>Migración RedHat — Ventanas de Mantenimiento</h1>
            <p>Gestión y agendamiento de máquinas virtuales pendientes de migración</p>
        </div>
    </div>
    """, unsafe_allow_html=True)