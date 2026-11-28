"""Read complete observation CSVs, persist routine events and exchange v5 on loopback."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

from tools import late_wakeup_demo as replay
from tools import personalization_http as http
from tools import routine_alert_demo as routine


class RoutinePeer:
    def __init__(self, app, history):
        if app.route != http.REMINDERS:
            raise ValueError('personalization sender store required')
        self.app = app
        samples = replay.read_samples(Path(history))
        self.history_days = {stamp.date() for stamp in samples}
        self.typical, self.training_days = replay.typical_departure(samples)

    def scan(self, observations):
        samples = replay.read_samples(Path(observations))
        now = self.app.clock()
        if now.utcoffset() is None:
            raise ValueError('clock requires a timezone')
        current = {stamp: row for stamp, row in samples.items() if stamp <= now}
        if self.history_days & {stamp.date() for stamp in current}:
            raise ValueError('history and observations must use separate dates')
        report = {'registered': 0, 'duplicates': 0, 'expired': 0, 'events': [],
                  'future_observations_ignored': len(samples)-len(current)}
        for reminder in routine.detect(current, self.typical):
            payload = {**reminder, 'device_id': self.app.device}
            disposition = self.app.register(payload)
            report['registered' if disposition == 'accepted' else 'duplicates'] += 1
            report['expired'] += replay.read_timestamp(payload['expires_at']) <= now
            report['events'].append({'event_id': payload['event_id'], 'alert_type': payload['alert_type'],
                                     'disposition': disposition})
        return report


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError('positive finite number required')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', type=Path, required=True)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--device-id', required=True)
    parser.add_argument('--model-port', type=int, required=True)
    parser.add_argument('--results-port', type=int, required=True)
    parser.add_argument('--scan-seconds', type=positive, default=5)
    parser.add_argument('--seconds', type=positive, help='bounded pilot duration; omit to keep running')
    args = parser.parse_args()
    if not (1 <= args.model_port <= 65535 and 1 <= args.results_port <= 65535):
        parser.error('ports must be between 1 and 65535')
    if args.model_port == args.results_port or not args.device_id.strip():
        parser.error('distinct ports and a nonblank device ID are required')
    if args.db.resolve() in (args.history.resolve(), args.observations.resolve()):
        parser.error('database must not replace an input CSV')
    try:
        args.db.parent.mkdir(parents=True, exist_ok=True)
        app = http.Personalization(args.db, lambda: datetime.now(timezone.utc), args.device_id)
        scanner = RoutinePeer(app, args.history)

        def receive(payload):
            disposition = app.receive(payload)
            state = app.summary(payload['event_id'])
            print(json.dumps({'event_id': payload['event_id'], 'disposition': disposition,
                              'revision': payload['revision'], 'help_tasks': state['help_tasks']},
                             ensure_ascii=False), flush=True)
            return disposition

        deadline = None if args.seconds is None else time.monotonic()+args.seconds
        next_scan = 0
        with http.serve(http.RESULTS, receive, port=args.results_port):
            print(json.dumps({'mode': 'CSV_rules_peer', 'device_id': args.device_id,
                              'baseline_departure': scanner.typical.isoformat(),
                              'history_days': scanner.training_days,
                              'results_port': args.results_port}, ensure_ascii=False), flush=True)
            while deadline is None or time.monotonic() < deadline:
                if time.monotonic() >= next_scan:
                    try:
                        report = scanner.scan(args.observations)
                        if report['registered']:
                            print(json.dumps(report, ensure_ascii=False), flush=True)
                    except (OSError, ValueError) as error:
                        # A partial CSV write must not stop result reception or durable retries.
                        print(json.dumps({'scan_error': str(error)}, ensure_ascii=False), file=sys.stderr, flush=True)
                    next_scan = time.monotonic()+args.scan_seconds
                app.flush(args.model_port)
                time.sleep(.25)
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__':
    main()
