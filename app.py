"""Streamlit darbo grafikų skaičiuoklė (3 žmonės, 2 grupės)."""
from __future__ import annotations

import hmac
import io
from html import escape
from calendar import monthcalendar
import os
import sqlite3
import re
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from saugykla import read_setting, restore_remote, save_remote, remote_configured

from grafiko_rodymas import month_annotations, group_month_entries
from grafiko_logika import (DAYS, GROUPS, TARGET_PCT, WEEK_HOURS, MONTH_NAMES,
                            _scheduled_hours, get_holidays, calculate_month, selected_employee_report, suggest_hours_from_text,
                            cumulative_group_debts, employee_cumulative_view)

st.set_page_config(page_title="Darbo grafikų skaičiuoklė", page_icon="📅", layout="wide")
st.markdown("""<style>
.block-container {padding-top: 1.6rem; max-width: 1350px;}
div[data-testid='stMetricValue'] {font-size: 1.7rem;}
</style>""", unsafe_allow_html=True)

# Tikroji darbo valandų ir skolų apskaita prasideda 2026-10-01.
ACCOUNTING_START_YEAR, ACCOUNTING_START_MONTH = 2026, 10

DB_PATH = Path(os.getenv("GRAFIKAS_DB", str(Path(__file__).with_name("grafikas.sqlite3"))))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def db_conn():
    """Lokali SQLite; esant sukonfigūruotai debesijos saugyklai – kopija po pakeitimų."""
    con = sqlite3.connect(DB_PATH, timeout=15)
    try:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=15000")
        changes_before = con.total_changes
        yield con
        con.commit()
        changed = con.total_changes > changes_before
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    if changed and remote_configured():
        save_remote(DB_PATH)


@st.cache_resource(show_spinner=False)
def initialize_storage_once():
    """Vienąkart po debesijos perkrovimo atkuria patvarią duomenų kopiją."""
    if remote_configured():
        restore_remote(DB_PATH)
    init_db()
    return True


def init_db():
    with db_conn() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS employees (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS allocations (
            employee_id INTEGER NOT NULL, group_name TEXT NOT NULL, pct REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (employee_id, group_name));
        CREATE TABLE IF NOT EXISTS weekdays (
            employee_id INTEGER NOT NULL, group_name TEXT NOT NULL, weekday INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 0,
            hours REAL DEFAULT NULL,
            PRIMARY KEY (employee_id, group_name, weekday));
        CREATE TABLE IF NOT EXISTS absences (
            id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL,
            kind TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL, note TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS substitutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL,
            employee_id INTEGER NOT NULL, replaced_id INTEGER,
            group_name TEXT NOT NULL, hours REAL NOT NULL, mode TEXT NOT NULL,
            source_group TEXT, note TEXT DEFAULT '', purpose TEXT NOT NULL DEFAULT 'Pavadavimas');
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL,
            employee_id INTEGER NOT NULL, group_name TEXT NOT NULL,
            delta_hours REAL NOT NULL, note TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, note TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS temporary_increases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL, group_name TEXT NOT NULL,
            start_date TEXT NOT NULL, end_date TEXT NOT NULL,
            additional_pct REAL NOT NULL, note TEXT DEFAULT '');
        """)
        # Senesnių DB atnaujinimas nekeičiant jau įrašytų mėnesių.
        sub_fields = {r[1] for r in db.execute("PRAGMA table_info(substitutions)")}
        if "purpose" not in sub_fields:
            db.execute("ALTER TABLE substitutions ADD COLUMN purpose TEXT NOT NULL DEFAULT 'Pavadavimas'")
        # Suderinamumas su seniau sukurta duomenų baze.
        fields = {r[1] for r in db.execute("PRAGMA table_info(weekdays)").fetchall()}
        if "hours" not in fields:
            db.execute("ALTER TABLE weekdays ADD COLUMN hours REAL DEFAULT NULL")
        if db.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
            # Tikrieji pradiniai duomenys: 3 darbuotojos, 2 grupės.
            people = [(1, "Diana"), (2, "Renata"), (3, "Vilma")]
            percentages = {
                (1, "Žiogeliai"): 75.0, (1, "Žirniukai"): 50.0,
                (2, "Žiogeliai"): 125.0, (2, "Žirniukai"): 0.0,
                (3, "Žiogeliai"): 0.0, (3, "Žirniukai"): 150.0,
            }
            # Pirmadienis=0 ... penktadienis=4; 12 val. pamainos.
            fixed_hours = {
                (1, "Žiogeliai"): [0, 12, 0, 12, 0],
                (1, "Žirniukai"): [0, 0, 12, 0, 0],
                (2, "Žiogeliai"): [12, 0, 12, 0, 12],
                (2, "Žirniukai"): [0, 0, 0, 0, 0],
                (3, "Žiogeliai"): [0, 0, 0, 0, 0],
                (3, "Žirniukai"): [12, 12, 0, 12, 12],
            }
            for eid, name in people:
                db.execute("INSERT INTO employees(id, name) VALUES (?, ?)", (eid, name))
                for group in GROUPS:
                    db.execute("INSERT INTO allocations VALUES (?,?,?)",
                               (eid, group, percentages[(eid, group)]))
                    for wd, h in enumerate(fixed_hours[(eid, group)]):
                        db.execute("""INSERT INTO weekdays(employee_id,group_name,weekday,active,hours)
                                      VALUES (?,?,?,?,?)""",
                                   (eid, group, wd, int(h > 0), float(h)))



def rows(sql, args=()):
    with db_conn() as db:
        return [dict(r) for r in db.execute(sql, args).fetchall()]


def execute(sql, args):
    with db_conn() as db:
        db.execute(sql, args)
        db.commit()


def load_state():
    employees = rows("SELECT id, name FROM employees ORDER BY id")
    allocations = {(r["employee_id"], r["group_name"]): r["pct"]
                   for r in rows("SELECT * FROM allocations")}
    flags = {(r["employee_id"], r["group_name"], r["weekday"]):
             (float(r["hours"]) if r["hours"] is not None else bool(r["active"]))
             for r in rows("SELECT * FROM weekdays")}
    absences = rows("SELECT * FROM absences ORDER BY id")
    substitutions = [
        {**r, "group": r["group_name"]}
        for r in rows("SELECT * FROM substitutions ORDER BY id")
    ]
    corrections = [
        {**r, "group": r["group_name"]}
        for r in rows("SELECT * FROM corrections ORDER BY id")
    ]
    notes = rows("SELECT * FROM notes ORDER BY id")
    temporary_increases = [{**r, "group": r["group_name"]}
                           for r in rows("SELECT * FROM temporary_increases ORDER BY id")]
    return employees, allocations, flags, absences, substitutions, corrections, notes, temporary_increases


def authorized_role():
    admin = read_setting("GRAFIKAS_ADMIN_PASSWORD")
    viewer = read_setting("GRAFIKAS_VIEW_PASSWORD")
    viewer2 = read_setting("GRAFIKAS_VIEW2_PASSWORD")
    if not admin:
        if os.getenv("GRAFIKAS_ALLOW_DEMO") == "1":
            return "admin", False
        st.error("Nenustatytas redaktoriaus slaptažodis. Pridėkite GRAFIKAS_ADMIN_PASSWORD „Streamlit“ skiltyje Secrets.")
        st.stop()
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = ""
    if st.session_state.authenticated in ("admin", "viewer"):
        return st.session_state.authenticated, True
    st.title("📅 Darbo grafikų skaičiuoklė")
    with st.form("prisijungimas"):
        pw = st.text_input("Įveskite prieigos slaptažodį", type="password")
        login = st.form_submit_button("Prisijungti")
    if login:
        if hmac.compare_digest(pw, admin):
            st.session_state.authenticated = "admin"
            st.rerun()
        elif (viewer and hmac.compare_digest(pw, viewer)) or (viewer2 and hmac.compare_digest(pw, viewer2)):
            st.session_state.authenticated = "viewer"
            st.rerun()
        else:
            st.error("Neteisingas slaptažodis.")
    st.stop()


def friendly_dataframe(records, key, height=330):
    if records:
        st.dataframe(pd.DataFrame(records), hide_index=True,
                     use_container_width=True, height=height, key=key)
    else:
        st.info("Šiuo metu įrašų nėra.")


def settings_page(employees, allocations, flags):
    st.subheader("1. Pradiniai nustatymai")
    st.caption("100 % = 30 val. per savaitę. Darbo krūviai nusako mėnesio VALANDŲ NORMĄ, "
               "o įprasti 12 val. pamainų grafikai generuoja konkrečių mėnesio dienų valandas. "
               "Savaitinis grafikas neturi tiksliai sutapti su darbo krūvio procentais.")
    # Saugus numatytasis režimas: baziniai grafikai matomi, bet neredaguojami.
    # Tik redaktoriui sąmoningai paspaudus mygtuką parodomi įvesties laukai.
    if "fixed_schedule_edit_mode" not in st.session_state:
        st.session_state.fixed_schedule_edit_mode = False
    edit_mode = bool(st.session_state.fixed_schedule_edit_mode)
    if edit_mode:
        st.warning("Įjungtas pastovių grafikų redagavimas. Pakeitimai įsigalios tik "
                   "atskirai patvirtinus kiekvieną išsaugojimą. Dėmesio: šiame prototipe "
                   "pakeitus bazinį grafiką anksčiau įvesti mėnesiai perskaičiuojami "
                   "pagal naująjį grafiką. Ateities pakeitimams būtina grafiko versijų apskaita.")
        if st.button("🔒 Baigti redagavimą ir užrakinti", type="secondary", key="lock_fixed_schedules"):
            st.session_state.fixed_schedule_edit_mode = False
            st.rerun()
    else:
        st.success("🔒 Pastovūs grafikai užrakinti. Juos galima peržiūrėti, bet netyčia pakeisti neįmanoma.")
        if st.button("✏️ Redaguoti pastovius grafikus", type="primary", key="unlock_fixed_schedules"):
            st.session_state.fixed_schedule_edit_mode = True
            st.rerun()
        preview = []
        for emp in employees:
            for group in GROUPS:
                eid = emp["id"]
                d = {"Darbuotojas": emp["name"], "Grupė": group,
                     "Krūvis (%)": float(allocations.get((eid, group), 0))}
                for wd, label in enumerate(DAYS):
                    d[f"{label} (val.)"] = round(_scheduled_hours(eid, group, wd, allocations, flags), 2)
                d["Savaitė (val.)"] = round(sum(d[f"{label} (val.)"] for label in DAYS), 2)
                preview.append(d)
        st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)
        st.caption("Parodytos visų trijų darbuotojų abiejų grupių valandos, tik pirmadienis–penktadienis. "
                   "Mėnesio pakeitimus registruokite kitame meniu; pastovaus grafiko jie nekeičia.")
        return

    data = []
    for emp in employees:
        record = {"ID": emp["id"], "Darbuotojas": emp["name"]}
        for group in GROUPS:
            record[f"{group} (%)"] = float(allocations.get((emp["id"], group), 0))
        data.append(record)
    with st.form("settings_personal"):
        changed = st.data_editor(
            pd.DataFrame(data), use_container_width=True, hide_index=True,
            disabled=["ID"], num_rows="fixed",
            column_config={"ID": None, "Darbuotojas": st.column_config.TextColumn(required=True),
                           **{f"{g} (%)": st.column_config.NumberColumn(
                               min_value=0.0, max_value=200.0, step=1.0, format="%.1f") for g in GROUPS}},
            key="settingsemployees")
        confirm_personal = st.checkbox("Patvirtinu, kad noriu pakeisti vardus ir / arba etatų procentus", key="confirm_personal")
        pressed = st.form_submit_button("Išsaugoti vardus ir krūvius", type="primary")
    if pressed and not confirm_personal:
        st.error("Prieš išsaugodami pažymėkite pakeitimo patvirtinimą.")
    if pressed and confirm_personal:
        names = [str(x).strip() for x in changed["Darbuotojas"]]
        if not all(names) or len(set(n.casefold() for n in names)) != 3:
            st.error("Įveskite tris skirtingus darbuotojų vardus.")
        elif changed[[f"{g} (%)" for g in GROUPS]].isna().any().any():
            st.error("Visi krūviai turi būti užpildyti.")
        elif any(float(row[f"{g} (%)"]) < 0 or float(row[f"{g} (%)"]) > 150
                 for _, row in changed.iterrows() for g in GROUPS):
            st.error("Vienos grupės procentai turi būti nuo 0 iki 150 %.")
        elif any(sum(float(row[f"{g} (%)"]) for g in GROUPS) > 150.001
                 for _, row in changed.iterrows()):
            st.error("Bendras darbuotojos krūvis abiejose grupėse negali viršyti 150 %.")
        else:
            with db_conn() as db:
                for _, rec in changed.iterrows():
                    eid = int(rec["ID"])
                    db.execute("UPDATE employees SET name=? WHERE id=?", (rec["Darbuotojas"].strip(), eid))
                    for group in GROUPS:
                        next_pct = float(rec[f"{group} (%)"])
                        old_pct = float(allocations.get((eid, group), 0))
                        db.execute("UPDATE allocations SET pct=? WHERE employee_id=? AND group_name=?",
                                   (next_pct, eid, group))
                        # Procento pakeitimas niekada automatiškai nekeičia įprastų pamainų.

                db.commit()
            st.success("Duomenys išsaugoti.")
            st.rerun()

    totals = {group: sum(float(allocations.get((p["id"], group), 0)) for p in employees)
              for group in GROUPS}
    c1, c2 = st.columns(2)
    for col, group in zip((c1, c2), GROUPS):
        with col:
            st.metric(group, f"{totals[group]:g} % / {TARGET_PCT[group]:g} %",
                      delta=f"{(totals[group] - TARGET_PCT[group]):g} proc. p.")
            if abs(totals[group] - TARGET_PCT[group]) > 0.01:
                st.warning(f"{group}: darbuotojų krūvių suma neatitinka grupės {TARGET_PCT[group]:g} %.")

    st.markdown("**Savaitinis paskirstymas pagal žmones**")
    week_table = []
    for person in employees:
        p = person["id"]
        x, y = (float(allocations.get((p, g), 0)) for g in GROUPS)
        week_table.append({"Darbuotojas": person["name"], "Žiogeliai (%)": x,
                           "Žirniukai (%)": y, "Iš viso (%)": x + y,
                           "Iš viso (val./sav.)": round((x + y) * WEEK_HOURS / 100, 2)})
    st.dataframe(pd.DataFrame(week_table), hide_index=True, use_container_width=True)
    st.subheader("2. Pastovus savaitės grafikas")
    st.write("Pažymėkite įprastas savaitės dienas (Pr–Pn). Tikslias 12 val. "
             "pamainas patikrinkite lentelėje žemiau. Procentai ir savaitės "
             "pamainų valandų suma neprivalo sutapti.")
    wd_records = []
    for e in employees:
        for g in GROUPS:
            r = {"ID": e["id"], "Darbuotojas": e["name"], "Grupė": g}
            for i, day_name in enumerate(DAYS):
                r[day_name] = bool(flags.get((e["id"], g, i), False))
            wd_records.append(r)
    with st.form("schedule_form"):
        edited = st.data_editor(pd.DataFrame(wd_records), hide_index=True, use_container_width=True,
                                disabled=["ID", "Darbuotojas", "Grupė"],
                                column_config={"ID": None}, num_rows="fixed", key="weekday_editor")
        confirm_days = st.checkbox("Patvirtinu, kad noriu keisti pastovias savaitės dienas", key="confirm_days")
        save_days = st.form_submit_button("Išsaugoti savaitės dienas")
    if save_days and not confirm_days:
        st.error("Prieš išsaugodami pažymėkite pakeitimo patvirtinimą.")
    if save_days and confirm_days:
        errors = []
        for _, record in edited.iterrows():
            if allocations.get((int(record["ID"]), record["Grupė"]), 0.0) > 0 and not any(
                bool(record[d]) for d in DAYS
            ):
                errors.append(f"{record['Darbuotojas']}, {record['Grupė']}: pasirinkite bent vieną dieną.")
        if errors:
            st.error("\n\n".join(errors))
        else:
            with db_conn() as db:
                for _, record in edited.iterrows():
                    for wd, day_name in enumerate(DAYS):
                        db.execute("""UPDATE weekdays SET active=?,hours=NULL
                                      WHERE employee_id=? AND group_name=? AND weekday=?""",
                                   (int(bool(record[day_name])), int(record["ID"]), record["Grupė"], wd))
                db.commit()
            st.success("Pastovus grafikas išsaugotas.")
            st.rerun()
    with st.expander("Visų 3 darbuotojų tikslios dienos valandos (jei valandos nevienodos)", expanded=True):
        st.caption("Visi trys darbuotojai, abi grupės. Tiksliai įveskite įprastų pamainų "
                   "valandas; jų nereikia sulyginti su savaitiniais krūvio procentais.")
        hours_records = []
        for e in employees:
            for g in GROUPS:
                r = {"ID": e["id"], "Darbuotojas": e["name"], "Grupė": g}
                for wd, name in enumerate(DAYS):
                    r[name] = round(_scheduled_hours(e["id"], g, wd, allocations, flags), 2)
                r["Iš viso"] = round(sum(r[x] for x in DAYS), 2)
                hours_records.append(r)
        with st.form("hours_all_three"):
            hours_edited = st.data_editor(
                pd.DataFrame(hours_records), hide_index=True, use_container_width=True,
                disabled=["ID", "Darbuotojas", "Grupė", "Iš viso"], num_rows="fixed",
                column_config={"ID": None, **{
                    d: st.column_config.NumberColumn(d, min_value=0.0, max_value=24.0, step=0.25, format="%.2f")
                    for d in DAYS}}, key="all_three_hours")
            confirm_hours = st.checkbox("Patvirtinu, kad noriu pakeisti tikslias dienų valandas", key="confirm_hours")
            save_hours = st.form_submit_button("Išsaugoti tikslias visų darbuotojų valandas")
            if save_hours and not confirm_hours:
                st.error("Prieš išsaugodami pažymėkite pakeitimo patvirtinimą.")
            if save_hours and confirm_hours:
                if hours_edited[list(DAYS)].isna().any().any():
                    st.error("Užpildykite visų darbo dienų valandas (nedirbamoms dienoms – 0).")
                    st.stop()
                with db_conn() as db:
                    for _, row in hours_edited.iterrows():
                        for wd, name in enumerate(DAYS):
                            hrs = float(row[name])
                            db.execute("""INSERT INTO weekdays(employee_id,group_name,weekday,active,hours)
                                          VALUES(?,?,?,?,?) ON CONFLICT(employee_id,group_name,weekday)
                                          DO UPDATE SET active=excluded.active,hours=excluded.hours""",
                                       (int(row["ID"]), row["Grupė"], wd, int(hrs > 0), hrs))
                    st.success("Visų trijų darbuotojų valandos išsaugotos.")
                    st.rerun()
    for emp in employees:
        total = []
        for wd in range(5):
            hrs = sum(_scheduled_hours(emp["id"], group, wd, allocations, flags) for group in GROUPS)
            if hrs > 12:
                total.append(f"{DAYS[wd]} – {hrs:.2f} val.")
        if total:
            st.warning(f"{emp['name']}: ilgos dienos ({', '.join(total)}). Patikrinkite grafiką.")
    st.info("Grafikas automatiškai kartojamas pagal **tikras mėnesio datas**. Lietuvos švenčių dienomis "
            "visos trys darbuotojos nedirba. Šventės neįskaitomos į neatvykimus ar valandų skolas. "
            "Prieššventinės dienos automatiškai netrumpinamos.")


# Tik šios aiškiai išvardytos lentelės leidžiamos trinimo funkcijoje.
DELETABLE_EVENT_TABLES = frozenset({"absences", "substitutions", "corrections",
                                   "notes", "temporary_increases"})


def event_delete_table(table, records, label, admin, year, month, cols):
    """Įrašų sąrašas su dviem apsaugomis: pasirinkti ir patvirtinti šalinimą."""
    if table not in DELETABLE_EVENT_TABLES:
        raise ValueError("Neleistinas įrašų tipas.")
    relevant = [r for r in records if (r.get("day", r.get("start_date", ""))[:7] <= f"{year}-{month:02d}"
                and r.get("end_date", r.get("day", "9999"))[:7] >= f"{year}-{month:02d}")]
    st.markdown(f"**{label} ({len(relevant)})**")
    if not relevant:
        st.caption("Įrašų nėra.")
        return
    pending_key = f"delete_pending_{table}"
    for r in reversed(relevant):
        entry_id = int(r["id"])
        left, right = st.columns([9, 1])
        with left:
            st.caption(" | ".join(f"{title}: {r.get(field, '')}" for field, title in cols))
        with right:
            if admin and st.button("🗑️ Trinti", key=f"del_{table}_{entry_id}"):
                st.session_state[pending_key] = entry_id
                st.rerun()
        if admin and st.session_state.get(pending_key) == entry_id:
            st.warning("Ar tikrai norite ištrinti šį įrašą? Jį pašalinus "
                       "mėnesio grafikai ir skolų balansai bus perskaičiuoti.")
            confirm, cancel = st.columns(2)
            if confirm.button("Taip, ištrinti", type="primary", key=f"yes_del_{table}_{entry_id}"):
                execute(f"DELETE FROM {table} WHERE id=?", (entry_id,))
                st.session_state.pop(pending_key, None)
                st.rerun()
            if cancel.button("Atšaukti", key=f"no_del_{table}_{entry_id}"):
                st.session_state.pop(pending_key, None)
                st.rerun()


def changes_page(year, month, employees, allocations, absences, substitutions, corrections, notes, temporary_increases):
    st.subheader("Mėnesio pakeitimai")
    st.caption("Pavadavimai, skolų dengimas, atostogos, liga ir papildomos valandos. Grafikai sudaromi pirmadieniui–penktadieniui; "
               "šeštadieniai ir sekmadieniai nerodomi, o šventės – laisvos visoms ir skolų nesukuria.")
    names = {e["id"]: e["name"] for e in employees}
    ids = list(names)
    today = date(year, month, min(date.today().day, 28))
    t1, t2, t3 = st.tabs(["Atostogos", "Pavadavimai ir skolų dengimas",
                          "Viršvalandžiai / kiti pakeitimai"])
    with t1:
        with st.form("add_absence", clear_on_submit=True):
            person = st.selectbox("Darbuotojas", ids, format_func=names.get, key="abs_person")
            absence_kind = st.radio("Neatvykimas", ["Atostogos", "Liga"], horizontal=True)
            a, b = st.columns(2)
            start = a.date_input("Nuo", value=today, format="DD.MM.YYYY")
            end = b.date_input("Iki (imtinai)", value=today, format="DD.MM.YYYY")
            note = st.text_input("Pastaba (nebūtina)")
            if st.form_submit_button("Pridėti neatvykimą", type="primary"):
                overlaps = any(x["employee_id"] == person and
                               x["start_date"] <= end.isoformat() and x["end_date"] >= start.isoformat()
                               for x in absences)
                if end < start:
                    st.error("Pabaigos data negali būti ankstesnė už pradžią.")
                elif overlaps:
                    st.error("Šiam darbuotojui šiuo laikotarpiu jau yra neatvykimas.")
                else:
                    execute("INSERT INTO absences(employee_id,kind,start_date,end_date,note) VALUES(?,?,?,?,?)",
                            (person, absence_kind, start.isoformat(), end.isoformat(), note))
                    st.rerun()
        with st.expander("Įvesti neatvykimai", expanded=True):
            shown = [{**a, "darbuotojas": names.get(a["employee_id"], "?")}
                     for a in absences]
            event_delete_table("absences", shown, "Neatvykimai", True, year, month,
                               [("darbuotojas", "Darbuotojas"), ("kind", "Tipas"),
                                ("start_date", "Nuo"), ("end_date", "Iki")])
        st.divider()
        st.markdown("#### Atostogų metu taikomas etatas")
        st.info("**Atostogų laikotarpiu** galima nustatyti kitai darbuotojai didesnį laikiną etatą. "
                "Bendras krūvis abiejose grupėse negali viršyti **150 %**. "
                "Pagal padidintą etatą papildomai dirbtos valandos (iki jo laikinos normos) "
                "**nekuria tarpusavio skolos ir nelaikomos viršvalandžiais**. "
                "Neišdirbta padidinto etato dalis taip pat **nesukuria skolos**. "
                "Tikras papildomas darbas vis tiek įrašomas „Pavadavimai“ arba „Viršvalandžiai“ skiltyje. "
                "Pastovūs grafikai ir pradiniai procentai nesikeičia.")
        with st.form("add_temporary_increase", clear_on_submit=True):
            selected = st.selectbox("Kas pavaduos atostogų metu?", ids,
                                    format_func=names.get, key="temp_employee")
            group = st.selectbox("Kurioje grupėje?", GROUPS, key="temp_group")
            a, b = st.columns(2)
            start = a.date_input("Atostogų laikotarpis nuo", today, format="DD.MM.YYYY", key="temp_from")
            end = b.date_input("Iki (imtinai)", today, format="DD.MM.YYYY", key="temp_to")
            base_ziog = float(allocations.get((selected, GROUPS[0]), 0.0))
            base_zirn = float(allocations.get((selected, GROUPS[1]), 0.0))
            base_total = base_ziog + base_zirn
            max_extra = max(0., 150. - base_total)
            st.caption(f"Pastovus krūvis: {base_total:g} % "
                       f"({GROUPS[0]} {base_ziog:g} %, {GROUPS[1]} {base_zirn:g} %). "
                       f"Galima papildomai iki {max_extra:g} proc. punktų.")
            new_total = st.number_input("Atostogų metu bendras etatas (%)", min_value=0.0,
                                        max_value=150.0,
                                        value=float(min(150., base_total + max_extra)), step=5.0,
                                        key="temporary_new_total")
            explanation = st.text_input("Pastaba, pvz. kieno atostogas dengia (nebūtina)",
                                        key="temporary_note")
            if st.form_submit_button("Išsaugoti atostogų laikotarpį", type="primary"):
                additional = round(new_total - base_total, 4)
                overlaps = any(int(t["employee_id"]) == selected and
                               t["start_date"] <= end.isoformat() and t["end_date"] >= start.isoformat()
                               for t in temporary_increases)
                if end < start:
                    st.error("Laikotarpio pabaiga negali būti ankstesnė už pradžią.")
                elif additional <= 0:
                    st.error("Laikinas bendras procentas turi viršyti pastovų darbuotojos procentą.")
                elif new_total > 150.001:
                    st.error("Bendras krūvis negali viršyti 150 %.")
                elif overlaps:
                    st.error("Šiai darbuotojai jau įvestas persidengiantis atostogų laikotarpio etatas. "
                             "Jei norite pakeisti, pirmiausia pašalinkite ankstesnį įrašą.")
                else:
                    execute("""INSERT INTO temporary_increases
                               (employee_id,group_name,start_date,end_date,additional_pct,note)
                               VALUES (?,?,?,?,?,?)""",
                            (selected, group, start.isoformat(), end.isoformat(), additional, explanation))
                    st.rerun()
        with st.expander("Įvesti atostogų laikotarpio etatai", expanded=True):
            shown = [{**t, "darbuotojas": names.get(t["employee_id"], "?"),
                      "laikinas bendras (%)": round(sum(float(allocations.get((int(t['employee_id']), g), 0))
                                                        for g in GROUPS) + float(t["additional_pct"]), 2)}
                     for t in temporary_increases]
            event_delete_table("temporary_increases", shown, "Atostogų laikotarpio etatai", True, year, month,
                               [("darbuotojas", "Darbuotoja"), ("group", "Grupė"),
                                ("start_date", "Nuo"), ("end_date", "Iki"),
                                ("additional_pct", "Pridėta proc. p."),
                                ("laikinas bendras (%)", "Bendras laikinas krūvis (%)")])

    with t2:
        st.info("**Kaip grąžinti skolą?** Jei A skolingas B 2 val. Žiogeliuose, "
                "įrašykite: **kas dirbo – A**, **už ką – B**, **Žiogeliai**, **2 val.**, "
                "paskirtis – *Ankstesnės skolos dengimas*. B numatytas darbo laikas "
                "sumažės 2 val., A padidės 2 val. Skola užskaitoma būtent tarp A ir B, "
                "o likutis persikels į kitą mėnesį. Atostogos ir liga asmeninės skolos nesukuria.")
        with st.form("add_replacement", clear_on_submit=True):
            purpose_label = st.radio("Pavadavimo paskirtis",
                                     ["Pavadavimas", "Ankstesnės skolos dengimas"], horizontal=True)
            day = st.date_input("Pavadavimo diena", value=today, format="DD.MM.YYYY")
            x, y = st.columns(2)
            replacement = x.selectbox("Kas dirbo?", ids, format_func=names.get)
            replaced = y.selectbox("Už kurį kolegą dirbo?", [None, *[i for i in ids if i != replacement]],
                                   format_func=lambda i: "Nenurodyta" if i is None else names[i])
            group = st.selectbox("Kurioje grupėje?", GROUPS)
            hours = st.number_input("Kiek valandų?", min_value=0.25, max_value=24.0, value=2.0, step=0.25)
            mode_label = st.radio("Pavadavimo būdas",
                                  ["Papildomai išdirbtos valandos", "Valandos perkeltos iš kitos grupės"],
                                  horizontal=True)
            more_note = st.text_input("Pastaba", key="replacement_note")
            if st.form_submit_button("Įrašyti pavadavimą", type="primary"):
                mode = "extra" if mode_label.startswith("Papildomai") else "transfer"
                source = next((g for g in GROUPS if g != group), None) if mode == "transfer" else None
                if day.weekday() >= 5:
                    st.error("Pavadavimas įvedamas tik darbo dienomis (Pr–Pn).")
                elif day in get_holidays(day.year):
                    st.error("Šventinė diena – visos darbuotojos laisvos; pavadavimas neįskaitomas.")
                elif purpose_label == "Ankstesnės skolos dengimas" and replaced is None:
                    st.error("Skolos dengimui būtina nurodyti konkretų kolegą.")
                elif purpose_label == "Ankstesnės skolos dengimas" and any(
                        a["employee_id"] == replaced and a["start_date"] <= day.isoformat() <= a["end_date"]
                        for a in absences):
                    st.error("Kolega atostogauja ar serga: pateisintos neatvykimo valandos nėra asmeninė skola.")
                elif any(a["employee_id"] == replacement and a["start_date"] <= day.isoformat() <= a["end_date"]
                         for a in absences):
                    st.error("Pavaduojantis darbuotojas tą dieną pažymėtas neatvykusiu.")
                else:
                    # Patikriname, ar valandų perkėlimas iš kitos grupės techniškai galimas.
                    if mode == "transfer":
                        current_employees, alloc, weekday_flags, aa, ss, cc, _, tt = load_state()
                        calc = calculate_month(day.year, day.month, current_employees, alloc,
                                               weekday_flags, aa, ss, cc, temporary_increases=tt)
                        available = next((r["actual"] for r in calc["daily"] if
                                          r["date"] == day and r["employee_id"] == replacement
                                          and r["group"] == source), 0.0)
                        if available + 0.00001 < hours:
                            st.error(f"Šią dieną grupėje „{source}“ turima tik {available:.2f} val. "
                                     "Pasirinkite mažesnį kiekį arba papildomą darbą.")
                            st.stop()
                    if purpose_label == "Ankstesnės skolos dengimas":
                        if mode != "extra":
                            st.error("Skolos dengimui rinkitės papildomas valandas, o ne perkėlimą iš kitos grupės.")
                            st.stop()
                        current_employees, alloc, weekday_flags, aa, ss, cc, _, tt = load_state()
                        calc = calculate_month(day.year, day.month, current_employees, alloc,
                                               weekday_flags, aa, ss, cc, temporary_increases=tt)
                        available_replaced = next((r["actual"] for r in calc["daily"] if
                                                   r["date"] == day and r["employee_id"] == replaced and
                                                   r["group"] == group), 0)
                        if available_replaced + .001 < hours:
                            st.error(f"Kolega tą dieną turi tik {available_replaced:g} val. grupėje „{group}“. "
                                     "Kad grąžinimas būtų užskaitytas, įveskite faktiškai perimtas valandas.")
                            st.stop()
                    execute("""INSERT INTO substitutions(day,employee_id,replaced_id,group_name,hours,
                              mode,source_group,note,purpose) VALUES (?,?,?,?,?,?,?,?,?)""",
                            (day.isoformat(), replacement, replaced, group, hours, mode, source,
                             more_note, purpose_label))
                    st.rerun()
        with st.expander("Įvesti pavadavimai", expanded=True):
            shown = [{**s, "darbuotojas": names.get(s["employee_id"], "?"),
                      "pavaduotas": names.get(s["replaced_id"], "—"),
                      "valandos": f"{s['hours']:g}",
                      "tipas": "papildomai" if s["mode"] == "extra" else "perkėlimas",
                      "paskirtis": s.get("purpose", "Pavadavimas")}
                     for s in substitutions]
            event_delete_table("substitutions", shown, "Pavadavimai", True, year, month,
                               [("day", "Data"), ("darbuotojas", "Kas"),
                                ("pavaduotas", "Ką"), ("group", "Grupė"),
                                ("valandos", "Valandos"), ("tipas", "Būdas"), ("paskirtis", "Paskirtis")])
    with t3:
        st.write("**Laisvas tekstas**: galima išsaugoti bet kokią pastabą arba paprašyti "
                 "atpažinti paprastą valandų pakeitimą. Programa skaičių **nekeičia be "
                 "jūsų patvirtinimo**. Sudėtingiems pakeitimams naudokite laukus žemiau.")
        with st.form("add_note", clear_on_submit=False):
            nd = st.date_input("Įvykio data", today, format="DD.MM.YYYY", key="note_day")
            raw = st.text_area("Kas pasikeitė?", placeholder="Pvz.: Darbuotojas A Žirniukuose dirbo 2 val. ilgiau.")
            b1, b2 = st.columns(2)
            save_text = b1.form_submit_button("Išsaugoti pastabą")
            interpret = b2.form_submit_button("Atpažinti valandų pokytį")
            if save_text:
                if not raw.strip():
                    st.error("Įveskite tekstą.")
                else:
                    execute("INSERT INTO notes(day, note) VALUES (?, ?)", (nd.isoformat(), raw.strip()))
                    st.success("Pastaba išsaugota; valandų skaičiavimo nekeičia.")
            if interpret:
                proposal = suggest_hours_from_text(raw, employees)
                if proposal:
                    st.session_state["text_proposal"] = {**proposal, "day": nd.isoformat(), "note": raw}
                else:
                    st.session_state.pop("text_proposal", None)
                    st.warning("Nepavyko patikimai atpažinti vieno žmogaus, grupės ir valandų pokyčio. "
                               "Įrašykite koregavimą ranka žemiau.")
        proposal = st.session_state.get("text_proposal")
        if proposal:
            st.info(f"Atpažinta: {names.get(proposal['employee_id'], '?')} · "
                    f"{proposal['group']} · {proposal['day']} · "
                    f"{proposal['delta_hours']:+g} val. Patikrinkite prieš patvirtindami.")
            pc1, pc2 = st.columns(2)
            if pc1.button("Patvirtinti ir įskaityti", key="confirm_text"):
                proposal_day = date.fromisoformat(proposal["day"])
                if proposal_day.weekday() >= 5 or proposal_day in get_holidays(proposal_day.year):
                    st.error("Koregavimas negalimas savaitgalį ar šventinę dieną.")
                    st.stop()
                execute("""INSERT INTO corrections(day,employee_id,group_name,delta_hours,note)
                           VALUES(?,?,?,?,?)""", (proposal['day'],proposal['employee_id'],
                               proposal['group'],proposal['delta_hours'],proposal['note']))
                del st.session_state["text_proposal"]
                st.rerun()
            if pc2.button("Atšaukti siūlymą", key="cancel_text"):
                del st.session_state["text_proposal"]
                st.rerun()
        st.markdown("**Viršvalandžiai ir skaitinis koregavimas.** Įveskite, kiek valandų pridėti (+) "
                    "ar atimti (−) konkrečioje grupėje. Neįvardyto kolegos skola nepriskiriama "
                    "automatiškai, jei galimi keli variantai; tokios valandos liks asmeniniame likutyje.")
        with st.form("add_correction", clear_on_submit=True):
            cd = st.date_input("Koregavimo data", today, format="DD.MM.YYYY", key="corr_day")
            person = st.selectbox("Darbuotojas", ids, format_func=names.get, key="corr_person")
            cg = st.selectbox("Grupė", GROUPS, key="corr_group")
            delta = st.number_input("Valandų pokytis (+ / −)", min_value=-24.0, max_value=24.0,
                                    value=1.0, step=0.25)
            cn = st.text_input("Paaiškinimas", key="corr_note")
            if st.form_submit_button("Įrašyti valandų koregavimą"):
                if cd.weekday() >= 5:
                    st.error("Koregavimas įvedamas tik darbo dienomis (Pr–Pn).")
                elif cd in get_holidays(cd.year):
                    st.error("Šventinė diena – visos darbuotojos laisvos; koregavimas neįskaitomas.")
                elif abs(delta) < 0.001:
                    st.error("Valandų pokytis negali būti nulis.")
                else:
                    execute("""INSERT INTO corrections(day, employee_id, group_name, delta_hours, note)
                              VALUES(?,?,?,?,?)""", (cd.isoformat(), person, cg, delta, cn))
                    st.rerun()
        with st.expander("Išsaugoti kitų pakeitimų įrašai", expanded=True):
            shown = [{**c, "darbuotojas": names.get(c["employee_id"], "?")}
                     for c in corrections]
            event_delete_table("corrections", shown, "Valandų koregavimai", True, year, month,
                               [("day", "Data"), ("darbuotojas", "Darbuotojas"),
                                ("group", "Grupė"), ("delta_hours", "Val.")])
            event_delete_table("notes", notes, "Pastabos", True, year, month,
                               [("day", "Data"), ("note", "Pastaba")])




def build_views(calc, employees):
    df = pd.DataFrame(calc["daily"])
    summary = pd.DataFrame(calc["people"])
    groups = pd.DataFrame(calc["groups"])
    comparisons = pd.DataFrame(calc["comparisons"])
    if df.empty:
        return df, summary, groups, comparisons
    df["Data"] = df["date"].map(lambda d: d.strftime("%Y-%m-%d"))
    df["Savaitės diena"] = df["date"].map(lambda d: DAYS[d.weekday()])
    return df, summary, groups, comparisons


def render_month_calendar(person_rows: pd.DataFrame, year: int, month: int,
                          event_labels=None):
    """Mėnesio kalendorius su neatvykimais, pavadavimais ir visais valandų pakeitimais."""
    event_labels = event_labels or {}
    day_lookup = {}
    for d, pieces in person_rows.groupby("date"):
        day_lookup[d.day] = list(pieces.to_dict("records"))
    tiles = []
    for week in monthcalendar(year, month):
        for number in week[:5]:
            if number == 0:
                tiles.append('<div class="cal-empty"></div>')
                continue
            day_rows = day_lookup.get(number, [])
            absent = next((r["absence"] for r in day_rows if r["absence"]), "")
            holiday = next((r["holiday"] for r in day_rows if r["holiday"]), "")
            total = sum(r["actual"] for r in day_rows)
            badges = []
            if holiday:
                badges.append('<div class="cal-holiday">' + escape(holiday) + ' · laisva</div>')
            else:
                if absent:
                    badges.append(f'<div class="cal-away">{escape(absent)}</div>')
                for row in day_rows:
                    if row["actual"] > 0.001:
                        cls = "cal-ziog" if row["group"] == "Žiogeliai" else "cal-zirn"
                        badges.append(f'<div class="{cls}">{escape(row["group"])}: {row["actual"]:g} val.</div>')
                date_key = date(year, month, number)
                for annotation in event_labels.get(date_key, []):
                    if annotation["kind"] == "absence":
                        continue  # Neatvykimas jau pateiktas viršuje.
                    cls = {'cover': 'cal-change', 'covered': 'cal-covered',
                           'change': 'cal-change', 'temporary': 'cal-temporary'}.get(
                               annotation['kind'], 'cal-change')
                    badges.append(f'<div class="{cls}">{escape(annotation["text"])}</div>')
            if not badges:
                badges.append('<div class="cal-off">Laisva</div>')
            tiles.append(f'<div class="cal-day"><div class="cal-date">{number}'
                         + (f'<span>{total:g} val.</span>' if total else '')
                         + '</div>' + ''.join(badges) + '</div>')
    headers = ''.join(f'<div class="cal-head">{escape(d)}</div>' for d in DAYS)
    html = """<style>
    .workcal{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px}
    .cal-head{font-weight:700;font-size:12px;text-align:center;color:#5a6e7d}
    .cal-day,.cal-empty{min-height:108px;border:1px solid #e0e7ed;border-radius:9px;padding:8px;overflow-wrap:anywhere;background:#fff}
    .cal-empty{background:#f5f7fa;border-color:#f5f7fa}
    .cal-date{font-weight:700;font-size:13px;display:flex;justify-content:space-between;gap:2px;margin-bottom:5px}
    .cal-date span{font-size:11px;color:#627384;font-weight:500}
    .cal-ziog,.cal-zirn,.cal-away,.cal-off,.cal-holiday,.cal-change,.cal-covered,.cal-temporary{border-radius:5px;font-size:11px;padding:4px 5px;margin:3px 0;line-height:1.32}
    .cal-ziog{background:#e7f3ff;color:#125b8a}.cal-zirn{background:#fff1d9;color:#885a12}
    .cal-away{background:#ffebed;color:#b71f3d}.cal-off{color:#9aa6b2}
    .cal-holiday{background:#eee9fc;color:#564189}
    .cal-change{background:#e7f7ed;color:#176544}.cal-covered{background:#e8f0fa;color:#2a547b}
    .cal-temporary{background:#f5eafa;color:#71419a}
    @media(max-width:680px){.cal-day{min-height:75px;padding:4px}.cal-date span{display:none}.cal-ziog,.cal-zirn,.cal-away,.cal-off,.cal-holiday,.cal-change,.cal-covered,.cal-temporary{font-size:9px;padding:2px}}
    </style>""" + f'<div class="workcal">{headers}{"".join(tiles)}</div>'
    st.markdown(html, unsafe_allow_html=True)
    st.caption("Mėlyna – Žiogeliai · Geltona – Žirniukai · Raudona – atostogos / liga · "
               "Žalia – pavadavimai ir valandų pakeitimai · Violetinė – šventė / atostogų etatas")



def render_group_month_calendar(group: str, cells: list[dict], year: int, month: int):
    """Vienos grupės Pr–Pn kalendorius, rodomos visų 3 darbuotojų pamainos."""
    by_day = {item["date"].day: item for item in cells}
    tiles = []
    for week in monthcalendar(year, month):
        for number in week[:5]:
            if not number:
                tiles.append('<div class="group-empty"></div>')
                continue
            data = by_day[number]
            badges = []
            if data["holiday"]:
                badges.append(f'<div class="group-holiday">{escape(data["holiday"])} · visoms laisva</div>')
            else:
                for person in data["staff"]:
                    name = escape(person["name"])
                    actual = person["hours"]
                    if person["absence"]:
                        badges.append(f'<div class="group-away">{name}: {escape(person["absence"])}</div>')
                    elif actual > 0.001:
                        badges.append(f'<div class="group-worker">{name}: <b>{actual:g} val.</b></div>')
                    elif person["replaced_by"]:
                        badges.append(f'<div class="group-covered">{name}: pavaduoja {escape(person["replaced_by"])}</div>')
                if not data["staff"]:
                    badges.append('<div class="group-off">Šią dieną pamainų nėra</div>')
                for note in data["annotations"]:
                    badges.append(f'<div class="group-note">{escape(note)}</div>')
            tiles.append('<div class="group-day">'
                         f'<div class="group-date">{number}<span>{data["total_hours"]:g} val.</span></div>'
                         + "".join(badges) + '</div>')
    style = """<style>
    .groupcal{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px}
    .group-head{text-align:center;font-size:13px;font-weight:700;color:#506479;padding:4px}
    .group-day,.group-empty{border:1px solid #dbe3eb;border-radius:9px;min-height:122px;padding:7px;overflow-wrap:anywhere;background:white}
    .group-empty{background:#f6f8fa;border-color:transparent}
    .group-date{display:flex;justify-content:space-between;gap:3px;font-weight:750;font-size:13px;margin-bottom:5px}
    .group-date span{color:#66788a;font-weight:500;font-size:11px}
    .group-worker,.group-away,.group-holiday,.group-covered,.group-off,.group-note{font-size:11px;line-height:1.3;margin:3px 0;padding:4px;border-radius:5px}
    .group-worker{color:#165880;background:#e7f2fb}
    .group-away{color:#ad2440;background:#ffe9eb}
    .group-holiday{background:#eee9fb;color:#5e4295}
    .group-covered{background:#f9eddf;color:#86612f}
    .group-note{background:#e9f8ed;color:#17613f}
    .group-off{color:#8594a3}
    @media(max-width:690px){.group-day{min-height:82px;padding:4px}.group-date span{display:none}.group-worker,.group-away,.group-holiday,.group-covered,.group-off,.group-note{font-size:9px;padding:2px}}
    </style>"""
    heads = "".join(f'<div class="group-head">{escape(wd)}</div>' for wd in DAYS)
    st.markdown(style + f'<div class="groupcal">{heads}{"".join(tiles)}</div>',
                unsafe_allow_html=True)
    st.caption(f"{group}: faktinės valandos. Pamainos rodomos kiekvienai darbuotojai atskirai; "
               "atostogos, pavadavimai, korekcijos ir šventės pažymėtos kalendoriuje.")


def group_month_table(cells: list[dict], employees: list[dict]) -> pd.DataFrame:
    """Pr–Pn datos ir visų darbuotojų valandos vienos grupės Excel eksportui."""
    result = []
    for entry in cells:
        record = {"Data": entry["date"].isoformat(),
                  "Diena": DAYS[entry["date"].weekday()]}
        for employee in employees:
            this_person = next((p for p in entry["staff"] if p["employee_id"] == employee["id"]), None)
            record[f"{employee['name']} (val.)"] = this_person["hours"] if this_person else 0.0
            record[f"{employee['name']} (pastaba)"] = (
                this_person["absence"] or ("Pavadavo " + this_person["replaced_by"]
                if this_person["replaced_by"] else "") if this_person else "")
        record["Viso (val.)"] = entry["total_hours"]
        record["Šventė"] = entry["holiday"]
        record["Pakeitimai"] = "; ".join(entry["annotations"])
        result.append(record)
    return pd.DataFrame(result)


def dashboard_page(year, month, employees, alloc, flags, absences, substitutions, corrections, notes, temporary_increases):
    calc = calculate_month(year, month, employees, alloc, flags,
                           absences, substitutions, corrections,
                           temporary_increases=temporary_increases)
    df, summary, groups, comparisons = build_views(calc, employees)
    st.subheader(f"{year} m. {month:02d} mėn. grafikai ir rezultatai")
    for w in calc["warnings"]:
        st.warning(w)
    actual = float(summary["Iš viso dirbta"].sum())
    planned = float(summary["Iš viso planas"].sum())
    a, b, c, d = st.columns(4)
    a.metric("Bendras planas", f"{planned:.1f} val.")
    b.metric("Faktiškai dirbta", f"{actual:.1f} val.", delta=f"{actual - planned:+.1f} val.")
    c.metric("Žiogeliai", f"{groups.iloc[0]['Dirbta (val.)']:.1f} val.")
    d.metric("Žirniukai", f"{groups.iloc[1]['Dirbta (val.)']:.1f} val.")

    st.markdown("#### 1. Darbuotojų valandų suvestinė")
    st.dataframe(summary, hide_index=True, use_container_width=True)
    st.markdown("#### 2. Grupės užimtumas")
    st.dataframe(groups, hide_index=True, use_container_width=True)
    st.caption("„Balansui taikomas planas“ – pagal sutartą krūvį (100 % = 30 val./sav.) ir konkretaus mėnesio datas, "
               "atėmus darbuotojos pastovias pamainas, kurios sutampa su šventėmis. "
               "Šventės nei sukuria skolą, nei tariamą viršvalandį. Tai tarpusavio valandų, o ne darbo užmokesčio norma. "
               "„Dirbta“ – pagal 12 val. pamainas ir mėnesio pakeitimus.")

    st.markdown("#### 3. Bendras mėnesio grafikas pagal grupę")
    st.caption("Pasirinkite grupę. Kalendoriuje vienoje vietoje matomos visų trijų darbuotojų "
               "dienos, valandos, atostogos, pavadavimai ir kiti pakeitimai. "
               "Šeštadieniai ir sekmadieniai nerodomi.")
    group_tabs = st.tabs(list(GROUPS))
    for tab, group in zip(group_tabs, GROUPS):
        with tab:
            cells = group_month_entries(year, month, group, calc["daily"], employees,
                                        absences, substitutions, corrections, temporary_increases,
                                        calc["holiday_names"])
            render_group_month_calendar(group, cells, year, month)
            group_frame = group_month_table(cells, employees)
            with st.expander(f"{group}: visų dienų lentelė", expanded=False):
                st.dataframe(group_frame, hide_index=True, use_container_width=True, height=380)
            excel_out = io.BytesIO()
            with pd.ExcelWriter(excel_out, engine="openpyxl") as writer:
                group_frame.to_excel(writer, index=False, sheet_name="Grupės mėnesio grafikas")
                ws = writer.book.active
                ws.freeze_panes = "C2"
                ws.auto_filter.ref = ws.dimensions
                for column in ws.columns:
                    max_len = max(len(str(cell.value or "")) for cell in column)
                    ws.column_dimensions[column[0].column_letter].width = min(58, max(13, max_len + 2))
            st.download_button(f"📥 {group}: atsisiųsti mėnesio grafiką (Excel)",
                               data=excel_out.getvalue(),
                               file_name=f"{('ziogeliai' if group == GROUPS[0] else 'zirniukai')}_{year}_{month:02d}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key=f"group_month_export_{group}_{year}_{month}")

    st.markdown("#### 4. Darbuotojų mėnesio kalendoriai (tik Pr–Pn)")
    st.caption("Visų trijų žmonių mėnesio grafikai rodomi viename puslapyje. "
               "Atostogos, ligos, pavadavimai, skolų dengimas, papildomos valandos ir laikinas atostogų etatas "
               "atsispindi konkrečiomis datomis. Valandos perskaičiuojamos automatiškai.")
    for emp in employees:
        part = df[df["employee_id"] == emp["id"]] if not df.empty else pd.DataFrame()
        st.markdown(f"**{escape(emp['name'])}**")
        if not part.empty:
            labels, _ = month_annotations(year, month, emp["id"], employees, alloc,
                                           absences, substitutions, corrections,
                                           temporary_increases, notes, calc["holidays"])
            render_month_calendar(part, year, month, labels)
            view = part.pivot_table(index=["Data", "Savaitės diena"], columns="group",
                                    values="actual", aggfunc="sum", fill_value=0).reset_index()
            for g in GROUPS:
                if g not in view.columns:
                    view[g] = 0.0
            view["Iš viso"] = view[list(GROUPS)].sum(axis=1)
            view["Neatvykimas"] = part.groupby("Data")["absence"].first().values
            view["Pakeitimai"] = view["Data"].map(lambda iso: "; ".join(
                a["text"] for a in labels.get(date.fromisoformat(iso), [])
                if a["kind"] != "absence"))
            with st.expander(f"{emp['name']}: dienų lentelė"):
                st.dataframe(view.round(2), hide_index=True, use_container_width=True, height=300)
    month_notes = [n for n in notes if n["day"].startswith(f"{year}-{month:02d}")]
    if month_notes:
        with st.expander("Bendros mėnesio pastabos", expanded=True):
            st.dataframe(pd.DataFrame([{"Data": n["day"], "Pastaba": n["note"]} for n in month_notes]),
                         hide_index=True, use_container_width=True)


def reports_page(year, month, employees, alloc, flags, absences, substitutions, corrections, notes, temporary_increases):
    """Vienam darbuotojui: mėnesio grafikas + atskirai pernešami poriniai grupių likučiai."""
    st.subheader(f"Mano valandų balansas — {year} m. {MONTH_NAMES[month - 1].lower()}")
    selected_id = st.selectbox("Kieno ataskaitą rodyti?", [e["id"] for e in employees],
                               format_func=lambda eid: next(e["name"] for e in employees if e["id"] == eid),
                               key="report_selected_person_id")
    selected_name = next(e["name"] for e in employees if e["id"] == selected_id)
    carry = cumulative_group_debts(year, month, employees, alloc, flags, absences,
                                   substitutions, corrections,
                                   start_year=ACCOUNTING_START_YEAR,
                                   start_month=ACCOUNTING_START_MONTH,
                                   temporary_increases=temporary_increases)
    calc = carry["current_calc"]
    df, _, _, _ = build_views(calc, employees)
    selected, personal_rows, _ = selected_employee_report(calc["people"], selected_name)
    own_daily = df[df["employee_id"] == selected_id].copy() if not df.empty else pd.DataFrame()
    st.caption("Skaičiuojama pagal kiekvieno žmogaus asmeninį planą. Šventės yra laisvos visoms ir "
               "nesukuria nei skolų, nei viršvalandžių. Žiogelių ir Žirniukų likučiai atskiri. "
               "Ankstesnių mėnesių likučiai perkeliami automatiškai.")
    st.markdown(f"### {escape(selected_name)}")

    cols = st.columns(2)
    for col, item in zip(cols, personal_rows):
        group = item["Grupė"]
        unassigned = carry["closing_unmatched"].get((group, selected_id), 0.0)
        with col:
            st.markdown(f"**{group}**")
            st.metric("Šio mėnesio asmeninis balansas", f"{item['Balansas (val.)']:+.1f} val.")
            st.caption(f"Planas {item['Planuota (val.)']:g} val. · "
                       f"Dirbta {item['Dirbta (val.)']:g} val. · "
                       f"Pateisintas neatvykimas {item['Pateisinti neatvykimai (val.)']:g} val.")
            if item.get("Laikino padidinimo norma (val.)", 0) > 0.001:
                st.caption(f"Atostogų laikotarpio papildoma norma "
                           f"{item['Laikino padidinimo norma (val.)']:g} val.; "
                           f"į skolų balansą neįtraukta "
                           f"{item['Neįtraukta į skolą (val.)']:g} faktiškai pridėtų val.")
            if abs(unassigned) > 0.005:
                st.caption(f"Nepriskirtas sukauptas likutis: {unassigned:+.1f} val. "
                           "(kuriam kolegai priklauso, dar nepatvirtinta).")

    st.markdown("#### Tarpusavio valandų likutis (iki pasirinkto mėnesio pabaigos)")
    st.caption("**+** kolega skolingas man; **−** aš skolingas kolegai; **0** atsiskaityta. "
               "Lentelė rodo likutį po šio mėnesio, įskaitant ankstesnius mėnesius.")
    relations = employee_cumulative_view(carry, selected_id, employees)
    view = pd.DataFrame([{
        "Kolega": r["Kolega"],
        "Žiogeliai (val.)": r["Žiogeliai: Likutis"],
        "Žirniukai (val.)": r["Žirniukai: Likutis"],
    } for r in relations])
    st.dataframe(view.style.format({"Žiogeliai (val.)": "{:+.1f}",
                                     "Žirniukai (val.)": "{:+.1f}"}),
                 hide_index=True, use_container_width=True)
    with st.expander("Kaip likutis pasikeitė šį mėnesį?", expanded=False):
        movements = [{"Kolega": r["Kolega"],
                      "Žiogeliai: iš praeito mėn.": r["Žiogeliai: Ankstesnis likutis"],
                      "Žiogeliai: pokytis": r["Žiogeliai: Mėnesio pokytis"],
                      "Žiogeliai: likutis": r["Žiogeliai: Likutis"],
                      "Žirniukai: iš praeito mėn.": r["Žirniukai: Ankstesnis likutis"],
                      "Žirniukai: pokytis": r["Žirniukai: Mėnesio pokytis"],
                      "Žirniukai: likutis": r["Žirniukai: Likutis"]} for r in relations]
        st.dataframe(pd.DataFrame(movements), hide_index=True, use_container_width=True)
        st.caption("Pavadavus kolegą per jo atostogas ar ligą, jam asmeninė skola nesusidaro. "
                   "Kai neįmanoma nustatyti konkrečios poros, likutis saugomas atskirai, "
                   "o ne priskiriamas atsitiktiniam kolegai.")
        if carry["changes"]:
            st.dataframe(pd.DataFrame(carry["changes"]), hide_index=True, use_container_width=True)

    personal_table = pd.DataFrame(personal_rows)
    with st.expander("Mano planas, faktiškai dirbta ir neatvykimai"):
        st.dataframe(personal_table, hide_index=True, use_container_width=True)
    with st.expander("Mano mėnesio grafikas (tik Pr–Pn)"):
        if not own_daily.empty:
            own_table = own_daily[["Data", "Savaitės diena", "group", "planned", "actual",
                                   "absence", "extra", "transferred", "replaces", "replaced_by"]].rename(columns={
                "group": "Grupė", "planned": "Planuota (val.)", "actual": "Dirbta (val.)",
                "absence": "Neatvykimas", "extra": "Papildoma (val.)",
                "transferred": "Perkelta (val.)", "replaces": "Ką pavadavo",
                "replaced_by": "Kas pavadavo"})
            own_labels, _ = month_annotations(year, month, selected_id, employees, alloc,
                                              absences, substitutions, corrections,
                                              temporary_increases, [], calc["holidays"])
            own_table["Pakeitimai"] = own_table["Data"].map(lambda iso: "; ".join(
                a["text"] for a in own_labels.get(date.fromisoformat(iso), [])
                if a["kind"] != "absence"))
            st.dataframe(own_table, hide_index=True, use_container_width=True, height=330)
        else:
            own_table = pd.DataFrame()
            st.info("Šį mėnesį suplanuotų darbo dienų nėra.")

    # Tikros .xlsx skaitinės valandos; atskiri mėnesio įvykiai ir perkeltas likutis.
    mem = io.BytesIO()
    with pd.ExcelWriter(mem, engine="openpyxl") as writer:
        view.to_excel(writer, index=False, sheet_name="Skolos iki menesio galo")
        pd.DataFrame(relations).to_excel(writer, index=False, sheet_name="Likutis ir pokytis")
        personal_table.to_excel(writer, index=False, sheet_name="Mano valandos")
        if not own_table.empty:
            own_table.to_excel(writer, index=False, sheet_name="Dienu grafikas")
        this_month = f"{year}-{month:02d}"
        current_absences = [r for r in absences if r["employee_id"] == selected_id and
                            r["start_date"][:7] <= this_month <= r["end_date"][:7]]
        current_subs = [r for r in substitutions if r["day"][:7] == this_month and
                        (r["employee_id"] == selected_id or r.get("replaced_id") == selected_id)]
        current_corr = [r for r in corrections if r["day"][:7] == this_month and
                        r["employee_id"] == selected_id]
        if current_absences:
            pd.DataFrame(current_absences).to_excel(writer, index=False, sheet_name="Neatvykimai")
        if current_subs:
            pd.DataFrame(current_subs).to_excel(writer, index=False, sheet_name="Pavadavimai")
        if current_corr:
            pd.DataFrame(current_corr).to_excel(writer, index=False, sheet_name="Viršvalandziai")
        current_temporary = [t for t in temporary_increases if int(t["employee_id"]) == selected_id
                             and t["start_date"][:7] <= this_month <= t["end_date"][:7]]
        if current_temporary:
            pd.DataFrame(current_temporary).to_excel(writer, index=False, sheet_name="Atostogų etatas")
        if carry["changes"]:
            pd.DataFrame(carry["changes"]).to_excel(writer, index=False, sheet_name="Skolu judejimas")
        leftovers = [{"Grupė": group,
                      "Ankstesnis": carry["opening_unmatched"][(group, selected_id)],
                      "Pokytis": carry["monthly_unmatched"][(group, selected_id)],
                      "Likutis": carry["closing_unmatched"][(group, selected_id)]} for group in GROUPS]
        pd.DataFrame(leftovers).to_excel(writer, index=False, sheet_name="Nepriskirtos valandos")
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for cells in ws.columns:
                width = min(43, max(13, max(len(str(c.value or "")) for c in cells) + 2))
                ws.column_dimensions[cells[0].column_letter].width = width
        for ws_name in ("Skolos iki menesio galo", "Likutis ir pokytis"):
            ws = writer.book[ws_name]
            for row in ws.iter_rows(min_row=2, min_col=2):
                for cell in row:
                    if isinstance(cell.value, (float, int)):
                        cell.number_format = '+0.0;−0.0;0.0'
    safe_name = re.sub(r"[^\w-]+", "_", selected_name, flags=re.UNICODE).strip("_") or "darbuotojas"
    st.download_button("📥 Atsisiųsti mėnesio ataskaitą (Excel)", data=mem.getvalue(),
                       file_name=f"balansas_{safe_name}_{year}_{month:02d}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if calc["warnings"]:
        with st.expander("Skaičiavimo pastabos"):
            for warning in calc["warnings"]:
                st.warning(warning)


def main():
    initialize_storage_once()
    role, secured = authorized_role()
    admin = role == "admin"
    st.title("📅 Darbo grafikų skaičiuoklė")
    st.caption("Žiogeliai • Žirniukai • 3 darbuotojai • 100 % = 30 val./sav. • Grupėms po 200 %")
    if not secured:
        st.warning("Vietinis demonstracinis režimas: prieigos slaptažodžiai nenustatyti. "
                   "Neskelbkite programos internete be autentifikacijos.")
    else:
        st.sidebar.write("Prisijungta: " + ("redagavimas" if admin else "tik peržiūra"))
        if st.sidebar.button("Atsijungti"):
            st.session_state.authenticated = ""
            st.rerun()
    year = st.sidebar.number_input("Metai", 2020, 2100, value=date.today().year, step=1)
    month = st.sidebar.selectbox("Mėnuo", range(1, 13), index=date.today().month - 1,
                                 format_func=lambda m: MONTH_NAMES[m-1])
    if (int(year), int(month)) < (ACCOUNTING_START_YEAR, ACCOUNTING_START_MONTH):
        st.info("Apskaita pradedama 2026 m. spalį. Ankstesnių skolų nėra (0 val.).")
        st.stop()
    employees, allocations, flags, absences, substitutions, corrections, notes, temporary_increases = load_state()
    views = ["Mėnesio grafikai", "Mėnesio ataskaitos"]
    if admin:
        views += ["Mėnesio pakeitimai", "Pradiniai grafikai"]
    tab = st.sidebar.radio("Meniu", views)
    if tab == "Pradiniai grafikai":
        settings_page(employees, allocations, flags)
    elif tab == "Mėnesio pakeitimai":
        changes_page(year, month, employees, allocations, absences, substitutions, corrections, notes, temporary_increases)
    elif tab == "Mėnesio ataskaitos":
        reports_page(year, month, employees, allocations, flags, absences, substitutions, corrections, notes, temporary_increases)
    else:
        dashboard_page(year, month, employees, allocations, flags, absences, substitutions, corrections, notes, temporary_increases)
    st.sidebar.divider()
    if remote_configured():
        st.sidebar.caption("Duomenys saugomi patvarioje Supabase saugykloje (sinchronizuota SQLite kopija).")
    else:
        st.sidebar.error("Šiame serveryje nustatyta tik vietinė SQLite saugykla. "
                         "Streamlit Community Cloud ji gali būti ištrinta po perkrovimo. "
                         "Prieš naudojimą sukonfigūruokite Supabase.")


if __name__ == "__main__":
    main()
