"""Replay synthetic frames through real AlertEpisodeTracker and compare regions.

    python tools/run_shadow_scenarios.py --output .tmp/shadow-regions.json

No real event source or device is connected. stdout and file use the same JSON.
"""
import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.shadow_fixtures import run_all


def main(argv=None, *, cases=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    scenarios = run_all(cases)
    report = {'schema_version': 1, 'passed': all(c['passed'] for c in scenarios),
              'scenario_count': len(scenarios), 'scenarios': scenarios}
    content = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding='utf-8', newline='\n')
    print(content, end='')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', newline='\n')
    raise SystemExit(main())
