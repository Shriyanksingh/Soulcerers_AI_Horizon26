from __future__ import annotations

import math


def _clamp_01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _base_availability_from_label(parking_availability: str) -> float:
    normalized = str(parking_availability or "").strip().lower()
    return {
        "high": 0.72,
        "medium": 0.52,
        "low": 0.28,
    }.get(normalized, 0.5)


def _noise(seed_value: float, index: int) -> float:
    # Deterministic pseudo-random value in [0,1] so demos stay reproducible.
    raw = math.sin(seed_value * (index + 1) * 7.123) * 43758.5453
    return abs(raw - math.floor(raw))


def _label_from_score(score: float, walking_time_min: int) -> str:
    if score >= 0.74:
        return "Best balance"
    if walking_time_min <= 3 and score >= 0.45:
        return "Close but crowded"
    if score >= 0.58:
        return "Good option"
    return "Backup only"


def generate_parking_options(
    *,
    destination_lat: float,
    destination_lng: float,
    parking_availability: str,
    destination_context: str | None = None,
) -> dict:
    """
    Generate nearby parking options for demo-mode intelligence.

    Placeholder logic:
    - uses destination coordinate seed for deterministic variety
    - scores options using availability and walking distance
    """
    base_availability = _base_availability_from_label(parking_availability)
    seed = abs(float(destination_lat) * 1000.0) + abs(float(destination_lng) * 1000.0)

    names = [
        "Parking A",
        "Parking B",
        "Parking C",
        "Parking D",
    ]

    options = []
    for idx, name in enumerate(names):
        variation = _noise(seed, idx)
        walking_time = max(2, min(9, int(round(2 + idx * 1.8 + variation * 1.5))))

        # Slightly bias later options toward better open-space probability.
        availability_probability = _clamp_01(
            base_availability + (0.12 - idx * 0.04) + (variation - 0.5) * 0.22
        )
        predicted_occupancy = _clamp_01(1.0 - availability_probability)

        # Weighted score: availability matters more than walking distance.
        walking_score = _clamp_01(1.0 - ((walking_time - 1) / 10))
        parking_score = 0.72 * availability_probability + 0.28 * walking_score
        parking_score = round(parking_score, 2)

        options.append(
            {
                "name": name,
                "predicted_occupancy": round(predicted_occupancy, 2),
                "availability_probability": round(availability_probability, 2),
                "walking_time_min": walking_time,
                "parking_score": parking_score,
                "recommendation_label": _label_from_score(parking_score, walking_time),
            }
        )

    options.sort(
        key=lambda item: (-float(item["parking_score"]), int(item["walking_time_min"]), item["name"])
    )
    best_option = options[0]

    return {
        "parking_options": options,
        "best_parking_option": {
            "name": best_option["name"],
            "parking_score": best_option["parking_score"],
            "recommendation_label": best_option["recommendation_label"],
        },
    }

