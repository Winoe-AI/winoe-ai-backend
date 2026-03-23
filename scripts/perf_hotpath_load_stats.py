from __future__ import annotations

import math
import statistics


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return float(sorted_values[lower])
    weight = position - lower
    return float(sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight)


def coeff_of_variation(values: list[float]) -> float:
    filtered = [float(v) for v in values if v >= 0]
    if len(filtered) < 2:
        return 0.0
    mean = statistics.mean(filtered)
    if math.isclose(mean, 0.0):
        return 0.0
    return float(statistics.stdev(filtered) / mean)


__all__ = ["coeff_of_variation", "quantile"]
