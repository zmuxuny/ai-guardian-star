"""Run repeatable offline scenarios and export expected/actual structured results.

python tools/run_weekly_scenarios.py --output .tmp/weekly-results.json
No sensors, network, audio or MaaS calls. Exit nonzero on any assertion failure.
"""
import argparse
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_weekly_report as scenarios

EXPECTED = {
 'test_cross_week_duplicate_and_threshold': {'current_count':1,'previous_count':0},
 'test_duplicate_events': {'current_count':1},
 'test_feedback_revoke': {'current_count':1,'human_confirmed_count':0},
 'test_timezone': {'utc_count':0,'utc_plus_8_count':1},
 'test_expiry_and_personal_delete': {'current_count':0,'observation_status':'no_observations'},
}


class Result(unittest.TextTestResult):
    def startTest(self,test):
        super().startTest(test)
        # tearDown executes after assertions, before setUp's directory cleanup.
        if isinstance(test,scenarios.WeeklyTests):
            test.tearDown = lambda: self.capture(test)

    def capture(self,test):
        report=test.report()
        row=test.row(report)
        actual={'current_count':row['current']['event_count'],
                'previous_count':row['previous']['event_count'],
                'human_confirmed_count':row['current']['human_confirmed_count'],
                'observation_status':row['current']['observation_status']}
        if test._testMethodName=='test_timezone':
            other=test.store.weekly('shadow','2026-11-09',regions=('room',),offset_minutes=480)
            actual.update(utc_count=row['current']['event_count'],utc_plus_8_count=test.row(other)['current']['event_count'])
        expected=EXPECTED.get(test._testMethodName,{})
        for key,value in expected.items():
            test.assertEqual(actual[key],value)
        self.records.append(dict(scenario=test._testMethodName,expected=expected,actual=actual,aggregation=report))

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.records=[]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('.tmp/weekly-results.json'))
    args=parser.parse_args()
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromModule(scenarios))
    payload=dict(schema_version=1,passed=result.wasSuccessful(),tests_run=result.testsRun,
                 failures=len(result.failures),errors=len(result.errors),scenarios=result.records)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
