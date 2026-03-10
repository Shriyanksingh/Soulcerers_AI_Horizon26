from __future__ import annotations

import re
from typing import Any


TRAFFIC_RANK = {"Low": 0, "Medium": 1, "High": 2}
TRAFFIC_PENALTY = {"Low": 0, "Medium": 6, "High": 14}
SUPPORTED_EVENT_TYPES = {
    "traffic_spike",
    "road_block",
    "accident",
    "congestion_near_destination",
}


def _parse_traffic_level(value: str) -> str:
    normalized = str(value or "").strip().lower()
    mapping = {"low": "Low", "medium": "Medium", "high": "High"}
    if normalized not in mapping:
        return "Medium"
    return mapping[normalized]


def _bump_traffic_level(level: str, step: int) -> str:
    current_rank = TRAFFIC_RANK[_parse_traffic_level(level)]
    bumped_rank = max(0, min(2, current_rank + max(0, int(step))))
    return {0: "Low", 1: "Medium", 2: "High"}[bumped_rank]


def _route_name_to_key(route_name: str) -> str:
    name = str(route_name or "").strip()
    if name.lower() == "main route":
        return "selected_route"

    match = re.match(r"^alternate route\s+(\d+)$", name, flags=re.IGNORECASE)
    if match:
        return f"alternate_{int(match.group(1))}"

    safe = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return safe or "route"


def _normalize_affected_route(affected_route: str, selected_route_name: str) -> str:
    raw = str(affected_route or "").strip().lower()
    if not raw:
        return "selected_route"
    if raw in {"selected", "selected_route", "main", "main_route"}:
        return "selected_route"
    if raw.startswith("alternate_"):
        return raw
    if raw == str(selected_route_name or "").strip().lower():
        return "selected_route"
    return raw


def _to_route_row(route: Any) -> dict[str, Any]:
    if hasattr(route, "model_dump"):
        source = route.model_dump()
    elif hasattr(route, "dict"):
        source = route.dict()
    else:
        source = dict(route)

    return {
        "route_name": str(source.get("route_name", "Route")).strip() or "Route",
        "distance_km": float(source.get("distance_km", 1.0) or 1.0),
        "estimated_duration_min": max(1, int(source.get("estimated_duration_min", 10) or 10)),
        "traffic_level": _parse_traffic_level(str(source.get("traffic_level", "Medium"))),
    }


def _event_profile(event_type: str) -> dict[str, float]:
    # Multipliers are intentionally simple for demo simulation.
    profiles: dict[str, dict[str, float]] = {
        "traffic_spike": {"affected_multiplier": 1.0, "spillover_minutes": 1, "traffic_bump": 1},
        "road_block": {"affected_multiplier": 1.5, "spillover_minutes": 3, "traffic_bump": 2},
        "accident": {"affected_multiplier": 1.3, "spillover_minutes": 2, "traffic_bump": 2},
        "congestion_near_destination": {
            "affected_multiplier": 1.1,
            "spillover_minutes": 4,
            "traffic_bump": 1,
        },
    }
    return profiles.get(event_type, profiles["traffic_spike"])


def simulate_traffic_event(
    *,
    selected_route_summary: Any,
    alternate_route_summaries: list[Any],
    current_predicted_traffic: str,
    simulated_delay_minutes: int,
    event_type: str = "traffic_spike",
    affected_route: str = "selected_route",
) -> dict[str, Any]:
    """
    Simulate a sudden traffic event and produce updated route recommendations.

    This function is deterministic and lightweight so it stays stable in demos.
    """
    selected = _to_route_row(selected_route_summary)
    alternates = [_to_route_row(item) for item in (alternate_route_summaries or [])]
    routes = [selected, *alternates]

    event = str(event_type or "traffic_spike").strip().lower()
    if event not in SUPPORTED_EVENT_TYPES:
        raise ValueError(
            "Unsupported event_type. Use traffic_spike, road_block, accident, or "
            "congestion_near_destination."
        )

    base_delay = max(1, int(simulated_delay_minutes))
    profile = _event_profile(event)
    normalized_affected = _normalize_affected_route(affected_route, selected["route_name"])
    reference_traffic = _parse_traffic_level(current_predicted_traffic)

    updated_rows: list[dict[str, Any]] = []
    for row in routes:
        route_name = row["route_name"]
        route_key = _route_name_to_key(route_name)
        is_directly_affected = route_key == normalized_affected
        affects_all = event == "congestion_near_destination"

        added_delay = 0
        traffic_bump = 0
        if is_directly_affected:
            added_delay = max(1, int(round(base_delay * profile["affected_multiplier"])))
            traffic_bump = int(profile["traffic_bump"])
        elif affects_all:
            # Near-destination congestion impacts all candidates, but less than affected route.
            added_delay = max(1, int(round(base_delay * 0.5)))
            traffic_bump = 1
        elif profile["spillover_minutes"] > 0 and base_delay >= 8:
            # Spillover gives nearby routes slight extra delay for realism.
            added_delay = int(profile["spillover_minutes"])

        original_duration = int(row["estimated_duration_min"])
        updated_duration = original_duration + added_delay
        baseline_traffic = row["traffic_level"] or reference_traffic
        updated_traffic = _bump_traffic_level(baseline_traffic, traffic_bump)

        simulated_cost = updated_duration + TRAFFIC_PENALTY[updated_traffic]
        updated_rows.append(
            {
                "route_name": route_name,
                "route_key": route_key,
                "distance_km": round(float(row["distance_km"]), 2),
                "original_duration_min": original_duration,
                "updated_duration_min": updated_duration,
                "added_delay_minutes": added_delay,
                "original_traffic": baseline_traffic,
                "updated_traffic": updated_traffic,
                "simulated_cost": simulated_cost,
                "is_now_best": False,
            }
        )

    ranked = sorted(
        updated_rows,
        key=lambda item: (float(item["simulated_cost"]), float(item["distance_km"]), item["route_name"]),
    )
    best = ranked[0]
    for item in updated_rows:
        item["is_now_best"] = item["route_name"] == best["route_name"]

    reroute_recommendation = best["route_key"]
    if reroute_recommendation == "selected_route":
        simulation_summary = (
            f"{event.replace('_', ' ').title()} simulated. Selected route remains safest."
        )
    else:
        simulation_summary = (
            f"{event.replace('_', ' ').title()} detected on {normalized_affected}. "
            f"{best['route_name']} is now safer."
        )

    return {
        "event_type": event,
        "affected_route": normalized_affected,
        "added_delay_minutes": base_delay,
        "updated_routes": updated_rows,
        "reroute_recommendation": reroute_recommendation,
        "simulation_summary": simulation_summary,
        "best_route_name": best["route_name"],
    }

