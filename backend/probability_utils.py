from __future__ import annotations

import math


def _traffic_delay_factor(predicted_traffic_level: str) -> float:
    """Map traffic level to delay multiplier used in probability estimation."""
    normalized = str(predicted_traffic_level).strip().lower()
    if normalized == "low":
        return 1.1
    if normalized == "medium":
        return 1.3
    return 1.6


def _sigmoid(value: float) -> float:
    """Stable sigmoid for converting ratio-like value into 0..1 probability."""
    clamped = max(-12.0, min(12.0, value))
    return 1.0 / (1.0 + math.exp(-clamped))


def calculate_arrival_probability(
    *,
    predicted_travel_time_min: int,
    departure_buffer_min: int,
    predicted_traffic_level: str,
) -> tuple[float, str]:
    """
    Estimate probability of reaching before target arrival time.

    Core idea:
    - estimate potential delay from travel time and traffic factor
    - compare available buffer to expected delay
    - convert ratio into a smooth probability using sigmoid
    """
    travel_time = max(1, int(predicted_travel_time_min))
    buffer_minutes = max(0, int(departure_buffer_min))
    delay_factor = _traffic_delay_factor(predicted_traffic_level)
    predicted_delay = max(1.0, travel_time * (delay_factor - 1.0))

    ratio = (buffer_minutes / predicted_delay) - 1.0
    probability = _sigmoid(ratio)
    probability = max(0.02, min(0.98, probability))
    probability = round(probability, 2)

    percentage = int(round(probability * 100))
    label = (
        f"{percentage}% chance of reaching before the target arrival time"
    )
    return probability, label

