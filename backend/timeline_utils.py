from __future__ import annotations

from typing import Any


def _normalize_traffic_level(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "high":
        return "high"
    if normalized in {"medium", "moderate"}:
        return "moderate"
    return "low"


def _color_hint(traffic_level: str) -> str:
    return {
        "low": "green",
        "moderate": "yellow",
        "high": "red",
    }.get(traffic_level, "yellow")


def _slot_value(slot: Any, key: str, default: str = "") -> str:
    if isinstance(slot, dict):
        return str(slot.get(key, default))
    return str(getattr(slot, key, default))


def build_traffic_timeline(
    *,
    next_time_slot_recommendations: list[Any],
    recommended_departure_time: str,
    target_arrival_time: str,
) -> dict:
    """
    Build frontend-friendly timeline objects from existing slot predictions.
    """
    timeline_rows = []
    seen_times: set[str] = set()

    for slot in next_time_slot_recommendations or []:
        slot_time = _slot_value(slot, "time").strip()
        if not slot_time or slot_time in seen_times:
            continue
        seen_times.add(slot_time)

        # Slot objects may carry either "traffic" or "traffic_level".
        raw_level = _slot_value(slot, "traffic", "")
        if not raw_level:
            raw_level = _slot_value(slot, "traffic_level", "")

        normalized_level = _normalize_traffic_level(raw_level)
        timeline_rows.append(
            {
                "time": slot_time,
                "traffic_level": normalized_level,
                "color_hint": _color_hint(normalized_level),
            }
        )

    return {
        "traffic_timeline": timeline_rows,
        "recommended_departure_marker": str(recommended_departure_time or "").strip(),
        "arrival_marker": str(target_arrival_time or "").strip(),
    }

