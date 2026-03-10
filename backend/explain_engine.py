from __future__ import annotations


def _parking_probability_from_label(parking_availability: str) -> float:
    """Convert parking label to probability-like value for explanation rules."""
    normalized = str(parking_availability).strip().lower()
    return {
        "high": 0.82,
        "medium": 0.58,
        "low": 0.32,
    }.get(normalized, 0.5)


def generate_route_explanation(
    *,
    predicted_traffic_level: str,
    travel_time_min: int,
    parking_availability: str,
    departure_buffer_min: int,
    arrival_probability: float,
) -> dict:
    """
    Build rule-based human explanation for why recommendation was made.

    This is intentionally deterministic (no LLM) for hackathon reliability.
    """
    traffic = str(predicted_traffic_level).strip().lower()
    travel_time = max(1, int(travel_time_min))
    buffer_minutes = max(0, int(departure_buffer_min))
    parking_probability = _parking_probability_from_label(parking_availability)
    arrival_prob = max(0.0, min(1.0, float(arrival_probability)))

    why_this_route: list[str] = []

    if traffic == "high":
        why_this_route.append(
            "Heavy congestion is predicted near destination corridors in this arrival window."
        )
        why_this_route.append(
            "This route is selected to reduce delay impact compared with slower alternatives."
        )
    elif traffic == "medium":
        why_this_route.append(
            "Moderate congestion is expected, so the route choice balances speed and reliability."
        )
    else:
        why_this_route.append(
            "Traffic outlook is relatively smooth on this route for the selected arrival window."
        )

    if travel_time >= 45:
        why_this_route.append(
            "Longer travel duration increases uncertainty, so a safer timing strategy is applied."
        )
    else:
        why_this_route.append(
            "Travel duration is manageable, improving consistency of ETA estimates."
        )

    if buffer_minutes >= 12:
        why_this_route.append(
            "Departure buffer is sufficient to absorb typical signal and junction delays."
        )
    elif buffer_minutes >= 6:
        why_this_route.append(
            "A moderate delay buffer is included to improve on-time arrival chances."
        )
    else:
        why_this_route.append(
            "Delay buffer is tight, so small disruptions can affect punctual arrival."
        )

    if arrival_prob >= 0.85:
        why_this_route.append(
            "Leaving at the recommended time gives a strong probability of arriving on time."
        )
    elif arrival_prob >= 0.70:
        why_this_route.append(
            "Recommended departure keeps arrival probability in a practical, moderate-safe band."
        )
    else:
        why_this_route.append(
            "Current timing carries noticeable arrival risk; consider leaving a bit earlier."
        )

    if parking_probability < 0.4:
        why_this_route.append(
            "Parking availability is likely low, so arrival slack or backup parking is advisable."
        )
    elif parking_probability < 0.7:
        why_this_route.append(
            "Parking availability is moderate at the destination."
        )
    else:
        why_this_route.append(
            "Parking availability appears favorable at the destination."
        )

    if arrival_prob < 0.70:
        risk_warning = "Moderate-to-high late-arrival risk in current conditions."
    elif traffic == "high":
        risk_warning = "Moderate congestion risk near destination."
    elif parking_probability < 0.4:
        risk_warning = "Parking scarcity risk at destination."
    else:
        risk_warning = "Overall risk is manageable for the selected plan."

    return {
        "why_this_route": why_this_route,
        "risk_warning": risk_warning,
    }

