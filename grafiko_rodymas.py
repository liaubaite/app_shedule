"""Aiškios mėnesio kalendoriaus žymos pagal išsaugotus mėnesio pakeitimus."""
from __future__ import annotations
from collections import defaultdict
from datetime import date


def month_annotations(year, month, person_id, employees, allocations, absences,
                      substitutions, corrections, temporary_increases, notes,
                      holidays=()):
    """Grąžina (datos -> žymos, bendros mėnesio pastabos).

    Žymos yra informacinės: faktines valandas skaičiuoja calculate_month.
    Šventinėmis dienomis neatvykimai ir pakeitimai neįskaitomi.
    """
    person_id = int(person_id)
    names = {int(p['id']): p['name'] for p in employees}
    holiday_set = set(holidays)
    first = date(year, month, 1)
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    last = date.fromordinal(next_month.toordinal() - 1)
    labels = defaultdict(list)

    def dates_for_period(start, end):
        a, b = date.fromisoformat(start), date.fromisoformat(end)
        d = max(first, a)
        while d <= min(last, b):
            if d.weekday() < 5 and d not in holiday_set:
                yield d
            d = date.fromordinal(d.toordinal() + 1)

    def add_single(day, kind, text):
        d = date.fromisoformat(day)
        if first <= d <= last and d.weekday() < 5 and d not in holiday_set:
            labels[d].append({'kind': kind, 'text': text})

    for event in absences:
        if int(event['employee_id']) != person_id:
            continue
        for d in dates_for_period(event['start_date'], event['end_date']):
            labels[d].append({'kind': 'absence', 'text': str(event['kind'])})

    for event in substitutions:
        day = event['day']
        actual_id = int(event['employee_id'])
        other_id = int(event['replaced_id']) if event.get('replaced_id') is not None else None
        hours = float(event['hours'])
        g = event['group']
        purpose = event.get('purpose', 'Pavadavimas')
        category = 'Skolos dengimas' if purpose == 'Ankstesnės skolos dengimas' else 'Pavadavimas'
        if actual_id == person_id:
            other = f' už {names.get(other_id, "kolegę")}' if other_id is not None else ''
            move = ' (perkelta iš kitos grupės)' if event.get('mode') == 'transfer' else ''
            add_single(day, 'cover', f'{category}: +{hours:g} val. {g}{other}{move}')
        if other_id == person_id:
            add_single(day, 'covered', f'Pavadavo {names.get(actual_id, "kolegė")}: {hours:g} val. {g}')

    for event in corrections:
        if int(event['employee_id']) == person_id:
            delta = float(event['delta_hours'])
            note = str(event.get('note') or '').strip()
            title = ('Papildomos valandos' if delta > 0 else 'Valandų korekcija')
            text = f'{title}: {delta:+g} val. {event["group"]}'
            add_single(event['day'], 'change', text + (f' · {note}' if note else ''))

    for event in temporary_increases:
        if int(event['employee_id']) != person_id:
            continue
        baseline = sum(float(allocations.get((person_id, g), 0)) for g in ('Žiogeliai', 'Žirniukai'))
        total_pct = baseline + float(event['additional_pct'])
        for d in dates_for_period(event['start_date'], event['end_date']):
            labels[d].append({'kind': 'temporary',
                              'text': f'Atostogų etatas: {total_pct:g} % · {event["group"]}'})

    # Bendrų pastabų nepriskiriame atsitiktinai kiekvienai darbuotojai.
    general_notes = []
    for entry in notes:
        d = date.fromisoformat(entry['day'])
        if first <= d <= last:
            general_notes.append({'day': d, 'note': entry['note']})
    return dict(labels), general_notes


def group_month_entries(year, month, group, daily, employees, absences=(),
                        substitutions=(), corrections=(), temporary_increases=(),
                        holiday_names=None):
    """Vienos grupės mėnesio Pr–Pn kalendorius su trimis darbuotojomis.

    Grąžinami atskiri kiekvienos dienos įrašai HTML kalendoriui ir Excel eksportui.
    Valandos gaunamos tik iš calculate_month: įvykiai nepridedami antrą kartą.
    """
    from calendar import monthrange
    from collections import defaultdict

    names = {int(e["id"]): str(e["name"]) for e in employees}
    holiday_names = holiday_names or {}
    rows_by_day = defaultdict(dict)
    for r in daily:
        if r["group"] == group and r["date"].year == year and r["date"].month == month:
            rows_by_day[r["date"]][int(r["employee_id"])] = r

    result = []
    for n in range(1, monthrange(year, month)[1] + 1):
        d = date(year, month, n)
        if d.weekday() > 4:
            continue
        holiday = holiday_names.get(d, "")
        per_person = []
        annotations = []
        for eid, name in names.items():
            r = rows_by_day[d].get(eid)
            if r is None:
                continue
            actual = float(r.get("actual", 0))
            planned = float(r.get("planned", 0))
            absence = str(r.get("absence") or "")
            covered = str(r.get("replaced_by") or "")
            replaces = str(r.get("replaces") or "")
            # Atostogos grupėje aktualios, kai pagal nuolatinį grafiką
            # šią dieną turėjo būti grupės pamaina.
            show = actual > 0.001 or planned > 0.001 or bool(covered)
            if show and not holiday:
                per_person.append({
                    "employee_id": eid, "name": name,
                    "planned": planned, "hours": round(actual, 2),
                    "absence": absence if planned > 0 else "",
                    "replaces": replaces, "replaced_by": covered,
                })
        if not holiday:
            for ev in substitutions:
                if ev["day"] != d.isoformat() or ev["group"] != group:
                    continue
                performer = names.get(int(ev["employee_id"]), "?")
                replacement = (names.get(int(ev["replaced_id"]), "?")
                               if ev.get("replaced_id") is not None else "—")
                purpose = ("Skolos dengimas" if ev.get("purpose") == "Ankstesnės skolos dengimas"
                           else "Pavadavimas")
                annotations.append(f"{purpose}: {performer} už {replacement}, {float(ev['hours']):g} val.")
            for ev in corrections:
                if ev["day"] == d.isoformat() and ev["group"] == group:
                    annotations.append(f"Pakeitimas: {names.get(int(ev['employee_id']), '?')} "
                                       f"{float(ev['delta_hours']):+g} val. "
                                       f"{str(ev.get('note') or '').strip()}".strip())
            for ev in temporary_increases:
                if ev["group"] == group and ev["start_date"] <= d.isoformat() <= ev["end_date"]:
                    annotations.append(f"Atostogų etatas: {names.get(int(ev['employee_id']), '?')} "
                                       f"+{float(ev['additional_pct']):g} proc. p.")
        result.append({
            "date": d, "holiday": holiday, "staff": per_person,
            "total_hours": round(sum(r["hours"] for r in per_person), 2),
            "annotations": annotations,
        })
    return result
