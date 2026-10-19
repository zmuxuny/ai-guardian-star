"""Validated opt-in recording configuration (no import or disabled side effects)."""
import json
import math
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class RecordingConfig:
    enabled: bool = False
    data_root: Optional[Path] = None
    segment_seconds: int = 300
    record_fps: float = 15.0
    bitrate_mbps: float = 1.0
    retention_days: int = 7
    timezone: str = "Asia/Shanghai"
    storage_quota_bytes: Optional[int] = None
    min_free_bytes: Optional[int] = None
    queue_frames: int = 15
    queue_bytes: int = 16 * 1024 * 1024
    cleanup_interval_seconds: int = 60
    encoder: Optional[str] = None
    journal_mode: str = "DELETE"
    synchronous: str = "FULL"
    history_token: Optional[str] = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("enabled must be a JSON boolean")
        integer_ranges = {
            "segment_seconds": (1, 3600), "retention_days": (7, 7),
            "queue_frames": (1, 300), "queue_bytes": (1, 1024 ** 3),
            "cleanup_interval_seconds": (1, 3600),
        }
        for name, bounds in integer_ranges.items():
            value = getattr(self, name)
            if type(value) is not int or not bounds[0] <= value <= bounds[1]:
                raise ValueError("invalid " + name)
        for name, maximum in (("record_fps", 120), ("bitrate_mbps", 1000)):
            value = getattr(self, name)
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not 0 < value <= maximum):
                raise ValueError("invalid " + name)
        for name in ("storage_quota_bytes", "min_free_bytes"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError(name + " must be a positive integer")
        if self.timezone != "Asia/Shanghai":
            raise ValueError("only Asia/Shanghai is supported in this preparation")
        if self.journal_mode not in ("DELETE",):
            raise ValueError("only conservative DELETE journal mode is supported")
        if self.synchronous not in ("FULL", "EXTRA"):
            raise ValueError("synchronous must be FULL or EXTRA")
        if self.encoder is not None and (not isinstance(self.encoder, str)
                                         or not self.encoder.strip()):
            raise ValueError("encoder must be a nonempty string or null")
        if self.history_token is not None and not isinstance(self.history_token, str):
            raise ValueError("history token must be a string")
        if self.data_root is not None:
            if not isinstance(self.data_root, (str, Path)) or not str(self.data_root).strip():
                raise ValueError("data_root must be an explicit absolute path")
            root = Path(self.data_root)
            if not root.is_absolute() or root == Path(root.anchor) or ".." in root.parts:
                raise ValueError("data_root must be an explicit non-root absolute path")
            object.__setattr__(self, "data_root", root)
        if self.enabled and (self.data_root is None or self.storage_quota_bytes is None
                             or self.min_free_bytes is None):
            raise ValueError("enabled recording requires data_root, quota and minimum free bytes")

    @classmethod
    def from_env(cls, environ=None):
        env = os.environ if environ is None else environ
        values = {}
        filename = env.get("AI_GUARDIAN_RECORDING_CONFIG")
        if filename:
            with open(filename, "r", encoding="utf-8-sig") as stream:
                values = json.load(stream)
            if not isinstance(values, dict):
                raise ValueError("recording configuration must be an object")
            allowed = {item.name for item in fields(cls)} - {"history_token"}
            if set(values) - allowed:
                raise ValueError("unknown recording configuration keys")
        values["history_token"] = env.get("AI_GUARDIAN_HISTORY_TOKEN") or None
        return cls(**values)
