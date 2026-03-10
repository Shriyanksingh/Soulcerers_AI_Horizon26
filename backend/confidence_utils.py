from __future__ import annotations


def calculate_traffic_confidence(
    *,
    predicted_traffic_level: str,
    weather_main: str,
    rain_1h: float,
) -> float:
    """
    Heuristic confidence for traffic prediction.

    Why heuristic:
    - FastAPI endpoint should stay dependency-light for hackathon demo.
    - Gives judges interpretable confidence signal without retraining.
    """
    normalized_level = str(predicted_traffic_level).strip().lower()
    normalized_weather = str(weather_main or "Clear").strip().lower()
    rain_value = max(0.0, float(rain_1h or 0.0))

    base = {
        "low": 0.82,
        "medium": 0.72,
        "high": 0.62,
    }.get(normalized_level, 0.65)

    if normalized_weather in {"thunderstorm", "rain", "drizzle", "fog", "mist", "haze"}:
        base -= 0.07
    if rain_value >= 2.0:
        base -= 0.05
    elif rain_value >= 0.5:
        base -= 0.03

    return round(max(0.40, min(0.95, base)), 2)


def calculate_parking_confidence(
    *,
    parking_availability: str,
    destination_type: str,
    traffic_level: str,
) -> float:
    """
    Heuristic confidence for parking prediction.

    Inputs emulate coverage/variance logic in a simple form:
    - availability class certainty
    - destination type volatility
    - traffic pressure
    """
    availability = str(parking_availability).strip().lower()
    dest = str(destination_type or "").strip().lower()
    traffic = str(traffic_level or "").strip().lower()

    base = {
        "high": 0.78,
        "medium": 0.71,
        "low": 0.67,
    }.get(availability, 0.68)

    if dest in {"market", "station", "mall"}:
        base -= 0.04
    if traffic == "high":
        base -= 0.04
    elif traffic == "low":
        base += 0.02

    return round(max(0.40, min(0.92, base)), 2)

