import unittest
from datetime import date
from grafiko_rodymas import month_annotations

PEOPLE=[{'id':1,'name':'Diana'},{'id':2,'name':'Renata'},{'id':3,'name':'Vilma'}]
ALLOC={(1,'Žiogeliai'):75,(1,'Žirniukai'):50,(2,'Žiogeliai'):125,
       (2,'Žirniukai'):0,(3,'Žiogeliai'):0,(3,'Žirniukai'):150}
ABS=[{'employee_id':1,'kind':'Atostogos','start_date':'2026-10-13','end_date':'2026-10-15'}]
SUB=[{'day':'2026-10-15','employee_id':2,'replaced_id':1,'group':'Žiogeliai',
      'hours':2,'mode':'extra','purpose':'Pavadavimas'}]
COR=[{'day':'2026-10-12','employee_id':1,'group':'Žirniukai',
      'delta_hours':12,'note':'Papildomas pirmadienis'}]
TEMP=[{'employee_id':2,'group':'Žiogeliai','start_date':'2026-10-13',
       'end_date':'2026-10-15','additional_pct':25}]
NOTES=[{'day':'2026-10-14','note':'Bendra pastaba'}]

class TestMonthlyAnnotations(unittest.TestCase):
    def labels(self,emp=1,year=2026,month=10,holidays=()):
        return month_annotations(year,month,emp,PEOPLE,ALLOC,ABS,SUB,COR,TEMP,NOTES,holidays)
    def test_vacation_visible_each_day(self):
        days,_=self.labels()
        self.assertEqual([x['text'] for x in days[date(2026,10,14)]],['Atostogos'])
    def test_substitution_visible_for_both_sides(self):
        a,_=self.labels(1)
        b,_=self.labels(2)
        self.assertIn('Pavadavo Renata',a[date(2026,10,15)][1]['text'])
        self.assertTrue(any('už Diana' in entry['text'] for entry in b[date(2026,10,15)]))
    def test_correction_and_temp_pct(self):
        a,_=self.labels(1)
        b,_=self.labels(2)
        self.assertIn('+12 val.',a[date(2026,10,12)][0]['text'])
        self.assertIn('150 %',b[date(2026,10,14)][0]['text'])
    def test_shared_notes_not_repeated(self):
        day,n=self.labels(3)
        self.assertNotIn(date(2026,10,14),day)
        self.assertEqual(n[0]['note'],'Bendra pastaba')
    def test_holiday_not_annotated(self):
        days,_=self.labels(1,holidays={date(2026,10,14)})
        self.assertNotIn(date(2026,10,14),days)
    def test_future_month_has_no_old_event(self):
        days,_=self.labels(month=11)
        self.assertEqual(days,{})

if __name__=='__main__':unittest.main()
