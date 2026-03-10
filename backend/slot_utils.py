from datetime import datetime, timedelta


def generate_departure_slots(
    start_hour: int, end_hour: int, interval_minutes: int = 15
) -> list[dict]:
    """
    Generate departure slots between start_hour and end_hour (inclusive)
    at fixed minute intervals.

    Returns a list of dicts with:
    - display_time: "HH:MM" (for UI/display)
    - hour: int (for ML prediction feature)
    - minute: int (display/supporting info)
    """
    if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23):
        raise ValueError("start_hour and end_hour must be between 0 and 23.")
    if end_hour < start_hour:
        raise ValueError("end_hour must be greater than or equal to start_hour.")
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be greater than 0.")

    start_time = datetime(2000, 1, 1, start_hour, 0)
    end_time = datetime(2000, 1, 1, end_hour, 0)

    slots: list[dict] = []
    current = start_time
    while current <= end_time:
        slots.append(
            {
                "display_time": current.strftime("%H:%M"),
                "hour": current.hour,  # Use this for ML prediction input
                "minute": current.minute,  # Keep minute for display
            }
        )
        current += timedelta(minutes=interval_minutes)

    return slots


def choose_best_departure_slot(predicted_slots: list[dict]) -> dict:
    """
    Pick the best slot from predicted traffic slots.

    Expected slot format:
    {"time": "HH:MM", "traffic": "Low|Medium|High"}
    """
    if not predicted_slots:
        raise ValueError("predicted_slots cannot be empty.")

    traffic_priority = {"Low": 0, "Medium": 1, "High": 2}
    ranked_slots: list[tuple[int, datetime, str]] = []

    for slot in predicted_slots:
        if "time" not in slot or "traffic" not in slot:
            raise ValueError("Each slot must include 'time' and 'traffic'.")

        time_str = str(slot["time"])
        traffic_level = str(slot["traffic"])

        if traffic_level not in traffic_priority:
            raise ValueError(
                "Invalid traffic value. Allowed values: Low, Medium, High."
            )

        try:
            slot_time = datetime.strptime(time_str, "%H:%M")
        except ValueError as exc:
            raise ValueError("Time must be in HH:MM format.") from exc

        ranked_slots.append((traffic_priority[traffic_level], slot_time, traffic_level))

    # Sort by traffic rank first, then by time (earliest wins on ties).
    _, best_time, best_traffic = min(ranked_slots, key=lambda item: (item[0], item[1]))

    return {
        "best_time": best_time.strftime("%H:%M"),
        "best_traffic_level": best_traffic,
    }


if __name__ == "__main__":
    # Example: start_hour=7, end_hour=9
    example_slots = generate_departure_slots(7, 9)
    print([slot["display_time"] for slot in example_slots])

    # Example: choose best slot from model predictions
    predicted_example = [
        {"time": "07:00", "traffic": "Medium"},
        {"time": "07:15", "traffic": "Low"},
        {"time": "07:30", "traffic": "Low"},
        {"time": "07:45", "traffic": "High"},
    ]
    print(choose_best_departure_slot(predicted_example))
