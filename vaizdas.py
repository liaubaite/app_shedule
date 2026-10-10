"""Tik atvaizdavimas: HTML demonstracijos kortelės Streamlit programai."""
from html import escape


def val(value, signed=False):
    number = float(value)
    return (f"{number:+.1f}" if signed else f"{number:.1f}").replace(".", ",")


def color(balance):
    return 'dg-plus' if balance > 0.005 else ('dg-minus' if balance < -0.005 else 'dg-zero')


def report_cards(selected_rows, allocations, selected_id):
    blocks = []
    for item in selected_rows:
        group = item['Grupė']
        klass = ' dg-zir' if group == 'Žirniukai' else ''
        planned = item['Planuota (val.)']
        actual = item['Dirbta (val.)']
        balance = item['Balansas (val.)']
        pct = allocations.get((selected_id, group), 0)
        blocks.append(f'''<div class="dg-group-card{klass}">
        <div class="dg-card-heading"><span>{escape(group)}</span><span class="dg-chip">{val(pct)} % etatas</span></div>
        <div class="dg-kpi-row"><div class="dg-kpi"><div class="dg-kpi-label">Mėnesio planas</div><div class="dg-kpi-value">{val(planned)} <span class="dg-unit">val.</span></div></div>
        <div class="dg-kpi"><div class="dg-kpi-label">Faktiškai dirbta</div><div class="dg-kpi-value">{val(actual)} <span class="dg-unit">val.</span></div></div>
        <div class="dg-kpi"><div class="dg-kpi-label">Balansas</div><div class="dg-kpi-value {color(balance)}">{val(balance, True)} <span class="dg-unit">val.</span></div></div></div>
        </div>''')
    return '<div class="dg-group-grid">' + ''.join(blocks) + '</div>'


def debt_panel(relations, year, month_label):
    lines = []
    for r in relations:
        z = float(r['Žiogeliai: Likutis'])
        zr = float(r['Žirniukai: Likutis'])
        lines.append(f'''<tr><td><b>{escape(str(r['Kolega']))}</b></td>
          <td><span class="dg-sign {color(z)}">{val(z, True)}</span><div class="dg-softline">val.</div></td>
          <td><span class="dg-sign {color(zr)}">{val(zr, True)}</span><div class="dg-softline">val.</div></td></tr>''')
    if not lines:
        lines.append('<tr><td colspan="3">Šį mėnesį palyginimų nėra.</td></tr>')
    return f'''<div class="dg-panel"><div class="dg-panel-header"><div><div class="dg-panel-title">Tarpusavio valandų balansas</div>
      <div class="dg-description">Vienos pasirinktos darbuotojos sukauptas likutis su kitomis dviem, atskirai pagal grupes.</div></div>
      <span class="dg-chip-last">{year} m. {escape(month_label)}</span></div>
      <table class="dg-table"><thead><tr><th>Su kuo lyginama</th><th>Žiogeliai (val.)</th><th>Žirniukai (val.)</th></tr></thead>
      <tbody>{''.join(lines)}</tbody></table>
      <div class="dg-help"><strong>Ženklų reikšmė:</strong> <span class="dg-plus">+ val.</span> – kolegė skolinga pasirinktai darbuotojai;
      <span class="dg-minus">− val.</span> – pasirinkta darbuotoja skolinga kolegei. Grupės tarpusavyje neužskaitomos.</div></div>'''


def plan_panel(rows):
    cells = []
    for r in rows:
        cells.append(f'''<tr><td><b>{escape(str(r['Grupė']))}</b></td>
          <td>{val(r['Planuota (val.)'])} val.</td><td>{val(r['Dirbta (val.)'])} val.</td>
          <td>{val(r['Pateisinti neatvykimai (val.)'])} val.</td>
          <td class="dg-sign {color(r['Balansas (val.)'])}">{val(r['Balansas (val.)'],True)} val.</td></tr>''')
    return '''<div class="dg-panel"><div class="dg-panel-title">Valandų plano vykdymas</div>
      <div class="dg-description">100 % = 30 val./sav. Plano valandos apskaičiuotos konkrečiam mėnesiui.</div>
      <table class="dg-table"><thead><tr><th>Grupė</th><th>Numatyta pagal etatą</th><th>Faktiškai dirbta</th>
      <th>Atostogos / liga</th><th>Valandų balansas</th></tr></thead><tbody>''' + ''.join(cells) + '''</tbody></table>
      <div class="dg-softline" style="margin-top:14px">Šventės yra laisvos visoms ir nesukuria skolų. Likučiai pernešami į kitą mėnesį.</div>
      </div>'''


def fixed_staff_cards(employees, allocations, weekday_hours, groups, days, hour_calculator):
    """Trijų asmenų kortelės – kaip pradiniame HTML."""
    cards=[]
    for emp in employees:
        employee_id=emp['id']
        total_pct=sum(float(allocations.get((employee_id, g), 0)) for g in groups)
        rows=[]
        for group in groups:
            pct=float(allocations.get((employee_id, group), 0))
            cell_list=[]
            for wd, _ in enumerate(days):
                h=hour_calculator(employee_id, group, wd, allocations, weekday_hours)
                cell_list.append(f'<td>{val(h).rstrip("0").rstrip(",") + " h" if h else "–"}</td>')
            rows.append(f'<tr><td>{escape(group)}<small class="dg-small">{val(pct)} %</small></td>{"".join(cell_list)}</tr>')
        headers=''.join(f'<th>{escape(str(day))}</th>' for day in days)
        cards.append(f'''<div class="dg-staff-card"><div class="dg-staff-title"><span>{escape(emp['name'])}</span>
            <span class="dg-chip">Iš viso {val(total_pct)} %</span></div>
            <table class="dg-staff-table"><thead><tr><th>Grupė</th>{headers}</tr></thead>
            <tbody>{''.join(rows)}</tbody></table></div>''')
    return '<div class="dg-staff-grid">'+''.join(cards)+'</div>'
