"""Deterministic, device-free sedentary care.

Full event/state matrix and timing policy:
docs/superpowers/specs/2026-11-16-sedentary-care-design.md

SIT is a trusted observation, not a request to assume indefinite sitting.
The caller owns person association and must send TARGET_CHANGED on a switch.
"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from enum import Enum
import math


class Event(str, Enum):
    SIT = 'SIT'
    STAND = 'STAND'
    NON_SIT = 'NON_SIT'
    OCCLUDE = 'OCCLUDE'
    LOW_CONFIDENCE = 'LOW_CONFIDENCE'
    MISSING = 'MISSING'
    TARGET_LOST = 'TARGET_LOST'
    DEVICE_ERROR = 'DEVICE_ERROR'
    TARGET_CHANGED = 'TARGET_CHANGED'
    RESPOND = 'RESPOND'
    DEFER = 'DEFER'
    DECLINE = 'DECLINE'
    TIMEOUT = 'TIMEOUT'


UNCERTAIN_EVENTS = frozenset({Event.OCCLUDE, Event.LOW_CONFIDENCE, Event.MISSING,
                              Event.TARGET_LOST, Event.DEVICE_ERROR})
TEXTS = {
    'L0': ('sedentary.l0', '已经坐了一会儿，方便的话起来活动一下吧。'),
    'L1': ('sedentary.l1', '您已连续久坐，建议现在起身走动、舒展一下。'),
}


def _positive(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0)


@dataclass(frozen=True)
class Config:
    l0_seconds: float = 1800
    upgrade_seconds: float = 300
    repeat_seconds: float = 300
    ack_seconds: float = 600
    observation_ttl: float = 30
    uncertainty_ttl: float = 120
    max_l1: int = 2
    quiet_start: time | None = time(22)
    quiet_end: time | None = time(7)

    def __post_init__(self):
        for name in ('l0_seconds', 'upgrade_seconds', 'repeat_seconds',
                     'ack_seconds', 'observation_ttl', 'uncertainty_ttl'):
            if not _positive(getattr(self, name)):
                raise ValueError(f'{name} must be a positive finite number')
        if type(self.max_l1) is not int or self.max_l1 < 1:
            raise ValueError('max_l1 must be a positive integer')
        if (self.quiet_start is None) != (self.quiet_end is None):
            raise ValueError('quiet_start and quiet_end must both be set or absent')
        if self.quiet_start is not None:
            for value in (self.quiet_start, self.quiet_end):
                if not isinstance(value, time) or value.tzinfo is not None:
                    raise ValueError('quiet boundaries must be local times without tzinfo')
            if self.quiet_start == self.quiet_end:
                raise ValueError('equal quiet boundaries are ambiguous')


class VirtualClock:
    """Fixed-offset wall clock mapped to manually advanced monotonic seconds."""

    def __init__(self, origin=None):
        self.origin = origin if origin is not None else datetime(
            2026, 11, 16, 12, tzinfo=timezone(timedelta(hours=8)))
        if not isinstance(self.origin, datetime) or not isinstance(self.origin.tzinfo, timezone):
            raise ValueError('origin requires an explicit fixed-offset timezone')
        self._now = 0.0

    @property
    def now(self):
        return self._now

    def wall_at(self, seconds):
        return self.origin + timedelta(seconds=seconds)

    def advance(self, seconds):
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
            raise ValueError('time increment must be a finite nonnegative number')
        if not math.isfinite(seconds) or seconds < 0 or not math.isfinite(self._now + seconds):
            raise ValueError('time cannot go backwards or become nonfinite')
        target = self._now + seconds
        self.wall_at(target)  # Validate representable wall time before mutation.
        self._now = target


class RecordingSpeaker:
    """Append-only simulated output; never opens an audio device."""

    def __init__(self):
        self.records = []

    def record(self, record):
        self.records.append(deepcopy(record))


class CareMachine:
    """Consumes Event values through handle(); exports detached JSON-ready data.

    Injected clock contract: read-only .now monotonic seconds and
    .wall_at(seconds) -> datetime in a fixed-offset timezone.
    The owner advances the clock and calls handle(), including TIMEOUT when
    no observations arrive. There are no background threads or real waits.
    """

    def __init__(self, clock, config=None, speaker=None):
        self.clock = clock
        self.config = config if config is not None else Config()
        self.speaker = speaker if speaker is not None else RecordingSpeaker()
        self._now = clock.now
        if not isinstance(self._now, (int, float)) or not math.isfinite(self._now):
            raise ValueError('clock must return finite monotonic seconds')
        wall = clock.wall_at(self._now)
        if not isinstance(wall, datetime) or not isinstance(wall.tzinfo, timezone):
            raise ValueError('clock must use a fixed-offset wall timezone')
        self.transitions = []
        self._reset()

    def _reset(self):
        self.phase = 'IDLE'
        self.seated = 0.0
        self.remaining = None
        self.pending = None
        self.level = None
        self.counts = {'L0': 0, 'L1': 0}
        self.uncertain_since = None
        self.uncertainty_reason = None
        self.last_observation = None

    @property
    def state(self):
        return 'PAUSED' if self.uncertain_since is not None else self.phase

    def _quiet(self):
        start, end = self.config.quiet_start, self.config.quiet_end
        if start is None:
            return False
        local = self.clock.wall_at(self._now).time()
        return start <= local < end if start < end else local >= start or local < end

    def _quiet_end(self):
        wall = self.clock.wall_at(self._now)
        end = datetime.combine(wall.date(), self.config.quiet_end, tzinfo=wall.tzinfo)
        if end <= wall:
            end += timedelta(days=1)
        return self._now + (end - wall).total_seconds()

    def snapshot(self):
        return {
            'at': self._now, 'wall_time': self.clock.wall_at(self._now).isoformat(),
            'state': self.state, 'phase': self.phase,
            'seated_seconds': self.seated, 'remaining_seconds': self.remaining,
            'uncertainty_seconds': (self._now - self.uncertain_since
                                    if self.uncertain_since is not None else 0),
            'uncertainty_reason': self.uncertainty_reason,
            'cooldown_seconds': self.remaining if self.phase == 'ACK' else None,
            'level': self.level, 'pending_level': self.pending,
            'counts': dict(self.counts), 'quiet': self._quiet(),
        }

    def export(self):
        return deepcopy({'snapshot': self.snapshot(), 'transitions': self.transitions,
                         'broadcasts': self.speaker.records})

    def _trace(self, event, before, decision='noop'):
        self.transitions.append({
            'at': self._now, 'event': event, 'before': before,
            'after': self.state, 'decision': decision, 'snapshot': self.snapshot(),
        })

    def _advance(self, target):
        elapsed = target - self._now
        if self.uncertain_since is None and self.phase != 'IDLE':
            self.seated += elapsed
            if self.remaining is not None and self.pending is None:
                self.remaining = max(0.0, self.remaining - elapsed)
        self._now = target

    def _deadline(self):
        if self.uncertain_since is not None:
            return self.uncertain_since + self.config.uncertainty_ttl
        deadlines = []
        if self.phase != 'IDLE' and self.last_observation is not None:
            deadlines.append(self.last_observation + self.config.observation_ttl)
        if self.pending is not None:
            deadlines.append(self._quiet_end() if self._quiet() else self._now)
        elif self.remaining is not None:
            deadlines.append(self._now + self.remaining)
        return min(deadlines) if deadlines else None

    def _pause(self, reason):
        if self.uncertain_since is None:
            self.uncertain_since = self._now
        self.uncertainty_reason = reason

    def _deliver(self, level):
        if self._quiet():
            self.pending = level
            self.remaining = None
            return 'suppressed'
        text_id, text = TEXTS[level]
        self.speaker.record({'at': self._now,
                             'wall_time': self.clock.wall_at(self._now).isoformat(),
                             'level': level, 'text_id': text_id, 'text': text})
        self.level = level
        self.counts[level] += 1
        self.pending = None
        if level == 'L0':
            self.phase, self.remaining = 'L0', self.config.upgrade_seconds
        elif self.counts['L1'] >= self.config.max_l1:
            self.phase, self.remaining = 'EXHAUSTED', None
        else:
            self.phase, self.remaining = 'L1', self.config.repeat_seconds
        return 'broadcast'

    def _tick(self):
        before = self.state
        if self.uncertain_since is not None:
            if self._now >= self.uncertain_since + self.config.uncertainty_ttl:
                self._reset()
                self._trace('uncertainty_expired', before, 'reset')
            return
        if (self.phase != 'IDLE' and self.last_observation is not None
                and self._now >= self.last_observation + self.config.observation_ttl):
            self._pause('observation_timeout')
            self._trace('observation_timeout', before, 'pause')
        elif self.pending is not None and not self._quiet():
            decision = self._deliver(self.pending)
            self._trace('pending_released', before, decision)
        elif self.remaining is not None and self.remaining <= 1e-9:
            event = 'ack_timeout' if self.phase == 'ACK' else 'reminder_timeout'
            level = 'L0' if self.counts['L0'] == 0 else 'L1'
            decision = self._deliver(level)
            self._trace(event, before, decision)

    def _process_until(self, target, inclusive):
        while True:
            due = self._deadline()
            if due is None or due > target or (due == target and not inclusive):
                return
            self._advance(due)
            self._tick()

    def handle(self, event):
        # Validate before processing overdue work so rejected events are atomic.
        try:
            event = Event(event)
        except (ValueError, TypeError):
            raise ValueError(f'unknown care event: {event!r}') from None
        target = self.clock.now
        if not isinstance(target, (int, float)) or not math.isfinite(target) or target < self._now:
            raise ValueError('clock went backwards or became nonfinite')
        self.clock.wall_at(target)
        self._process_until(target, inclusive=False)
        self._advance(target)
        # A complete uncertainty TTL invalidates the old episode even if SIT
        # arrives at exactly that instant. Short pauses resume the saved phase.
        if (self.uncertain_since is not None
                and target >= self.uncertain_since + self.config.uncertainty_ttl):
            self._tick()
        before = self.state
        decision = 'noop'
        if event in (Event.STAND, Event.NON_SIT, Event.TARGET_CHANGED):
            self._reset()
            decision = 'reset'
        elif event == Event.SIT:
            self.uncertain_since = self.uncertainty_reason = None
            self.last_observation = self._now
            if self.phase == 'IDLE':
                self.phase, self.remaining = 'SITTING', self.config.l0_seconds
            decision = 'observe'
        elif event in UNCERTAIN_EVENTS:
            self._pause(event.value)
            decision = 'pause'
        elif event in (Event.RESPOND, Event.DEFER):
            if self.phase != 'ACK' and (self.phase in ('L0', 'L1') or self.pending is not None):
                self.phase, self.remaining = 'ACK', self.config.ack_seconds
                self.pending = None
                decision = 'cancelled'
        elif event == Event.DECLINE and self.phase != 'IDLE':
            self.phase, self.remaining, self.pending = 'EXHAUSTED', None, None
            decision = 'cancelled'
        self._trace(event.value, before, decision)
        self._process_until(target, inclusive=True)
        return self.snapshot()
