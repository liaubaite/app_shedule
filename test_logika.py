"""Paleisti: python -m unittest -v test_logika.py"""
import unittest
from datetime import date
from grafiko_logika import (GROUPS, _scheduled_hours, calculate_month, selected_employee_report,
                          suggest_hours_from_text, cumulative_group_debts, employee_cumulative_view)

EMPLOYEES = [
    {"id": 1, "name": "Darbuotojas A"},
    {"id": 2, "name": "Darbuotojas B"},
    {"id": 3, "name": "Darbuotojas C"},
]
PCT = {
    (1, "Žiogeliai"): 75, (1, "Žirniukai"): 50,
    (2, "Žiogeliai"): 75, (2, "Žirniukai"): 75,
    (3, "Žiogeliai"): 50, (3, "Žirniukai"): 75,
}
DAYS = {(e['id'], group, wd): True for e in EMPLOYEES for group in GROUPS for wd in range(5)}


def calc(month, absences=(), substitutions=(), corrections=()):
    return calculate_month(2026, month, EMPLOYEES, PCT, DAYS, list(absences), list(substitutions), list(corrections))


class TestGrafikas(unittest.TestCase):
    def test_person_weekly_hours(self):
        self.assertAlmostEqual(sum(_scheduled_hours(1, 'Žiogeliai', x, PCT, DAYS) for x in range(7)), 22.5)
        self.assertAlmostEqual(sum(_scheduled_hours(1, 'Žirniukai', x, PCT, DAYS) for x in range(7)), 15)
        self.assertEqual(sum(PCT[(i,'Žiogeliai')] for i in (1,2,3)), 200)
        self.assertEqual(sum(PCT[(i,'Žirniukai')] for i in (1,2,3)), 200)

    def test_october_month_total(self):
        r = calc(10)
        self.assertAlmostEqual(r['people'][0]['Iš viso planas'], 165)
        self.assertAlmostEqual(r['groups'][0]['Planas (val.)'], 264)
        self.assertAlmostEqual(r['groups'][1]['Planas (val.)'], 264)
        self.assertAlmostEqual(r['people'][1]['Iš viso planas'], 198)

    def test_months_change_from_calendar(self):
        a, b = calc(10), calc(11)
        self.assertNotEqual(a['people'][0]['Iš viso planas'], b['people'][0]['Iš viso planas'])
        self.assertGreater(a['people'][0]['Iš viso planas'], b['people'][0]['Iš viso planas'])

    def test_absence_removes_work_not_balance(self):
        event={'id':1,'employee_id':1,'kind':'Atostogos','start_date':'2026-10-12','end_date':'2026-10-13'}
        r=calc(10,[event])
        a=r['people'][0]
        self.assertEqual(a['Atostogos (val.)'], 15)
        self.assertEqual(a['Iš viso planas'],165)
        self.assertEqual(a['Iš viso dirbta'],150)
        self.assertEqual(a['Balansas po neatvykimų'],0)

    def test_substitution_does_not_double_count_replaced_work(self):
        ev={'id':1,'day':'2026-10-12','employee_id':1,'replaced_id':2,
            'group':'Žiogeliai','hours':2.0,'mode':'extra','source_group':None}
        r=calc(10,substitutions=[ev])
        x=[r for r in r['daily'] if r['date']==date(2026,10,12) and r['group']=='Žiogeliai']
        self.assertAlmostEqual(sum(z['actual'] for z in x), sum(z['planned'] for z in x))
        self.assertAlmostEqual(next(z['actual']-z['planned'] for z in x if z['employee_id']==1),2)
        self.assertAlmostEqual(next(z['actual']-z['planned'] for z in x if z['employee_id']==2),-2)

    def test_substitution_during_leave_counts_coverage(self):
        absn={'id':1,'employee_id':2,'kind':'Liga','start_date':'2026-10-12','end_date':'2026-10-12'}
        sub={'id':1,'day':'2026-10-12','employee_id':1,'replaced_id':2,
             'group':'Žiogeliai','hours':4.5,'mode':'extra','source_group':None}
        r=calc(10,[absn],[sub])
        rows=[x for x in r['daily'] if x['date']==date(2026,10,12) and x['group']=='Žiogeliai']
        self.assertAlmostEqual(sum(x['actual'] for x in rows),sum(x['planned'] for x in rows))

    def test_transfer_keeps_person_total(self):
        ev={'id':1,'day':'2026-10-12','employee_id':1,'replaced_id':None,
            'group':'Žirniukai','hours':2.0,'mode':'transfer','source_group':'Žiogeliai'}
        r=calc(10,substitutions=[ev])
        self.assertEqual(r['people'][0]['Iš viso dirbta'], 165.0)
        self.assertAlmostEqual(r['people'][0]['Žirniukai: dirbta'],68.0)
        self.assertAlmostEqual(r['people'][0]['Žiogeliai: dirbta'],97.0)

    def test_manual_hours(self):
        mixed=dict(DAYS)
        for wd, hrs in enumerate([9,0,9,0,9,0,0]):
            mixed[(1,'Žiogeliai',wd)]=float(hrs)
        self.assertEqual(sum(_scheduled_hours(1,'Žiogeliai',wd,PCT,mixed) for wd in range(7)),27)

    def test_selected_person_report_orientation(self):
        result = calc(10)
        person, detail, comparisons = selected_employee_report(result['people'], 'Darbuotojas A')
        self.assertEqual(person['Darbuotojas'], 'Darbuotojas A')
        self.assertEqual(len(detail), 2)
        self.assertEqual(len(comparisons), 2)
        self.assertIn('Žiogeliai (val.)', comparisons[0])
        self.assertEqual(comparisons[0]['Žiogeliai (val.)'], 0)

    def test_carryover_and_repayment_separate_groups(self):
        events = [
            {'id':1,'day':'2026-10-12','employee_id':1,'replaced_id':2,
             'group':'Žiogeliai','hours':2,'mode':'extra'},
            {'id':2,'day':'2026-10-13','employee_id':2,'replaced_id':1,
             'group':'Žirniukai','hours':1,'mode':'extra'},
            {'id':3,'day':'2026-11-09','employee_id':2,'replaced_id':1,
             'group':'Žiogeliai','hours':1,'mode':'extra','purpose':'Ankstesnės skolos dengimas'},
        ]
        octb = cumulative_group_debts(2026,10, EMPLOYEES, PCT, DAYS, [], events, [])
        novb = cumulative_group_debts(2026,11, EMPLOYEES, PCT, DAYS, [], events, [])
        octview = employee_cumulative_view(octb, 1, EMPLOYEES)
        novview = employee_cumulative_view(novb, 1, EMPLOYEES)
        self.assertEqual(octview[0]['Žiogeliai: Likutis'], +2)
        self.assertEqual(octview[0]['Žirniukai: Likutis'], -1)
        self.assertEqual(novview[0]['Žiogeliai: Ankstesnis likutis'], +2)
        self.assertEqual(novview[0]['Žiogeliai: Mėnesio pokytis'], -1)
        self.assertEqual(novview[0]['Žiogeliai: Likutis'], +1)
        self.assertEqual(novview[0]['Žirniukai: Likutis'], -1)

    def test_leave_coverage_does_not_create_debt(self):
        absences = [{'id':1,'employee_id':2,'kind':'Atostogos',
                     'start_date':'2026-10-12','end_date':'2026-10-12'}]
        events = [{'id':1,'day':'2026-10-12','employee_id':1,'replaced_id':2,
                   'group':'Žiogeliai','hours':4.5,'mode':'extra'}]
        r = cumulative_group_debts(2026,10, EMPLOYEES, PCT, DAYS, absences, events, [])
        rel = employee_cumulative_view(r, 1, EMPLOYEES)
        self.assertEqual(rel[0]['Žiogeliai: Likutis'], 0)
        self.assertAlmostEqual(r['closing_unmatched'][('Žiogeliai',1)],4.5)

    def test_unmatched_overtime_carries_and_matches_later(self):
        corrections = [{'id':1,'day':'2026-10-12','employee_id':1,
                        'group':'Žiogeliai','delta_hours':2},
                       {'id':2,'day':'2026-11-09','employee_id':2,
                        'group':'Žiogeliai','delta_hours':-2}]
        r = cumulative_group_debts(2026,11, EMPLOYEES, PCT, DAYS, [], [], corrections)
        rel = employee_cumulative_view(r, 1, EMPLOYEES)
        self.assertEqual(rel[0]['Žiogeliai: Likutis'], 2)
        self.assertEqual(r['closing_unmatched'][('Žiogeliai',1)],0)

    def test_cross_year_carry(self):
        events = [{'id':1,'day':'2026-12-14','employee_id':1,'replaced_id':2,
                   'group':'Žiogeliai','hours':1,'mode':'extra'}]
        r = cumulative_group_debts(2027,1, EMPLOYEES, PCT, DAYS, [], events, [])
        rel = employee_cumulative_view(r, 1, EMPLOYEES)
        self.assertEqual(rel[0]['Žiogeliai: Ankstesnis likutis'], 1)
        self.assertEqual(rel[0]['Žiogeliai: Likutis'], 1)

    def test_real_staffing_schedule_no_weekly_pct_validation(self):
        real_employees = [{"id": 1, "name": "Diana"}, {"id": 2, "name": "Renata"},
                          {"id": 3, "name": "Vilma"}]
        real_pct = {(1, "Žiogeliai"): 75, (1, "Žirniukai"): 50,
                    (2, "Žiogeliai"): 125, (2, "Žirniukai"): 0,
                    (3, "Žiogeliai"): 0, (3, "Žirniukai"): 150}
        weekly = {(1, "Žiogeliai"): (0,12,0,12,0), (1, "Žirniukai"): (0,0,12,0,0),
                  (2, "Žiogeliai"): (12,0,12,0,12), (2, "Žirniukai"): (0,0,0,0,0),
                  (3, "Žiogeliai"): (0,0,0,0,0), (3, "Žirniukai"): (12,12,0,12,12)}
        wh = {(i,g,wd): hrs for (i,g), seq in weekly.items() for wd,hrs in enumerate(seq)}
        r=calculate_month(2026,10,real_employees,real_pct,wh,[],[],[])
        by_name={v['Darbuotojas']:v for v in r['people']}
        self.assertEqual(by_name['Diana']['Žiogeliai: planas'],99)
        self.assertEqual(by_name['Diana']['Žirniukai: planas'],66)
        self.assertEqual(by_name['Diana']['Žiogeliai: dirbta'],108)
        self.assertEqual(by_name['Diana']['Žirniukai: dirbta'],48)
        self.assertEqual(by_name['Renata']['Žiogeliai: planas'],165)
        self.assertEqual(by_name['Renata']['Žiogeliai: dirbta'],156)
        self.assertEqual(by_name['Vilma']['Žirniukai: planas'],198)
        self.assertEqual(by_name['Vilma']['Žirniukai: dirbta'],216)
        balances = {v['Darbuotojas']: (v['Žiogeliai: balansas'], v['Žirniukai: balansas']) for v in r['people']}
        self.assertEqual(balances, {'Diana': (9,-18), 'Renata': (-9,0), 'Vilma': (0,18)})

    def test_october_initial_debts_begin_without_prior_months(self):
        real_employees=[{"id": 1, "name": "Diana"}, {"id": 2, "name": "Renata"},
                        {"id": 3, "name": "Vilma"}]
        r=cumulative_group_debts(2026,10,real_employees,PCT,DAYS,[],[],[],start_year=2026,start_month=10)
        self.assertEqual(r['begin'],(2026,10))
        self.assertTrue(all(v==0 for v in r['opening_pairs'].values()))

    def test_temporary_percentage_extra_is_not_debt(self):
        # A bazinis krūvis 125 %, laikinai iki 150 %.
        # Darbas iki laikino padidinimo normos nekuria skolos.
        temp = [{'employee_id':1, 'group':'Žiogeliai',
                 'start_date':'2026-10-01', 'end_date':'2026-10-31',
                 'additional_pct':25}]
        corrected = [{'id':1,'day':'2026-10-12','employee_id':1,
                      'group':'Žiogeliai','delta_hours':2}]
        calc_result = calculate_month(2026,10,EMPLOYEES,PCT,DAYS,[],[],corrected,
                                      temporary_increases=temp)
        person = calc_result['people'][0]
        self.assertEqual(person['Žiogeliai: dirbta'] - person['Žiogeliai: planas'], 2)
        self.assertEqual(person['Žiogeliai: neįtraukiama į balansą'], 2)
        self.assertEqual(person['Žiogeliai: balansas'], 0)
        carry = cumulative_group_debts(2026,10,EMPLOYEES,PCT,DAYS,[],[],corrected,
                                       start_year=2026,start_month=10,temporary_increases=temp)
        self.assertEqual(carry['closing_unmatched'][('Žiogeliai',1)], 0)

    def test_temporary_pct_without_extra_never_creates_underwork(self):
        temp = [{'employee_id':1,'group':'Žiogeliai',
                 'start_date':'2026-10-12','end_date':'2026-10-16','additional_pct':25}]
        r = calculate_month(2026,10,EMPLOYEES,PCT,DAYS,[],[],[],
                            temporary_increases=temp)
        self.assertEqual(r['people'][0]['Žiogeliai: balansas'], 0)
        self.assertAlmostEqual(r['people'][0]['Žiogeliai: laikino padidinimo norma'], 7.5)

    def test_temporary_pct_excess_over_cap_is_balance(self):
        temp = [{'employee_id':1,'group':'Žiogeliai',
                 'start_date':'2026-10-12','end_date':'2026-10-12','additional_pct':25}]
        corrected = [{'id':1,'day':'2026-10-12','employee_id':1,
                      'group':'Žiogeliai','delta_hours':4}]
        r = calculate_month(2026,10,EMPLOYEES,PCT,DAYS,[],[],corrected,
                            temporary_increases=temp)
        self.assertAlmostEqual(r['people'][0]['Žiogeliai: laikino padidinimo norma'], 1.5)
        self.assertAlmostEqual(r['people'][0]['Žiogeliai: neįtraukiama į balansą'], 1.5)
        self.assertAlmostEqual(r['people'][0]['Žiogeliai: balansas'], 2.5)

    def test_temporary_pct_only_excludes_work_on_increase_dates(self):
        temp = [{'employee_id':1,'group':'Žiogeliai',
                 'start_date':'2026-10-13','end_date':'2026-10-13','additional_pct':25}]
        corrected = [{'id':1,'day':'2026-10-12','employee_id':1,
                      'group':'Žiogeliai','delta_hours':2}]
        r = calculate_month(2026,10,EMPLOYEES,PCT,DAYS,[],[],corrected,
                            temporary_increases=temp)
        self.assertEqual(r['people'][0]['Žiogeliai: neįtraukiama į balansą'], 0)
        self.assertEqual(r['people'][0]['Žiogeliai: balansas'], 2)

    def test_temporary_pct_allocation_cap_is_150(self):
        temp = [{'employee_id':1,'group':'Žiogeliai',
                 'start_date':'2026-10-12','end_date':'2026-10-12','additional_pct':60}]
        r = calculate_month(2026,10,EMPLOYEES,PCT,DAYS,[],[],[],
                            temporary_increases=temp)
        self.assertAlmostEqual(r['people'][0]['Žiogeliai: laikino padidinimo norma'], 1.5)
        self.assertTrue(any('150 %' in w for w in r['warnings']))

    def test_text_suggestion(self):
        self.assertEqual(suggest_hours_from_text('Darbuotojas A Žirniukuose dirbo 2 val. ilgiau', EMPLOYEES),
                         {'employee_id':1,'group':'Žirniukai','delta_hours':2})
        self.assertEqual(suggest_hours_from_text('Darbuotojas C Ziogeliuose -1,5 val.', EMPLOYEES),
                         {'employee_id':3,'group':'Žiogeliai','delta_hours':-1.5})
        self.assertIsNone(suggest_hours_from_text('Kažkas dirbo ilgiau', EMPLOYEES))


    def test_2026_november_public_holiday_cancels_shift_without_debt(self):
        staff=[{'id':1,'name':'Diana'},{'id':2,'name':'Renata'},{'id':3,'name':'Vilma'}]
        pct={(1,'Žiogeliai'):75,(1,'Žirniukai'):50,
             (2,'Žiogeliai'):125,(2,'Žirniukai'):0,
             (3,'Žiogeliai'):0,(3,'Žirniukai'):150}
        hours={(eid,group,wd):shift for (eid,group),week in {
            (1,'Žiogeliai'):[0,12,0,12,0],(1,'Žirniukai'):[0,0,12,0,0],
            (2,'Žiogeliai'):[12,0,12,0,12],(2,'Žirniukai'):[0,0,0,0,0],
            (3,'Žiogeliai'):[0,0,0,0,0],(3,'Žirniukai'):[12,12,0,12,12],
        }.items() for wd,shift in enumerate(week)}
        with_holiday=calculate_month(2026,11,staff,pct,hours,[],[],[])
        without_holiday=calculate_month(2026,11,staff,pct,hours,[],[],[],use_holidays=False)
        for person,baseline in zip(with_holiday['people'], without_holiday['people']):
            for group in GROUPS:
                self.assertAlmostEqual(person[f'{group}: balansas'],baseline[f'{group}: balansas'])
        self.assertEqual(with_holiday['people'][1]['Žiogeliai: švenčių pamainos'],12)
        self.assertEqual(with_holiday['people'][2]['Žirniukai: švenčių pamainos'],12)
        monday = [r for r in with_holiday['daily'] if r['date']==date(2026,11,2)]
        self.assertEqual(len(monday),6)
        self.assertTrue(all(r['actual']==0 and r['planned']==0 and r['absent_hours']==0 for r in monday))

    def test_public_holiday_is_not_recorded_as_vacation_or_sick_leave(self):
        absence=[{'id':1,'employee_id':1,'kind':'Atostogos',
                  'start_date':'2026-11-02','end_date':'2026-11-03'}]
        r=calc(11,absences=absence)
        day2=[x for x in r['daily'] if x['employee_id']==1 and x['date']==date(2026,11,2)]
        self.assertTrue(all(x['absence']=='' and x['absent_hours']==0 for x in day2))
        day3=[x for x in r['daily'] if x['employee_id']==1 and x['date']==date(2026,11,3)]
        self.assertTrue(all(x['absence']=='Atostogos' and x['absent_hours']>0 for x in day3))

    def test_no_substitutions_or_extra_on_holidays(self):
        substitute=[{'id':1,'day':'2026-11-02','employee_id':1,'replaced_id':2,
                     'group':'Žiogeliai','hours':2,'mode':'extra'}]
        correction=[{'id':1,'day':'2026-11-02','employee_id':1,
                     'group':'Žirniukai','delta_hours':1}]
        r=calc(11,substitutions=substitute,corrections=correction)
        self.assertTrue(all(x['actual']==0 for x in r['daily'] if x['date']==date(2026,11,2)))
        self.assertTrue(any('šventinė diena' in w for w in r['warnings']))

    def test_easter_monday_changes_by_year(self):
        from grafiko_logika import holiday_names
        self.assertEqual(holiday_names(2027)[date(2027,3,29)], 'Antroji Velykų diena')
        self.assertEqual(holiday_names(2026)[date(2026,4,6)], 'Antroji Velykų diena')

if __name__=='__main__':
    unittest.main()
