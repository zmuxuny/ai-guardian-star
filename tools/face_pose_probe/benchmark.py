"""Privacy-bounded reporting helpers for the board head-pose probe."""

import hashlib
import math


class BenchmarkInputError(ValueError):
    pass


def _percentile(values, percentile):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * percentile / 100.0
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def build_report(model_id, rows):
    if not str(model_id).strip():
        raise BenchmarkInputError("model_id is required")
    samples = []
    absolute_errors = {"yaw": [], "pitch": [], "roll": []}
    latencies = []
    matches = 0
    mismatches = 0
    for row in rows:
        sample_id = str(row.get("sample_id", ""))
        if not sample_id.strip():
            raise BenchmarkInputError("sample_id is required")
        sample_hash = hashlib.sha256(sample_id.encode("utf-8")).hexdigest()
        try:
            expected = row["expected"]
            actual = row["actual"]
            latency = float(row["latency_ms"])
            errors = {
                axis: abs(float(actual[axis]) - float(expected[axis]))
                for axis in ("yaw", "pitch", "roll")
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise BenchmarkInputError("invalid benchmark row") from exc
        if latency < 0.0 or not math.isfinite(latency) or not all(
                math.isfinite(error) for error in errors.values()):
            raise BenchmarkInputError("benchmark metrics must be finite")
        for axis, error in errors.items():
            absolute_errors[axis].append(error)
        latencies.append(latency)
        gate_match = row.get("expected_pose") == row.get("actual_pose")
        matches += int(gate_match)
        mismatches += int(not gate_match)
        samples.append({
            "sample_hash": sample_hash,
            "latency_ms": latency,
            "absolute_error_degrees": errors,
            "gate_match": gate_match,
        })
    return {
        "model_id": str(model_id),
        "sample_count": len(samples),
        "latency_ms": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
        },
        "mae_degrees": {
            axis: (sum(values) / len(values) if values else None)
            for axis, values in absolute_errors.items()
        },
        "gate_confusion": {"match": matches, "mismatch": mismatches},
        "samples": samples,
    }
