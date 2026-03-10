"""ui/calendar_utils.py — Event expansion + calendar HTML builder."""

import calendar as cal_mod
import sqlite3
from datetime import date, datetime, timedelta

import pandas as pd
from ui.db_utils import build_column_map, safe_get, DB_PATH

DIAS_ES = {"Lunes":0,"Martes":1,"Miercoles":2,"Jueves":3,"Viernes":4,"Sabado":5,"Domingo":6}
TURNO_HORAS = {"Mañana":("06:00","14:00"),"Tarde":("14:00","22:00"),"Noche":("22:00","06:00")}
ESTADO_COLOR = {
    "Asignada":"#3182CE","Éxito":"#38A169","Pendiente":"#D69E2E",
    "RollBack":"#E53E3E","Fallida":"#C53030","En Seguimiento":"#805AD5",
}
DEFAULT_COLOR = "#FF7800"
MONTH_NAMES_ES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
                  "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
DAY_NAMES_ES   = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]


def _expand_rango(semanas_str, dias_str, year, month):
    last_day = cal_mod.monthrange(year, month)[1]
    semanas  = [s.strip() for s in semanas_str.split(",") if s.strip()]
    dias     = [d.strip() for d in dias_str.split(",")    if d.strip()]
    dia_nums = {DIAS_ES[d] for d in dias if d in DIAS_ES}
    result   = []
    for sem_str in semanas:
        try: sem = int(sem_str)
        except: continue
        s = (sem-1)*7+1
        e = min(s+6, last_day)
        for d in range(s, e+1):
            dt = date(year, month, d)
            if dt.weekday() in dia_nums:
                result.append(dt)
    return result


def _parse_dt(raw):
    for fmt in ("%Y-%m-%d %H:%M:%S","%Y-%m-%d %H:%M","%Y-%m-%d"):
        try: return datetime.strptime(raw.strip()[:19], fmt)
        except: pass
    return None


def get_events_for_month(year, month, cliente_filter=None):
    cm          = build_column_map()
    col_cliente = cm.get("cliente")
    col_vm_id   = cm.get("vm_id")

    conn = sqlite3.connect(DB_PATH)
    try:
        if cliente_filter and col_cliente:
            df = pd.read_sql_query(f'SELECT * FROM VMs WHERE "{col_cliente}"=?',
                                   conn, params=(cliente_filter,))
        else:
            df = pd.read_sql_query("SELECT * FROM VMs", conn)
    except Exception as e:
        print(f"[calendar] {e}"); return {}
    finally:
        conn.close()

    if df.empty: return {}

    out = {}
    for _, row in df.iterrows():
        tipo   = safe_get(row, cm.get("tipo_ventana"))
        estado = safe_get(row, cm.get("estado"),"Asignada") or "Asignada"
        color  = ESTADO_COLOR.get(estado, DEFAULT_COLOR)
        base   = dict(
            vm_id       = safe_get(row, col_vm_id),
            cliente     = safe_get(row, col_cliente),
            ambiente    = safe_get(row, cm.get("ambiente")),
            criticidad  = safe_get(row, cm.get("criticidad")),
            en_uso      = safe_get(row, cm.get("en_uso")),
            apps        = safe_get(row, cm.get("apps")),
            comentarios = safe_get(row, cm.get("comentarios")),
            estado      = estado, tipo_ventana=tipo, color=color,
        )
        slots = []

        if tipo == "Horario Específico":
            sd = _parse_dt(safe_get(row, cm.get("start_dt")))
            ed = _parse_dt(safe_get(row, cm.get("end_dt")))
            if sd and ed:
                cur = sd.date()
                while cur <= ed.date():
                    if cur.year == year and cur.month == month:
                        ts = sd.strftime("%H:%M") if cur==sd.date() else "00:00"
                        te = ed.strftime("%H:%M") if cur==ed.date() else "23:59"
                        slots.append((cur,ts,te))
                    cur += timedelta(days=1)

        elif tipo == "Rango de Horario":
            turno = safe_get(row, cm.get("turno_rango"),"Mañana") or "Mañana"
            ts,te = TURNO_HORAS.get(turno,("06:00","14:00"))
            for d in _expand_rango(safe_get(row, cm.get("semanas_rango")),
                                   safe_get(row, cm.get("dias_rango")), year, month):
                slots.append((d,ts,te))

        elif tipo == "Horario Semi-específico":
            raw_s = safe_get(row, cm.get("start_dt"))
            raw_e = safe_get(row, cm.get("end_dt"))
            ts = raw_s[:5] if len(raw_s)>=5 else "00:00"
            te = raw_e[:5] if len(raw_e)>=5 else "23:59"
            for d in _expand_rango(safe_get(row, cm.get("semanas_rango")),
                                   safe_get(row, cm.get("dias_rango")), year, month):
                slots.append((d,ts,te))

        else:
            sd = _parse_dt(safe_get(row, cm.get("start_dt")))
            if sd and sd.year==year and sd.month==month:
                slots.append((sd.date(), sd.strftime("%H:%M"),"—"))

        for ev_date,ts,te in slots:
            key = ev_date.strftime("%Y-%m-%d")
            out.setdefault(key,[]).append({**base,"start_time":ts,"end_time":te,"date":key})

    return out


# ─── Tooltip HTML ─────────────────────────────────────────────
def _tt(ev):
    apps  = ev["apps"]  if ev["apps"]  not in ("","nan") else "—"
    com   = ev["comentarios"] if ev["comentarios"] not in ("","nan") else "—"
    badge = ESTADO_COLOR.get(ev["estado"], DEFAULT_COLOR)
    amb   = ev["ambiente"].lower() if ev["ambiente"] else ""
    def r(k,v): return f'<div class="tr"><b>{k}</b><span>{v}</span></div>'
    return (
        f'<div class="tt"><div class="th">{ev["vm_id"] or "VM"}</div>'
        + r("Cliente",   ev["cliente"] or "—")
        + r("Horario",   f'{ev["start_time"]} – {ev["end_time"]}')
        + r("Ambiente",  f'<span class="a{amb}">{ev["ambiente"] or "—"}</span>')
        + r("Criticidad",ev["criticidad"] or "—")
        + r("Estado",    f'<span class="badge" style="background:{badge}">{ev["estado"]}</span>')
        + r("Apps",      apps)
        + f'<hr/>'+ r("Notas", f'<i>{com}</i>') + '</div>'
    )


def build_calendar_html(year, month, events_by_date, selected_date=None, selected_vm_id=None):
    first_wd, num_days = cal_mod.monthrange(year, month)
    today   = date.today()
    MAX_EV  = 3

    CSS = """
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
    html,body{background:#F2F4F7;font-family:'Plus Jakarta Sans',sans-serif;}
    body{padding:4px 6px;}

    .grid{
        display:grid;
        grid-template-columns:repeat(7,minmax(0,1fr));
        gap:3px;
        width:100%;
    }

    .hdr{
        text-align:center;font-size:.62rem;font-weight:800;
        letter-spacing:.08em;text-transform:uppercase;
        color:#FF7800;padding:3px 0 6px;
    }

    .day{
        background:#fff;border:1.5px solid #E8ECF1;border-radius:8px;
        padding:5px 4px 4px;min-height:75px;overflow:hidden;
        transition:border-color .12s,box-shadow .12s;
    }
    .day:hover{border-color:#FF9A3C;box-shadow:0 2px 8px rgba(255,120,0,.13);}
    .day.empty{background:transparent;border-color:transparent;}
    .day.today{border-color:#FF7800;border-width:2px;}
    .day.sel{background:#FFF6EE;border-color:#FF7800;border-width:2px;}
    .day.sel .dn{color:#FF7800;}

    .dn{
        font-size:.7rem;font-weight:800;color:#2D3748;
        margin-bottom:3px;line-height:1;display:inline-block;
    }
    .day.today .dn{
        background:#FF7800;color:#fff;border-radius:50%;
        width:18px;height:18px;display:inline-flex;
        align-items:center;justify-content:center;font-size:.62rem;
    }

    .pills{display:flex;flex-direction:column;gap:2px;overflow:hidden;}

    .pill{
        font-size:.56rem;font-weight:700;color:#fff;
        padding:1px 4px;border-radius:3px;
        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
        position:relative;cursor:default;
        max-width:100%;
    }

    /* Tooltip on pill hover */
    .pill:hover .tt{display:block;}
    .tt{
        display:none;position:absolute;
        left:calc(100% + 6px);top:-4px;
        z-index:99999;background:#fff;
        border:1px solid #E2E6ED;border-radius:10px;
        padding:10px 12px;min-width:220px;max-width:260px;
        box-shadow:0 8px 24px rgba(0,0,0,.12);
        pointer-events:none;font-size:.71rem;
        white-space:normal;
    }
    .pill:hover .tt.fl{left:auto;right:calc(100% + 6px);}

    .th{font-size:.8rem;font-weight:800;color:#1E2330;margin-bottom:6px;
        padding-bottom:5px;border-bottom:1.5px solid #F0F2F5;}
    .tr{display:flex;gap:5px;margin-bottom:3px;align-items:flex-start;line-height:1.35;}
    .tr b{color:#8A95A3;font-weight:700;min-width:60px;flex-shrink:0;font-size:.64rem;}
    .tr span{color:#2D3748;font-weight:500;font-size:.67rem;}
    .badge{color:#fff;padding:1px 6px;border-radius:20px;font-size:.63rem;font-weight:700;}
    .aprod{color:#822727;background:#FFF5F5;padding:0 4px;border-radius:3px;}
    .adev {color:#22543D;background:#F0FFF4;padding:0 4px;border-radius:3px;}
    .aqa  {color:#744210;background:#FFFFF0;padding:0 4px;border-radius:3px;}
    hr{border:none;border-top:1px solid #F0F2F5;margin:4px 0;}

    .more{font-size:.54rem;color:#A0AEC0;font-weight:700;
          padding:0 2px;margin-top:1px;letter-spacing:.01em;}
    """

    body = '<div class="grid">'
    for d in DAY_NAMES_ES:
        body += f'<div class="hdr">{d}</div>'
    for _ in range(first_wd):
        body += '<div class="day empty"></div>'

    for day in range(1, num_days+1):
        d   = date(year, month, day)
        key = d.strftime("%Y-%m-%d")
        evs = events_by_date.get(key, [])

        cls = "day"
        if d == today:         cls += " today"
        if d == selected_date: cls += " sel"

        body += f'<div class="{cls}"><div class="dn">{day}</div><div class="pills">'

        for ev in evs[:MAX_EV]:
            flip = " fl" if d.weekday() >= 5 else ""
            body += (
                f'<div class="pill" style="background:{ev["color"]}">'
                f'{ev["vm_id"] or "VM"}'
                f'<div class="tt{flip}">{_tt(ev)}</div></div>'
            )
        ov = len(evs) - MAX_EV
        if ov > 0:
            body += f'<div class="more">+{ov} más</div>'

        body += '</div></div>'

    for _ in range((7-(first_wd+num_days)%7)%7):
        body += '<div class="day empty"></div>'
    body += '</div>'

    return (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<style>{CSS}</style></head><body>{body}</body></html>')


def events_to_df(events):
    if not events: return pd.DataFrame()
    return pd.DataFrame([{
        "VM ID":      e["vm_id"],
        "Cliente":    e["cliente"],
        "Horario":    f'{e["start_time"]} – {e["end_time"]}',
        "Tipo":       e["tipo_ventana"],
        "Ambiente":   e["ambiente"],
        "Criticidad": e["criticidad"],
        "Estado":     e["estado"],
        "Apps":       e["apps"],
    } for e in events])