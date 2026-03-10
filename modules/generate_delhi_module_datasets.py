from __future__ import annotations

from pathlib import Path
import random

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"


DAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
WEEKDAYS = set(DAYS[:5])
DESTINATION_TYPES = ["office", "mall", "residential", "market", "station"]
AREA_TYPES = ["office", "mall", "residential", "market", "station"]


def weighted_pick(rng: random.Random, options: list[tuple]) -> str:
    """
    Pick first item from tuples using second item as weight.
    Supports tuples like (label, weight) and (label, weight, ...).
    """
    labels = [item[0] for item in options]
    weights = [float(item[1]) for item in options]
    return rng.choices(labels, weights=weights, k=1)[0]


def sample_weather(rng: random.Random) -> tuple[str, float, float]:
    weather = weighted_pick(
        rng,
        [
            ("Clear", 0.34),
            ("Clouds", 0.25),
            ("Haze", 0.12),
            ("Fog", 0.08),
            ("Rain", 0.14),
            ("Drizzle", 0.05),
            ("Thunderstorm", 0.02),
        ],
    )

    if weather == "Clear":
        temp = rng.uniform(293.0, 313.0)
        rain = 0.0
    elif weather == "Clouds":
        temp = rng.uniform(290.0, 307.0)
        rain = rng.uniform(0.0, 0.2)
    elif weather == "Haze":
        temp = rng.uniform(285.0, 301.0)
        rain = 0.0
    elif weather == "Fog":
        temp = rng.uniform(279.0, 293.0)
        rain = 0.0
    elif weather == "Rain":
        temp = rng.uniform(285.0, 302.0)
        rain = rng.uniform(0.5, 2.2)
    elif weather == "Drizzle":
        temp = rng.uniform(286.0, 301.0)
        rain = rng.uniform(0.2, 1.2)
    else:
        temp = rng.uniform(287.0, 304.0)
        rain = rng.uniform(1.0, 3.0)

    return weather, round(temp, 2), round(rain, 2)


def infer_traffic_level(
    *,
    day_of_week: str,
    hour: int,
    location_type: str,
    weather_main: str,
    rain_1h: float,
    holiday: str,
) -> str:
    score = 0
    weekend = day_of_week not in WEEKDAYS
    holiday_flag = holiday == "Yes"
    weather = weather_main.lower()

    if 7 <= hour <= 10 or 17 <= hour <= 21:
        score += 2
    elif 11 <= hour <= 16:
        score += 1

    if location_type in {"office", "station"} and day_of_week in WEEKDAYS and (
        7 <= hour <= 10 or 17 <= hour <= 20
    ):
        score += 2

    if location_type in {"mall", "market"} and (weekend or holiday_flag) and 12 <= hour <= 21:
        score += 2
    elif location_type in {"mall", "market"} and 16 <= hour <= 21:
        score += 1

    if weather in {"rain", "drizzle", "thunderstorm"}:
        score += 1
    if weather in {"fog", "haze"}:
        score += 1
    if rain_1h >= 1.0:
        score += 1

    if holiday_flag and location_type in {"market", "mall", "station"}:
        score += 1

    if score <= 2:
        return "Low"
    if score <= 5:
        return "Medium"
    return "High"


def pick_preferred_arrival_hour(
    rng: random.Random, destination_type: str, day_of_week: str
) -> int:
    weekend = day_of_week not in WEEKDAYS

    if destination_type == "office":
        return int(rng.choice([8, 8, 9, 9, 10])) if not weekend else int(rng.choice([10, 11, 12]))
    if destination_type == "station":
        return int(rng.choice([6, 7, 8, 17, 18, 19]))
    if destination_type == "market":
        return int(rng.choice([10, 11, 12, 17, 18, 19, 20]))
    if destination_type == "mall":
        return int(rng.choice([11, 12, 13, 17, 18, 19, 20, 21]))
    return int(rng.choice([7, 8, 9, 10, 17, 18, 19, 20]))


def infer_best_departure_hour(
    *,
    preferred_arrival_hour: int,
    destination_type: str,
    day_of_week: str,
    traffic_level: str,
    weather_main: str,
    holiday: str,
    rng: random.Random,
) -> int:
    offset = {"Low": 0, "Medium": 1, "High": 2}[traffic_level]
    weekend = day_of_week not in WEEKDAYS
    holiday_flag = holiday == "Yes"
    weather = weather_main.lower()

    if destination_type in {"office", "station"} and day_of_week in WEEKDAYS:
        offset += 1
    if destination_type == "mall" and (weekend or holiday_flag) and preferred_arrival_hour >= 16:
        offset += 1
    if destination_type == "market" and preferred_arrival_hour >= 17:
        offset += 1
    if destination_type == "residential" and traffic_level == "Low":
        offset = max(0, offset - 1)
    if weather in {"rain", "drizzle", "thunderstorm", "fog"}:
        offset += 1

    # Keep target simple and stable for MVP.
    offset = min(3, max(0, offset))
    jitter = rng.choice([0, 0, 0, 1])  # small realistic variation
    return max(0, preferred_arrival_hour - min(3, offset + jitter))


def generate_departure_dataset(rng: random.Random, rows: int = 8000) -> pd.DataFrame:
    records: list[dict] = []

    destination_weights = [
        ("office", 0.32),
        ("mall", 0.2),
        ("residential", 0.18),
        ("market", 0.18),
        ("station", 0.12),
    ]

    for _ in range(rows):
        day_of_week = weighted_pick(
            rng,
            [
                ("Monday", 0.16),
                ("Tuesday", 0.16),
                ("Wednesday", 0.16),
                ("Thursday", 0.16),
                ("Friday", 0.16),
                ("Saturday", 0.1),
                ("Sunday", 0.1),
            ],
        )
        destination_type = weighted_pick(rng, destination_weights)
        preferred_arrival_hour = pick_preferred_arrival_hour(rng, destination_type, day_of_week)

        weather_main, temp, rain_1h = sample_weather(rng)
        holiday = "Yes" if rng.random() < (0.06 if day_of_week in WEEKDAYS else 0.12) else "No"
        traffic_level = infer_traffic_level(
            day_of_week=day_of_week,
            hour=preferred_arrival_hour,
            location_type=destination_type,
            weather_main=weather_main,
            rain_1h=rain_1h,
            holiday=holiday,
        )
        best_departure_hour = infer_best_departure_hour(
            preferred_arrival_hour=preferred_arrival_hour,
            destination_type=destination_type,
            day_of_week=day_of_week,
            traffic_level=traffic_level,
            weather_main=weather_main,
            holiday=holiday,
            rng=rng,
        )

        records.append(
            {
                "day_of_week": day_of_week,
                "weather_main": weather_main,
                "temp": temp,
                "rain_1h": rain_1h,
                "holiday": holiday,
                "destination_type": destination_type,
                "preferred_arrival_hour": preferred_arrival_hour,
                "traffic_level": traffic_level,
                "best_departure_hour": best_departure_hour,
            }
        )

    return pd.DataFrame(records)


def infer_parking_availability(
    *,
    area_type: str,
    hour: int,
    day_of_week: str,
    holiday: str,
    traffic_level: str,
    rng: random.Random,
) -> str:
    weekend = day_of_week not in WEEKDAYS
    holiday_flag = holiday == "Yes"
    score = 1  # 0=Low, 1=Medium, 2=High

    score += {"Low": 1, "Medium": 0, "High": -1}[traffic_level]

    if area_type in {"office", "market", "station", "mall"} and traffic_level == "High":
        score -= 1

    if area_type == "office":
        if day_of_week in WEEKDAYS and not holiday_flag and (8 <= hour <= 11 or 16 <= hour <= 20):
            score -= 1
        if weekend or holiday_flag:
            score += 1
    elif area_type == "mall":
        if (weekend or holiday_flag) and 12 <= hour <= 22:
            score -= 1
        if day_of_week in WEEKDAYS and 9 <= hour <= 11:
            score += 1
    elif area_type == "residential":
        if hour >= 22 or hour <= 6:
            score += 1
        if day_of_week in WEEKDAYS and 18 <= hour <= 21:
            score -= 1
    elif area_type == "market":
        if 10 <= hour <= 14 or 17 <= hour <= 21:
            score -= 1
        if weekend and 16 <= hour <= 21:
            score -= 1
    elif area_type == "station":
        if 6 <= hour <= 10 or 17 <= hour <= 21:
            score -= 1
        if hour >= 22 or hour <= 5:
            score += 1

    # Keep slight randomness so model learns robust boundaries.
    score += rng.choice([0, 0, 0, 1, -1])
    score = max(0, min(2, score))
    return {0: "Low", 1: "Medium", 2: "High"}[score]


def generate_parking_dataset(rng: random.Random, rows: int = 9000) -> pd.DataFrame:
    records: list[dict] = []

    for _ in range(rows):
        day_of_week = weighted_pick(
            rng,
            [
                ("Monday", 0.15),
                ("Tuesday", 0.15),
                ("Wednesday", 0.15),
                ("Thursday", 0.15),
                ("Friday", 0.15),
                ("Saturday", 0.125),
                ("Sunday", 0.125),
            ],
        )
        area_type = weighted_pick(
            rng,
            [
                ("office", 0.3),
                ("mall", 0.2),
                ("residential", 0.2),
                ("market", 0.18),
                ("station", 0.12),
            ],
        )
        hour = rng.randint(0, 23)
        holiday = "Yes" if rng.random() < (0.06 if day_of_week in WEEKDAYS else 0.14) else "No"

        weather_main, _, rain_1h = sample_weather(rng)
        traffic_level = infer_traffic_level(
            day_of_week=day_of_week,
            hour=hour,
            location_type=area_type,
            weather_main=weather_main,
            rain_1h=rain_1h,
            holiday=holiday,
        )
        parking_availability = infer_parking_availability(
            area_type=area_type,
            hour=hour,
            day_of_week=day_of_week,
            holiday=holiday,
            traffic_level=traffic_level,
            rng=rng,
        )

        records.append(
            {
                "area_type": area_type,
                "hour": hour,
                "day_of_week": day_of_week,
                "holiday": holiday,
                "traffic_level": traffic_level,
                "parking_availability": parking_availability,
            }
        )

    return pd.DataFrame(records)


def destination_area_type(destination: str) -> str:
    name = destination.lower()
    if "station" in name or "metro" in name:
        return "station"
    if "mall" in name:
        return "mall"
    if "market" in name or "chowk" in name:
        return "market"
    if "office" in name or "place" in name or "district" in name:
        return "office"
    return "residential"


def user_destination_profiles() -> dict[str, list[tuple[str, float, int]]]:
    return {
        "u1": [
            ("Nehru Place Office", 0.55, 8),
            ("Connaught Place", 0.25, 9),
            ("India Gate", 0.20, 18),
        ],
        "u2": [
            ("Dwarka Sector 21 Metro Station", 0.45, 8),
            ("Saket Select Citywalk Mall", 0.30, 17),
            ("Janakpuri Residential", 0.25, 19),
        ],
        "u3": [
            ("Chandni Chowk Market", 0.5, 18),
            ("Karol Bagh Market", 0.3, 17),
            ("Lajpat Nagar Market", 0.2, 16),
        ],
        "u4": [
            ("New Delhi Railway Station", 0.5, 7),
            ("Anand Vihar ISBT", 0.2, 8),
            ("Kashmere Gate Metro Station", 0.3, 18),
        ],
        "u5": [
            ("Rohini Residential", 0.35, 9),
            ("Saket Select Citywalk Mall", 0.35, 18),
            ("Connaught Place", 0.30, 11),
        ],
    }


def generate_user_behavior_dataset(rng: random.Random, rows_per_user: int = 1600) -> pd.DataFrame:
    records: list[dict] = []
    profiles = user_destination_profiles()

    for user_id, destinations in profiles.items():
        for _ in range(rows_per_user):
            day_of_week = weighted_pick(
                rng,
                [
                    ("Monday", 0.16),
                    ("Tuesday", 0.16),
                    ("Wednesday", 0.16),
                    ("Thursday", 0.16),
                    ("Friday", 0.16),
                    ("Saturday", 0.1),
                    ("Sunday", 0.1),
                ],
            )
            destination = weighted_pick(rng, destinations)
            base_usual_hour = next(base_hour for name, _w, base_hour in destinations if name == destination)

            weekend = day_of_week not in WEEKDAYS
            if weekend and base_usual_hour <= 10:
                base_usual_hour += 1

            weather_main, _temp, rain_1h = sample_weather(rng)
            area_type = destination_area_type(destination)
            holiday = "Yes" if rng.random() < (0.05 if day_of_week in WEEKDAYS else 0.12) else "No"
            traffic_level = infer_traffic_level(
                day_of_week=day_of_week,
                hour=base_usual_hour,
                location_type=area_type,
                weather_main=weather_main,
                rain_1h=rain_1h,
                holiday=holiday,
            )

            # "hour" is current contextual hour signal and can vary around habitual behavior.
            context_hour = max(0, min(23, base_usual_hour + rng.choice([-2, -1, 0, 0, 1, 2])))

            usual_departure_hour = base_usual_hour
            if traffic_level == "High":
                usual_departure_hour = max(0, usual_departure_hour - 1)
            if weather_main in {"Rain", "Fog", "Drizzle"}:
                usual_departure_hour = max(0, usual_departure_hour - 1)
            if weekend and area_type in {"mall", "market"}:
                usual_departure_hour = max(0, usual_departure_hour - 1)

            records.append(
                {
                    "user_id": user_id,
                    "day_of_week": day_of_week,
                    "weather_main": weather_main,
                    "destination": destination,
                    "hour": context_hour,
                    "traffic_level": traffic_level,
                    "usual_departure_hour": usual_departure_hour,
                }
            )

    return pd.DataFrame(records)


def save_dataset(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved {output_path.name} with {len(df)} rows")


def main() -> None:
    rng = random.Random(42)
    departure_df = generate_departure_dataset(rng=rng, rows=8000)
    parking_df = generate_parking_dataset(rng=rng, rows=9000)
    behavior_df = generate_user_behavior_dataset(rng=rng, rows_per_user=1600)

    save_dataset(departure_df, DATA_DIR / "module2" / "departure_dataset.csv")
    save_dataset(parking_df, DATA_DIR / "module3" / "parking_dataset.csv")
    save_dataset(behavior_df, DATA_DIR / "module4" / "user_behavior_dataset.csv")

    print("Delhi dataset generation complete for Module 2, 3, and 4.")


if __name__ == "__main__":
    main()
