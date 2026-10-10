"""Tests: bendri grupių kalendoriai, atostogos, šventės, valandos, pavadavimai."""
import unittest
from datetime import date
from grafiko_rodymas import group_month_entries
from grafiko_logika import calculate_month, holiday_names

PEOPLE = [{'id': 1, 'name': 'Diana'}, {'id': 2, 'name': 'Renata'}, {'id': 3, 'name': 'Vilma'}]
ALLOC = {(1, 'Žiogeliai'): 75, (1, 'Žirniukai'): 50,
         (2, 'Žiogeliai'): 125, (2, 'Žirniukai'): 0,
         (3, 'Žiogeliai'): 0, (3, 'Žirniukai'): 150}
SCHEDULE = {
    (1, 'Žiogeliai'): (0, 12, 0, 12, 0),
    (1, 'Žirniukai'): (0, 0, 12, 0, 0),
    (2, 'Žiogeliai'): (12, 0, 12, 0, 12),
    (2, 'Žirniukai'): (0, 0, 0, 0, 0),
    (3, 'Žiogeliai'): (0, 0, 0, 0, 0),
    (3, 'Žirniukai'): (12, 12, 0, 12, 12),
}
HOURS = {(eid, group, weekday): values[weekday]
         for (eid, group), values in SCHEDULE.items() for weekday in range(5)}

class GroupCalendarTests(unittest.TestCase):
    def group(self, group='Žiogeliai', month=10, absences=(), substitutions=(), corrections=(), temporary=()):
        calc = calculate_month(2026, month, PEOPLE, ALLOC, HOURS, absences, substitutions, corrections,
                               temporary_increases=temporary)
        return group_month_entries(2026, month, group, calc['daily'], PEOPLE,
                                   absences, substitutions, corrections, temporary,
                                   calc['holiday_names'])

    def test_monday_to_friday_only(self):
        cells = self.group()
        self.assertEqual(len(cells), 22)
        self.assertTrue(all(x['date'].weekday() < 5 for x in cells))

    def test_group_separation_and_real_schedules(self):
        z = next(x for x in self.group('Žiogeliai') if x['date'] == date(2026, 10, 5))
        r = next(x for x in self.group('Žirniukai') if x['date'] == date(2026, 10, 5))
        self.assertEqual([(p['name'], p['hours']) for p in z['staff']], [('Renata', 12)])
        self.assertEqual([(p['name'], p['hours']) for p in r['staff']], [('Vilma', 12)])

    def test_vacations_are_shown_in_group_with_scheduled_shift(self):
        a = [{'employee_id': 1, 'kind': 'Atostogos', 'start_date': '2026-10-13', 'end_date': '2026-10-13'}]
        z = next(x for x in self.group(absences=a) if x['date'] == date(2026, 10, 13))
        self.assertEqual(z['staff'][0]['name'], 'Diana')
        self.assertEqual(z['staff'][0]['hours'], 0)
        self.assertEqual(z['staff'][0]['absence'], 'Atostogos')
        r = next(x for x in self.group('Žirniukai', absences=a) if x['date'] == date(2026, 10, 13))
        self.assertFalse(any(p['name'] == 'Diana' for p in r['staff']))

    def test_replacement_note_and_no_double_count(self):
        s = [{'id': 1, 'day': '2026-10-05', 'employee_id': 1, 'replaced_id': 2,
              'group': 'Žiogeliai', 'hours': 3, 'mode': 'extra', 'source_group': None,
              'purpose': 'Ankstesnės skolos dengimas'}]
        z = next(x for x in self.group(substitutions=s) if x['date'] == date(2026, 10, 5))
        self.assertEqual(z['total_hours'], 12)
        self.assertTrue(any('Diana už Renata' in note for note in z['annotations']))
        self.assertEqual([(p['name'],p['hours']) for p in z['staff']], [('Diana',3), ('Renata',9)])

    def test_no_group_cross_contamination(self):
        c = [{'day': '2026-10-05', 'employee_id': 1, 'group': 'Žiogeliai',
              'delta_hours': 1, 'note': 'papildomai'}]
        z = next(x for x in self.group(corrections=c) if x['date'] == date(2026,10,5))
        r = next(x for x in self.group('Žirniukai', corrections=c) if x['date'] == date(2026,10,5))
        self.assertTrue(z['annotations'])
        self.assertFalse(r['annotations'])

    def test_holiday_is_non_working(self):
        z = next(x for x in self.group(month=11) if x['date'] == date(2026,11,2))
        self.assertEqual(z['total_hours'], 0)
        self.assertEqual(z['holiday'], 'Vėlinės')

    def test_temporary_vacation_workload_visible(self):
        t = [{'employee_id': 2, 'group': 'Žiogeliai',
              'start_date': '2026-10-13', 'end_date': '2026-10-13', 'additional_pct': 25}]
        z = next(x for x in self.group(temporary=t) if x['date'] == date(2026,10,13))
        self.assertTrue(any('Atostogų etatas: Renata +25' in x for x in z['annotations']))

if __name__ == '__main__': unittest.main()
