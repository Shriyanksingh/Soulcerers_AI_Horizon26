from __future__ import annotations

from typing import Any


# Lower congestion is better for route quality.
# We convert traffic labels to numeric "cost" values for normalization.
TRAFFIC_COST = {
    "Low": 1.0,
    "Medium": 2.0,
    "High": 3.0,
}

# Hackathon-safe placeholder until a real personalized route preference score is added.
DEFAULT_PERSONALIZATION_SCORE = 0.7


def _clamp_01(value: float) -> float:
    """Clamp a value into [0, 1] range."""
    return max(0.0, min(1.0, value))


def _normalize_values(values: list[float], *, lower_is_better: bool) -> list[float]:
    """
    Normalize values to [0, 1].

    Why normalization:
    - Traffic and travel-time are measured on different scales.
    - Normalization makes weighted combination mathematically stable.
    - lower_is_better=True inverts costs so better routes always get higher scores.
    """
    if not values:
        return []

    min_value = min(values)
    max_value = max(values)
    if max_value == min_value:
        # If all values are equal, give all routes the same strong component score.
        return [1.0 for _ in values]

    normalized: list[float] = []
    spread = max_value - min_value
    for value in values:
        scaled = (value - min_value) / spread
        if lower_is_better:
            scaled = 1.0 - scaled
        normalized.append(_clamp_01(scaled))
    return normalized


def calculate_weighted_route_scores(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Calculate weighted decision score for each route.

    Expected per-route input keys:
    - route_name
    - predicted_traffic
    - travel_time_min
    - parking_probability (0..1)
    - personalization_score (0..1), optional

    Weighted formula:
      final_score =
          traffic_score * 0.4 +
          time_score * 0.3 +
          parking_score * 0.2 +
          personalization_score * 0.1
    """
    if not routes:
        return []

    traffic_costs: list[float] = []
    travel_times: list[float] = []
    parking_scores: list[float] = []
    personalization_scores: list[float] = []

    for route in routes:
        traffic_label = str(route.get("predicted_traffic", "Medium")).strip().title()
        traffic_costs.append(TRAFFIC_COST.get(traffic_label, TRAFFIC_COST["Medium"]))

        travel_time = float(route.get("travel_time_min", 0.0))
        travel_times.append(max(0.0, travel_time))

        parking_probability = float(route.get("parking_probability", 0.5))
        parking_scores.append(_clamp_01(parking_probability))

        personalization_value = float(
            route.get("personalization_score", DEFAULT_PERSONALIZATION_SCORE)
        )
        personalization_scores.append(_clamp_01(personalization_value))

    traffic_component = _normalize_values(traffic_costs, lower_is_better=True)
    time_component = _normalize_values(travel_times, lower_is_better=True)

    scored_routes: list[dict[str, Any]] = []
    for index, route in enumerate(routes):
        final_score = (
            traffic_component[index] * 0.4
            + time_component[index] * 0.3
            + parking_scores[index] * 0.2
            + personalization_scores[index] * 0.1
        )

        enriched = dict(route)
        enriched["traffic_score"] = round(traffic_component[index], 4)
        enriched["time_score"] = round(time_component[index], 4)
        enriched["parking_score"] = round(parking_scores[index], 4)
        enriched["personalization_score"] = round(personalization_scores[index], 4)
        enriched["decision_score"] = round(final_score, 4)
        scored_routes.append(enriched)

    return scored_routes


def select_best_and_backup(
    scored_routes: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    """
    Select best and backup routes from pre-scored routes.

    Ranking strategy:
    1) Higher decision_score wins.
    2) If tied, lower travel_time_min wins.
    3) Distance is considered only when all routes have the same score.
    4) Final deterministic tie-break by route_name.
    """
    score_values = {
        round(float(route.get("decision_score", 0.0)), 4) for route in scored_routes
    }
    all_scores_same = len(score_values) == 1

    if all_scores_same:
        # User-requested behavior:
        # only when every route score is equal, pick shorter-distance route first.
        ranked_routes = sorted(
            scored_routes,
            key=lambda route: (
                float(route.get("distance_km", 0.0)),
                float(route.get("travel_time_min", 0.0)),
                str(route.get("route_name", "")),
            ),
        )
    else:
        ranked_routes = sorted(
            scored_routes,
            key=lambda route: (
                -float(route.get("decision_score", 0.0)),
                float(route.get("travel_time_min", 0.0)),
                str(route.get("route_name", "")),
            ),
        )

    best_route = ranked_routes[0] if ranked_routes else None
    backup_route = ranked_routes[1] if len(ranked_routes) > 1 else None
    return best_route, backup_route, ranked_routes
