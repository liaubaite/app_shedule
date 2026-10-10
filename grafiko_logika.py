"""Darbo grafikų skaičiuoklės nepriklausoma, testuojama skaičiavimo logika.

30 val. = 100 % (savaitinis etatas). Abiejose grupėse turi būti po 200 %.
Valandos = faktiškai dirbtas laikas; neatvykimas rodomas atskirai.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from itertools import combinations

WEEK_HOURS = 30.0
GROUPS = ("Žiogeliai", "Žirniukai")
TARGET_PCT = {"Žiogeliai": 200.0, "Žirniukai": 200.0}
DAYS = ("Pr", "An", "Tr", "Kt", "Pn")
MONTH_NAMES = ("Sausis", "Vasaris", "Kovas", "Balandis", "Gegužė", "Birželis",
               "Liepa", "Rugpjūtis", "Rugsėjis", "Spalis", "Lapkritis", "Gruodis")


def month_dates(year: int, month: int) -> list[date]:
    return [date(year, month, day) for day in range(1, monthrange(year, month)[1] + 1)
            if date(year, month, day).weekday() < 5]


def _easter(year: int) -> date:
    """Grigališkojo kalendoriaus Velykų data (Meeus/Jones/Butcher)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _first_sunday(year: int, month: int) -> date:
    d = date(year, month, 1)
    return d + timedelta(days=(6 - d.weekday()) % 7)


def holiday_names(year: int) -> dict[date, str]:
    """LT nedarbo šventės be priklausomybės nuo papildomo kalendoriaus paketo.

    Nėra teisinės apskaitos pakaitalas; normų/sutrumpintų prieššventinių dienų neskaičiuoja.
    """
    easter = _easter(year)
    result = {
        date(year, 1, 1): "Naujieji metai",
        date(year, 2, 16): "Lietuvos valstybės atkūrimo diena",
        date(year, 3, 11): "Nepriklausomybės atkūrimo diena",
        easter: "Velykos",
        easter + timedelta(days=1): "Antroji Velykų diena",
        date(year, 5, 1): "Tarptautinė darbo diena",
        _first_sunday(year, 5): "Motinos diena",
        _first_sunday(year, 6): "Tėvo diena",
        date(year, 6, 24): "Joninės",
        date(year, 7, 6): "Valstybės diena",
        date(year, 8, 15): "Žolinė",
        date(year, 11, 1): "Visų Šventųjų diena",
        date(year, 11, 2): "Vėlinės",
        date(year, 12, 24): "Kūčios",
        date(year, 12, 25): "Kalėdos",
        date(year, 12, 26): "Antroji Kalėdų diena",
    }
    return result


def get_holidays(year: int) -> set[date]:
    return set(holiday_names(year))


def _scheduled_hours(emp_id: int, group: str, wd: int, alloc: dict, schedule: dict) -> float:
    value = schedule.get((emp_id, group, wd), 0.0)
    # Compatibility with boolean weekday flags in an earlier prototype.
    if isinstance(value, bool):
        days = sum(bool(schedule.get((emp_id, group, x), False)) for x in range(5))
        return WEEK_HOURS * float(alloc.get((emp_id, group), 0.0)) / 100 / days if value and days else 0.0
    return max(float(value or 0.0), 0.0)


def calculate_month(year, month, employees, allocations, weekday_hours, absences,
                    substitutions, corrections, use_holidays=True, temporary_increases=()):
    """Apskaičiuoja kalendorines darbo valandas ir skirtumus.

    weekday_hours: {(employee_id, group, weekday_0_to_6): hours_per_day}.
    absences: {id, employee_id, kind, start_date, end_date}.
    substitutions: {id, day, employee_id, replaced_id, group, hours, mode, source_group}.
      mode=extra | transfer; transfer atima valandas iš kitos grupės.
      Jei pavaduojamasis nėra neatvykęs, jo faktiškai dirbtos valandos
      pavadavimo grupėje sumažinamos, kad tas pats darbas nebūtų skaičiuojamas du kartus.
    corrections: {id, day, employee_id, group, delta_hours}.
    """
    name_by_id = {int(e["id"]): e["name"] for e in employees}
    holiday_map = holiday_names(year) if use_holidays else {}
    daily = {}
    warnings = []
    selected_days = month_dates(year, month)

    for d in selected_days:
        holiday = holiday_map.get(d, "")
        for emp_id in name_by_id:
            for group in GROUPS:
                planned = (0.0 if holiday else
                           _scheduled_hours(emp_id, group, d.weekday(), allocations, weekday_hours))
                daily[(d, emp_id, group)] = {
                    "date": d, "employee_id": emp_id, "employee": name_by_id[emp_id],
                    "group": group, "planned": planned, "actual": planned,
                    "absence": "", "absent_hours": 0.0, "extra": 0.0,
                    "transferred": 0.0, "holiday": holiday, "replaced_by": "", "replaces": "",
                    "temp_increase_pct": 0.0, "temp_increase_norm": 0.0,
                }

    # Laikinas atostogų pavadavimui skirtas etato padidinimas.
    # Jis nekeičia pastovaus grafiko ir NESUKURIA asmeninės skolos.
    # Padidinto etato normos trūkumas nėra minusuojamas. Tik papildomai
    # faktiškai įvestos valandos gali panaudoti šio laikotarpio išimtį.
    for ev in temporary_increases or ():
        try:
            aid = int(ev["employee_id"])
            group = ev["group"]
            start, end = date.fromisoformat(ev["start_date"]), date.fromisoformat(ev["end_date"])
            pct = float(ev["additional_pct"])
        except (KeyError, ValueError, TypeError):
            warnings.append("Neteisingi laikino etato padidinimo duomenys – neįskaityta.")
            continue
        if aid not in name_by_id or group not in GROUPS or end < start or pct <= 0:
            warnings.append("Neteisingas laikino etato padidinimo darbuotojas, grupė ar laikotarpis.")
            continue
        original_pct = sum(float(allocations.get((aid, g), 0)) for g in GROUPS)
        for d in selected_days:
            if not start <= d <= end or d in holiday_map:
                continue
            already = sum(daily[(d, aid, g)]["temp_increase_pct"] for g in GROUPS)
            available_pct = 150.0 - original_pct - already
            allowed_pct = min(pct, max(0., available_pct))
            if allowed_pct < pct - 1e-7:
                warnings.append(f"{d}: {name_by_id[aid]} laikinas bendras krūvis viršytų 150 %; "
                                "viršijanti dalis neįskaityta.")
            daily[(d, aid, group)]["temp_increase_pct"] += allowed_pct
            daily[(d, aid, group)]["temp_increase_norm"] += WEEK_HOURS / 5.0 * allowed_pct / 100.0

    occupied = {}
    for a in sorted(absences, key=lambda x: int(x.get("id", 0))):
        aid = int(a["employee_id"])
        if aid not in name_by_id:
            warnings.append("Neatvykimas priskirtas nežinomam darbuotojui.")
            continue
        start = date.fromisoformat(a["start_date"])
        end = date.fromisoformat(a["end_date"])
        for d in selected_days:
            if not (start <= d <= end) or d in holiday_map:
                continue  # Šventė nėra atostogų / ligos valanda, net jei laikotarpis ją apima.
            if (d, aid) in occupied:
                warnings.append(f"{d}: dubliuojasi {name_by_id[aid]} neatvykimai.")
                continue
            occupied[(d, aid)] = a["kind"]
            for group in GROUPS:
                row = daily[(d, aid, group)]
                row["absent_hours"] = row["planned"]
                row["actual"] = 0.0
                row["absence"] = a["kind"]

    for s in sorted(substitutions, key=lambda x: int(x.get("id", 0))):
        d = date.fromisoformat(s["day"])
        aid = int(s["employee_id"])
        group = s["group"]
        if (d, aid, group) not in daily:
            continue  # Įvykis kitam mėnesiui.
        if d in holiday_map:
            warnings.append(f"{d}: šventinė diena ({holiday_map[d]}); pavadavimas neįskaitytas.")
            continue
        if (d, aid) in occupied:
            warnings.append(f"{d}: {name_by_id[aid]} pavaduoja neatvykimo dieną – neįskaityta.")
            continue
        replaced_id = int(s["replaced_id"]) if s.get("replaced_id") is not None else None
        if replaced_id == aid:
            warnings.append(f"{d}: negalima pavaduoti savęs – neįskaityta.")
            continue
        if replaced_id is not None and replaced_id not in name_by_id:
            warnings.append(f"{d}: nenurodytas galiojantis pavaduojamas darbuotojas – neįskaityta.")
            continue
        hours = float(s["hours"])
        if hours <= 0:
            warnings.append(f"{d}: pavadavimo valandos turi būti teigiamos.")
            continue
        if s["mode"] == "transfer":
            source = s["source_group"]
            if source not in GROUPS or source == group:
                warnings.append(f"{d}: netinkama perkėlimo grupė.")
                continue
            from_row = daily[(d, aid, source)]
            if from_row["actual"] + 1e-7 < hours:
                warnings.append(
                    f"{d}: {name_by_id[aid]} nepakanka valandų perkelti iš „{source}“ "
                    f"({hours:g} val. prašoma, {from_row['actual']:.2f} val. galima)."
                )
                continue
            from_row["actual"] -= hours
            from_row["transferred"] -= hours
            daily[(d, aid, group)]["transferred"] += hours
        elif s["mode"] == "extra":
            daily[(d, aid, group)]["extra"] += hours
        else:
            warnings.append(f"{d}: nežinomas pavadavimo tipas.")
            continue
        target_row = daily[(d, aid, group)]
        target_row["actual"] += hours
        if replaced_id is not None:
            target_row["replaces"] += (", " if target_row["replaces"] else "") + name_by_id[replaced_id]
            original_row = daily[(d, replaced_id, group)]
            if (d, replaced_id) not in occupied:
                deducted = min(hours, max(0.0, original_row["actual"]))
                original_row["actual"] -= deducted
                if deducted:
                    original_row["replaced_by"] += (", " if original_row["replaced_by"] else "") + name_by_id[aid]
                if deducted + 1e-7 < hours:
                    warnings.append(f"{d}: {name_by_id[replaced_id]} grupėje „{group}“ turėjo tik "
                                    f"{deducted:g} val. iš {hours:g} val. pavadavimo; "
                                    "likusi dalis laikoma papildomu grupės darbu.")

    for c in sorted(corrections, key=lambda x: int(x.get("id", 0))):
        d = date.fromisoformat(c["day"])
        aid = int(c["employee_id"])
        group = c["group"]
        if (d, aid, group) not in daily:
            continue
        if d in holiday_map:
            warnings.append(f"{d}: šventinė diena ({holiday_map[d]}); valandų korekcija neįskaityta.")
            continue
        if (d, aid) in occupied:
            warnings.append(f"{d}: {name_by_id[aid]} korekcija sutampa su neatvykimu – neįskaityta.")
            continue
        row = daily[(d, aid, group)]
        delta = float(c["delta_hours"])
        if row["actual"] + delta < -1e-7:
            warnings.append(f"{d}: {name_by_id[aid]} „{group}“ valandos taptų neigiamos – neįskaityta.")
            continue
        row["actual"] += delta
        row["extra"] += delta

    result = list(daily.values())
    # ŠVENTINIŲ DIENŲ NEUTRALUMAS SKOLOMS:
    # 1) sutartinis krūvio planas skaičiuojamas visoms mėnesio Pr–Pn datoms;
    # 2) iš to plano pašalinamos būtent tos 12 val. (ar kito dydžio) pamainos,
    #    kurios būtų tekusios šventei PAGAL KONKRETAUS žmogaus pastovų grafiką.
    # 3) tą šventę faktinis darbas irgi = 0. Taigi atšaukta pamaina
    #    niekada nesukuria nei valandų skolos, nei tariamo viršvalandžio.
    # Tai valandų tarpusavio atsiskaitymo taisyklė, NE oficiali LT DU norma.
    norm_workdays = sum(d.weekday() < 5 and d not in holiday_map for d in selected_days)
    month_fulltime_norm = norm_workdays * WEEK_HOURS / 5.0
    nominal_norm_including_holidays = len(selected_days) * WEEK_HOURS / 5.0
    weekday_holidays = [d for d in selected_days if d in holiday_map]
    people = []
    for employee in employees:
        aid = int(employee["id"])
        selected = [r for r in result if r["employee_id"] == aid]
        rec = {"Darbuotojas": name_by_id[aid]}
        for group in GROUPS:
            group_rows = [r for r in selected if r["group"] == group]
            fixed_holiday_hours = sum(_scheduled_hours(aid, group, d.weekday(),
                                                        allocations, weekday_hours)
                                      for d in weekday_holidays)
            # Atėmus šventę iš 12 val. grafiko ir tiek pat iš individualaus
            # plano, balansas lieka lygiai toks pat, lyg šventės nebūtų.
            rec[f"{group}: švenčių pamainos"] = round(fixed_holiday_hours, 2)
            rec[f"{group}: standartinė norma"] = round(month_fulltime_norm *
                                                  float(allocations.get((aid, group), 0.0)) / 100, 2)
            rec[f"{group}: planas"] = round(nominal_norm_including_holidays *
                                               float(allocations.get((aid, group), 0.0)) / 100
                                               - fixed_holiday_hours, 2)
            rec[f"{group}: pagal grafiką"] = round(sum(r["planned"] for r in group_rows), 2)
            rec[f"{group}: dirbta"] = round(sum(r["actual"] for r in group_rows), 2)
            rec[f"{group}: pateisintas neatvykimas"] = round(sum(
                r["absent_hours"] for r in group_rows if r["absence"] in ("Atostogos", "Liga")), 2)
            rec[f"{group}: laikino padidinimo norma"] = round(
                sum(r["temp_increase_norm"] for r in group_rows), 2)
            # Kiek realiai papildomai įdirbta tuo laikotarpiu – vertiname tik
            # įvestus pap. darbus; vien pakeltas procentas balanso nekeičia.
            worked_extra_during_increase = sum(max(0., r["actual"] - r["planned"])
                                               for r in group_rows if r["temp_increase_norm"] > 0)
            raw_balance = (rec[f"{group}: dirbta"] - rec[f"{group}: planas"] +
                           rec[f"{group}: pateisintas neatvykimas"])
            excluded = min(max(0., raw_balance),
                           rec[f"{group}: laikino padidinimo norma"],
                           worked_extra_during_increase)
            rec[f"{group}: neįtraukiama į balansą"] = round(excluded, 2)
            rec[f"{group}: balansas"] = round(raw_balance - excluded, 2)
        rec["Atostogos (val.)"] = round(sum(r["absent_hours"] for r in selected if r["absence"] == "Atostogos"), 2)
        rec["Liga (val.)"] = round(sum(r["absent_hours"] for r in selected if r["absence"] == "Liga"), 2)
        rec["Papildomas darbas (val.)"] = round(sum(r["extra"] for r in selected if r["extra"] > 0), 2)
        rec["Iš viso planas"] = round(sum(rec[f"{group}: planas"] for group in GROUPS), 2)
        rec["Iš viso dirbta"] = round(sum(r["actual"] for r in selected), 2)
        rec["Skirtumas nuo plano"] = round(rec["Iš viso dirbta"] - rec["Iš viso planas"], 2)
        rec["Balansas po neatvykimų"] = round(sum(rec[f"{group}: balansas"] for group in GROUPS), 2)
        rec["Laikinas padidinimas: neįskaityta (val.)"] = round(
            sum(rec[f"{group}: neįtraukiama į balansą"] for group in GROUPS), 2)
        people.append(rec)

    groups = []
    working_days = [d for d in selected_days if d.weekday() < 5 and d not in holiday_map]
    # Informacinis etalonas: du 30 val. etatai, paskirstyti per 5 darbo dienas.
    reference_hours = len(working_days) * 2 * WEEK_HOURS / 5
    for group in GROUPS:
        selected = [r for r in result if r["group"] == group]
        planned = sum(float(p[f"{group}: planas"]) for p in people)
        actual = sum(r["actual"] for r in selected)
        groups.append({"Grupė": group, "2 etatų norma (val.)": round(reference_hours, 2),
                       "Planas (val.)": round(planned, 2), "Dirbta (val.)": round(actual, 2),
                       "Padengimas (%)": round(actual / reference_hours * 100, 1) if reference_hours else 0,
                       "Trūkumas / perteklius (val.)": round(actual - reference_hours, 2)})

    comparisons = []
    for a, b in combinations(people, 2):
        for group in (*GROUPS, "Abi grupės"):
            if group == "Abi grupės":
                ac, bc = a["Iš viso dirbta"], b["Iš viso dirbta"]
                ap, bp = a["Iš viso planas"], b["Iš viso planas"]
            else:
                ac, bc = a[f"{group}: dirbta"], b[f"{group}: dirbta"]
                ap, bp = a[f"{group}: planas"], b[f"{group}: planas"]
            comparisons.append({
                "Pirmas": a["Darbuotojas"], "Antras": b["Darbuotojas"],
                "Grupė": group, "Dirbtų valandų skirtumas": round(ac - bc, 2),
                "Skirtumas nuo individualių planų": round((ac - ap) - (bc - bp), 2)
            })

    return {"daily": result, "people": people, "groups": groups,
            "comparisons": comparisons, "warnings": list(dict.fromkeys(warnings)),
            "holidays": set(holiday_map), "holiday_names": holiday_map}



def person_balance(person: dict, group: str) -> float:
    """Darbo valandų balansas, neįtraukiant pateisintų neatvykimų į skolas."""
    if group == "Abi grupės":
        return round(float(person["Balansas po neatvykimų"]), 2)
    return round(float(person[f"{group}: balansas"]), 2)


def reconcile_hour_balances(people: list[dict], group: str = "Abi grupės") -> dict:
    """Susieja priešingus asmeninius valandų balansus, kai tai vienareikšmiška.

    Negalima nustatyti, kuris asmuo kam skolingas vien iš mėnesio sumų,
    kai dalį valandų galėtų kompensuoti keli kolegos. Tokiu atveju porų
    nesukuriame ir grąžiname neaiškią sumą patikslinimui.

    Atsiradusi pora yra BALANSO interpretacija, ne automatiškai
    patvirtintas konkretus pavadavimas.
    """
    balances = {p["Darbuotojas"]: person_balance(p, group) for p in people}
    creditors = [(name, hours) for name, hours in balances.items() if hours > 0.005]
    debtors = [(name, -hours) for name, hours in balances.items() if hours < -0.005]
    credits = round(sum(h for _, h in creditors), 2)
    deficits = round(sum(h for _, h in debtors), 2)
    matchable = round(min(credits, deficits), 2)
    assignments = []
    ambiguous = 0.0

    if len(creditors) == 1 and len(debtors) == 1:
        assignments.append({"Skolingas": debtors[0][0], "Kam skolingas": creditors[0][0],
                            "Valandos": matchable})
    elif len(creditors) == 1 and credits + 0.005 >= deficits:
        for debtor, hours in debtors:
            assignments.append({"Skolingas": debtor, "Kam skolingas": creditors[0][0],
                                "Valandos": hours})
    elif len(debtors) == 1 and deficits + 0.005 >= credits:
        for creditor, hours in creditors:
            assignments.append({"Skolingas": debtors[0][0], "Kam skolingas": creditor,
                                "Valandos": hours})
    elif matchable > 0.005:
        ambiguous = matchable
    assignments = [a for a in assignments if a["Valandos"] > 0.005]
    assigned = round(sum(a["Valandos"] for a in assignments), 2)
    return {"balances": balances, "assignments": assignments, "unassigned": round(max(0, matchable-assigned), 2),
            "ambiguous": ambiguous > 0.005, "unmatched_extra": round(credits-matchable, 2),
            "unmatched_short": round(deficits-matchable, 2), "group": group}


def selected_employee_report(people: list[dict], selected_name: str):
    """Vieno žmogaus mėnesio plano balansas ir porinė valandų kompensacija.

    Grupių valandos niekada netarpusavyje neužskaitomos. Kiekvienam kolegai
    pateikiamas atskiras SKAITINIS stulpelis kiekvienai grupei:
      teigiamas = kolega skolingas pasirinktam darbuotojui;
      neigiamas = pasirinktas darbuotojas skolingas kolegai;
      0 = nėra priskirtos tarpusavio skolos;
      None = pagal vien bendrus balansus neįmanoma nustatyti gavėjo/mokėtojo.

    Tokia kompensacija nustatoma iš *nuokrypių nuo asmeninio plano*, o ne iš
    absoliutaus darbuotojų išdirbtų valandų skirtumo.
    """
    by_name = {p["Darbuotojas"]: p for p in people}
    if selected_name not in by_name:
        raise ValueError("Pasirinktas darbuotojas nerastas.")
    selected = by_name[selected_name]
    personal = []
    for group in GROUPS:
        plan = float(selected[f"{group}: planas"])
        actual = float(selected[f"{group}: dirbta"])
        leave = float(selected[f"{group}: pateisintas neatvykimas"])
        personal.append({"Grupė": group, "Planuota (val.)": round(plan, 2),
                         "Dirbta (val.)": round(actual, 2),
                         "Pateisinti neatvykimai (val.)": round(leave, 2),
                         "Laikino padidinimo norma (val.)": round(float(selected.get(f"{group}: laikino padidinimo norma", 0)), 2),
                         "Neįtraukta į skolą (val.)": round(float(selected.get(f"{group}: neįtraukiama į balansą", 0)), 2),
                         "Balansas (val.)": person_balance(selected, group)})

    relations = [{"Kolega": name} for name in by_name if name != selected_name]
    for group in GROUPS:
        settlement = reconcile_hour_balances(people, group)
        for relation in relations:
            colleague = relation["Kolega"]
            pair = next((x for x in settlement["assignments"]
                         if {x["Skolingas"], x["Kam skolingas"]} ==
                         {selected_name, colleague}), None)
            if pair:
                signed = pair["Valandos"] * (1 if pair["Kam skolingas"] == selected_name else -1)
            elif settlement["ambiguous"] and (
                person_balance(selected, group) * person_balance(by_name[colleague], group) < 0
            ):
                signed = None  # Nepriskiriame skolos be papildomos informacijos.
            else:
                signed = 0.0
            relation[f"{group} (val.)"] = round(signed, 2) if signed is not None else None
    return selected, personal, relations


def suggest_hours_from_text(text: str, employees: list[dict]):
    """Konservatyvus valandų korekcijos atpažinimas iš lietuviško teksto.

    Nieko nekeičia automatiškai. Atpažįsta tik vieną žmogų, grupę ir aiškią
    valandų DELTĄ (+N/-N arba N val. daugiau / mažiau).
    """
    import re
    from unicodedata import normalize

    def fold(value: str) -> str:
        return ''.join(c for c in normalize('NFD', value.casefold()) if ord(c) < 0x300 or not 0x300 <= ord(c) <= 0x36f)

    # Pastabose galima vartoti lietuviškus simbolius arba rašyti be jų.
    raw = fold(text)
    matching = [p for p in employees if fold(p['name']) in raw]
    if len(matching) != 1:
        return None
    matches_ziog = 'ziogel' in raw
    matches_zirn = 'zirniuk' in raw or 'zirniu' in raw
    if matches_ziog == matches_zirn:
        return None
    group = 'Žiogeliai' if matches_ziog else 'Žirniukai'
    explicit = re.search(r'(?<!\w)([+-])\s*(\d+(?:[,.]\d+)?)\s*(?:val\.?|valand)', raw)
    if explicit:
        delta = float(explicit.group(2).replace(',', '.')) * (1 if explicit.group(1) == '+' else -1)
    else:
        number = re.search(r'(?<!\w)(\d+(?:[,.]\d+)?)\s*(?:val\.?|valand)', raw)
        if not number:
            return None
        plus = any(x in raw for x in ('ilgiau', 'daugiau', 'papildomai'))
        minus = any(x in raw for x in ('trumpiau', 'maziau'))
        if plus == minus:
            return None
        delta = float(number.group(1).replace(',', '.')) * (1 if plus else -1)
    if abs(delta) < 0.001 or abs(delta) > 24:
        return None
    return {'employee_id': int(matching[0]['id']), 'group': group, 'delta_hours': delta}


def _month_sequence(start_year: int, start_month: int, end_year: int, end_month: int):
    """Metai/mėnuo imtinai, įskaitant perėjimą į kitus kalendorinius metus."""
    yy, mm = start_year, start_month
    while (yy, mm) <= (end_year, end_month):
        yield yy, mm
        mm += 1
        if mm == 13:
            yy, mm = yy + 1, 1


def cumulative_group_debts(year: int, month: int, employees: list[dict], allocations: dict,
                           weekday_hours: dict, absences: list, substitutions: list,
                           corrections: list, start_year: int | None = None,
                           start_month: int = 1, temporary_increases: list | tuple = ()) -> dict:
    """Perkelia neapmokėtus porinius valandų likučius iš mėnesio į mėnesį.

    Tiksliai įvardyti pavadavimai priskiriami porai tik tuomet, kai pavaduojamo
    žmogaus faktiškai dirbtos valandos buvo SUMAŽINTOS. Atostogų ar ligos atveju
    darbuotojui skola nesukuriama. Kiti nukrypimai priskiriami poroms tik tada,
    kai paskirstymas vienareikšmis; kitu atveju lieka nepriskirtos valandos.

    Teigiama pair balance (a,b) reikšmė: b skolingas a (a – mažesnis ID).
    Kiekviena grupė apskaitoma atskirai, net jeigu bendras žmogaus balansas 0.
    """
    if start_year is None:
        starts = [str(ev[k])[:7] for event_list, k in
                  ((absences, 'start_date'), (substitutions, 'day'), (corrections, 'day'))
                  for ev in event_list if ev.get(k)]
        starts = [s for s in starts if len(s) == 7 and s[4] == '-']
        if starts:
            first = min(starts)
            start_year, start_month = int(first[:4]), int(first[5:7])
        else:
            start_year, start_month = year, month
    if (start_year, start_month) > (year, month):
        start_year, start_month = year, month
    names = {int(e['id']): e['name'] for e in employees}
    ids = sorted(names)
    pairs = {(group, a, b): 0.0 for group in GROUPS for a, b in combinations(ids, 2)}
    outstanding = {(group, i): 0.0 for group in GROUPS for i in ids}
    changes = []
    opening = None
    opening_unmatched = None
    selected_calc = None
    tolerance = 0.005

    for yy, mm in _month_sequence(start_year, start_month, year, month):
        if (yy, mm) == (year, month):
            opening = dict(pairs)
            opening_unmatched = dict(outstanding)
        calc = calculate_month(yy, mm, employees, allocations, weekday_hours,
                               absences, substitutions, corrections,
                               temporary_increases=temporary_increases)
        if (yy, mm) == (year, month):
            selected_calc = calc
        current = {}
        for group in GROUPS:
            monthly = {int(e['id']): person_balance(
                next(p for p in calc['people'] if p['Darbuotojas'] == e['name']), group)
                for e in employees}
            # Suderinamos eilės tvarka, kad keli pavadavimai tą pačią dieną
            # neskirtų didesnės skolos nei realiai padengtas kolegos darbas.
            relevant = sorted((x for x in substitutions if x.get('group') == group
                               and str(x['day'])[:7] == f'{yy}-{mm:02d}'),
                              key=lambda x: int(x.get('id', 0)))
            deducted_so_far = {}
            for s in relevant:
                creditor = int(s['employee_id'])
                debtor = int(s['replaced_id']) if s.get('replaced_id') is not None else None
                if not debtor or debtor == creditor or debtor not in names or creditor not in names:
                    continue
                day = date.fromisoformat(s['day'])
                if day.weekday() > 4:
                    continue
                if any(a['employee_id'] == creditor and
                       a['start_date'] <= s['day'] <= a['end_date'] for a in absences):
                    continue
                if any(a['employee_id'] == debtor and
                       a['start_date'] <= s['day'] <= a['end_date'] for a in absences):
                    continue  # Pateisintas neatvykimas – ne asmeninė skola.
                # Tik atimta iš kolegos planuotų/faktiškų valandų dalis.
                original = _scheduled_hours(debtor, group, day.weekday(), allocations, weekday_hours)
                if day in calc['holidays']:
                    original = 0
                key_daily = (day, debtor, group)
                available = max(0.0, original - deducted_so_far.get(key_daily, 0.0))
                hours = min(max(0.0, float(s.get('hours', 0))), available)
                if hours <= tolerance:
                    continue
                deducted_so_far[key_daily] = deducted_so_far.get(key_daily, 0.0) + hours
                # Valandos poroje jau priskirtos; iš bendro nukrypimo jas išimame.
                monthly[creditor] = round(monthly[creditor] - hours, 4)
                monthly[debtor] = round(monthly[debtor] + hours, 4)
                a, b = sorted((creditor, debtor))
                signed = hours if creditor == a else -hours
                pairs[(group, a, b)] = round(pairs[(group, a, b)] + signed, 4)
                changes.append({'Metai': yy, 'Mėnuo': mm, 'Grupė': group,
                                'Dirbo': names[creditor], 'Už ką': names[debtor],
                                'Valandos': round(hours, 2),
                                'Pobūdis': s.get('purpose') or 'Pavadavimas'})
            for i in ids:
                outstanding[(group, i)] = round(outstanding[(group, i)] + monthly[i], 4)
            # Papildomos, neįvardytos valandos tarpusavyje užskaitomos TIK tada,
            # kai vienareikšmė kreditoriaus ir skolininko pora.
            positive = [(i, v) for i in ids if (v := outstanding[(group, i)]) > tolerance]
            negative = [(i, -v) for i in ids if (v := outstanding[(group, i)]) < -tolerance]
            allocations_found = []
            pos_total, neg_total = sum(v for _, v in positive), sum(v for _, v in negative)
            if len(positive) == 1 and len(negative) == 1:
                allocations_found = [(negative[0][0], positive[0][0], min(negative[0][1], positive[0][1]))]
            elif len(positive) == 1 and pos_total + tolerance >= neg_total:
                allocations_found = [(debtor, positive[0][0], hrs) for debtor, hrs in negative]
            elif len(negative) == 1 and neg_total + tolerance >= pos_total:
                allocations_found = [(negative[0][0], creditor, hrs) for creditor, hrs in positive]
            for debtor, creditor, hrs in allocations_found:
                if hrs <= tolerance:
                    continue
                outstanding[(group, debtor)] = round(outstanding[(group, debtor)] + hrs, 4)
                outstanding[(group, creditor)] = round(outstanding[(group, creditor)] - hrs, 4)
                a, b = sorted((creditor, debtor))
                pairs[(group, a, b)] = round(pairs[(group, a, b)] + (hrs if creditor == a else -hrs), 4)
                changes.append({'Metai': yy, 'Mėnuo': mm, 'Grupė': group,
                                'Dirbo': names[creditor], 'Už ką': names[debtor],
                                'Valandos': round(hrs, 2), 'Pobūdis': 'Priskirta pagal balansus'})
        if (yy, mm) == (year, month):
            current = dict(pairs)
    return {
        'opening_pairs': {k: round(v, 2) for k, v in (opening or {}).items()},
        'closing_pairs': {k: round(v, 2) for k, v in pairs.items()},
        'monthly_pairs': {k: round(pairs[k] - (opening or {}).get(k, 0), 2) for k in pairs},
        'opening_unmatched': {k: round(v, 2) for k, v in (opening_unmatched or {}).items()},
        'closing_unmatched': {k: round(v, 2) for k, v in outstanding.items()},
        'monthly_unmatched': {k: round(outstanding[k] - (opening_unmatched or {}).get(k, 0), 2)
                              for k in outstanding},
        'changes': [c for c in changes if (c['Metai'], c['Mėnuo']) == (year, month)],
        'current_calc': selected_calc,
        'begin': (start_year, start_month),
    }


def employee_cumulative_view(carry: dict, selected_id: int, employees: list[dict]) -> list[dict]:
    """Tik pasirinktam darbuotojui: atidarymo, mėnesio ir uždarymo porinės skolos."""
    output = []
    for p in employees:
        eid = int(p['id'])
        if eid == selected_id:
            continue
        item = {'Kolega': p['name']}
        a, b = sorted((eid, selected_id))
        multiplier = 1 if selected_id == a else -1
        for group in GROUPS:
            k = (group, a, b)
            for src, label in (('opening_pairs', 'Ankstesnis likutis'),
                               ('monthly_pairs', 'Mėnesio pokytis'),
                               ('closing_pairs', 'Likutis')):
                item[f'{group}: {label}'] = round(multiplier * carry[src][k], 2)
        output.append(item)
    return output
