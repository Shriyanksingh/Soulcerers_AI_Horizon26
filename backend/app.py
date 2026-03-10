from pathlib import Path
from datetime import datetime, timedelta
from math import atan2, cos, radians, sin, sqrt
from typing import Optional
import csv
import threading

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
try:
    from .slot_utils import choose_best_departure_slot, generate_departure_slots
except ImportError:
    # Fallback for direct execution contexts.
    from slot_utils import choose_best_departure_slot, generate_departure_slots
try:
    from .probability_utils import calculate_arrival_probability
except ImportError:
    from probability_utils import calculate_arrival_probability
try:
    from .confidence_utils import calculate_parking_confidence, calculate_traffic_confidence
except ImportError:
    from confidence_utils import calculate_parking_confidence, calculate_traffic_confidence
try:
    from .explain_engine import generate_route_explanation
except ImportError:
    from explain_engine import generate_route_explanation
try:
    from .decision_engine import calculate_weighted_route_scores, select_best_and_backup
except ImportError:
    # Fallback for direct execution contexts.
    from decision_engine import calculate_weighted_route_scores, select_best_and_backup
try:
    from .parking_intelligence import generate_parking_options
except ImportError:
    from parking_intelligence import generate_parking_options
try:
    from .timeline_utils import build_traffic_timeline
except ImportError:
    from timeline_utils import build_traffic_timeline
try:
    from .simulation_engine import simulate_traffic_event
except ImportError:
    from simulation_engine import simulate_traffic_event


# Create the FastAPI application
app = FastAPI(title="Traffic Prediction API", version="1.0.0")

# Enable CORS for local React development.
# This allows the frontend at port 5173 to call backend APIs.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent


def load_model_if_present(path_candidates: list[Path]) -> object | None:
    """Load first available model path and return None on any load failure."""
    for candidate in path_candidates:
        if candidate.exists():
            try:
                return joblib.load(candidate)
            except Exception:
                continue
    return None


# Load the trained traffic model(s) once when the app starts.
MODEL_PATHS = [
    PROJECT_ROOT / "models" / "module1" / "traffic_model.pkl",
    PROJECT_ROOT / "traffic_model.pkl",
]
model = load_model_if_present(MODEL_PATHS)

# Optional Delhi-specific traffic model (Module 1 upgrade).
DELHI_TRAFFIC_MODEL_PATHS = [
    PROJECT_ROOT / "models" / "module1" / "traffic_model_delhi.pkl",
    PROJECT_ROOT / "traffic_model_delhi.pkl",
]
delhi_traffic_model = load_model_if_present(DELHI_TRAFFIC_MODEL_PATHS)

if model is None and delhi_traffic_model is None:
    raise FileNotFoundError(
        "No usable traffic model found. Expected at least one of "
        "'traffic_model_delhi.pkl' or 'traffic_model.pkl'."
    )

# Module 3 model path (parking availability classifier)
PARKING_MODEL_PATHS = [
    PROJECT_ROOT / "models" / "module3" / "parking_model.pkl",
    PROJECT_ROOT / "parking_model.pkl",
]
parking_model = load_model_if_present(PARKING_MODEL_PATHS)

# Module 2 model path (best departure hour regressor)
DEPARTURE_MODEL_PATHS = [
    PROJECT_ROOT / "models" / "module2" / "departure_model.pkl",
    PROJECT_ROOT / "departure_model.pkl",
]
departure_model = load_model_if_present(DEPARTURE_MODEL_PATHS)

# Module 4 model path (user behavior regressor)
USER_BEHAVIOR_MODEL_PATHS = [
    PROJECT_ROOT / "models" / "module4" / "user_behavior_model.pkl",
    PROJECT_ROOT / "user_behavior_model.pkl",
]
user_behavior_model = load_model_if_present(USER_BEHAVIOR_MODEL_PATHS)

# Local storage file for module 4 trip history.
TRIP_HISTORY_FILE = PROJECT_ROOT / "data" / "module4" / "trip_history.csv"
if not TRIP_HISTORY_FILE.exists():
    legacy_trip_history = PROJECT_ROOT / "trip_history.csv"
    if legacy_trip_history.exists():
        TRIP_HISTORY_FILE = legacy_trip_history
TRIP_HISTORY_COLUMNS = [
    "user_id",
    "source",
    "destination",
    "day_of_week",
    "departure_hour",
    "weather_main",
    "traffic_level",
    "recommended_departure_time",
    "timestamp",
]
TRIP_HISTORY_LOCK = threading.Lock()


# Mapping for day names/short names to numeric weekday values
# Monday=0 ... Sunday=6 (same as pandas .dt.dayofweek used in training)
DAY_NAME_TO_INT = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}
DAY_INDEX_TO_NAME = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}

# Ranking rule for module 2: Low is best, then Medium, then High.
TRAFFIC_PRIORITY = {"Low": 0, "Medium": 1, "High": 2}
VALID_DESTINATION_TYPES = {"office", "mall", "residential", "market", "station"}


class TrafficRequest(BaseModel):
    """Request schema for traffic prediction."""

    hour: int = Field(..., ge=0, le=23, description="Hour of day (0-23)")
    day_of_week: str = Field(
        ...,
        description="Day as name or number string. Examples: Monday, mon, 0-6",
    )
    weather_main: str = Field(..., description="Main weather condition")
    temp: float = Field(..., description="Temperature value")
    rain_1h: float = Field(..., ge=0, description="Rain volume for last hour")
    holiday: str = Field(..., description="Holiday name or None")


class TrafficResponse(BaseModel):
    """Response schema for traffic prediction."""

    predicted_traffic_level: str


class BestTimeRequest(BaseModel):
    """Request schema for best departure time recommendation."""

    day_of_week: Optional[str] = Field(
        default=None,
        description="Optional day name/number. Examples: Monday, mon, 0-6",
    )
    weather_main: str = Field(..., description="Main weather condition")
    temp: float = Field(..., description="Temperature value")
    rain_1h: float = Field(..., ge=0, description="Rain volume for last hour")
    holiday: str = Field(..., description="Holiday name or None")
    destination_type: str = Field(
        default="office",
        description="Destination type (office, mall, residential, market, station)",
    )
    preferred_arrival_hour: Optional[int] = Field(
        default=None,
        ge=0,
        le=23,
        description="Preferred arrival hour (0-23).",
    )
    traffic_level: Optional[str] = Field(
        default=None,
        description="Optional traffic level: Low, Medium, High",
    )
    current_time: Optional[str] = Field(
        default=None,
        description="Optional current time in ISO format. Example: 2026-03-10T08:07:00",
    )
    horizon_minutes: int = Field(
        default=120,
        ge=15,
        description="How far in future to evaluate (minutes).",
    )


class SlotPrediction(BaseModel):
    """One evaluated departure slot and its predicted traffic."""

    departure_time: str
    predicted_traffic_level: str


class BestTimeResponse(BaseModel):
    """Response schema for best departure time recommendation."""

    recommended_departure_time: str
    recommended_traffic_level: str
    evaluated_slots: list[SlotPrediction]
    rule: str


class MultiSlotRequest(BaseModel):
    """Request schema for predicting traffic over multiple 15-minute slots."""

    start_hour: int = Field(..., ge=0, le=23, description="Start hour (0-23)")
    end_hour: int = Field(..., ge=0, le=23, description="End hour (0-23)")
    day_of_week: str = Field(
        ...,
        description="Day as name or number string. Examples: Monday, mon, 0-6",
    )
    weather_main: str = Field(..., description="Main weather condition")
    temp: float = Field(..., description="Temperature value")
    rain_1h: float = Field(..., ge=0, description="Rain volume for last hour")
    holiday: str = Field(..., description="Holiday name or None")


class MultiSlotResponse(BaseModel):
    """Response schema for multi-slot traffic prediction."""

    slot_predictions: list[SlotPrediction]


class CheckedSlot(BaseModel):
    """One checked departure slot with model prediction."""

    time: str
    traffic: str


class RecommendDepartureResponse(BaseModel):
    """Response schema for best departure recommendation endpoint."""

    recommended_departure_time: str
    predicted_traffic_level: str
    checked_slots: list[CheckedSlot]


class ParkingPredictRequest(BaseModel):
    """Request schema for module 3 parking prediction."""

    area_type: str = Field(..., description="Area type (office, mall, residential, market, station)")
    hour: int = Field(..., ge=0, le=23, description="Hour of day (0-23)")
    day_of_week: str = Field(
        ...,
        description="Day as name or number string. Examples: Monday, mon, 0-6",
    )
    holiday: str = Field(..., description="Holiday flag. Example: Yes or No")
    traffic_level: str = Field(..., description="Predicted traffic level: Low, Medium, High")


class ParkingPredictResponse(BaseModel):
    """Response schema for module 3 parking prediction."""

    parking_availability: str
    suggestion: str


class LogTripRequest(BaseModel):
    """Request schema for module 4 trip history logging."""

    user_id: str = Field(..., min_length=1, description="Unique user ID")
    source: str = Field(..., min_length=1, description="Trip start location")
    destination: str = Field(..., min_length=1, description="Trip end location")
    day_of_week: str = Field(
        ...,
        description="Day as name or number string. Examples: Monday, mon, 0-6",
    )
    departure_hour: int = Field(..., ge=0, le=23, description="Departure hour (0-23)")
    weather_main: str = Field(..., min_length=1, description="Main weather condition")
    traffic_level: str = Field(..., description="Traffic level: Low, Medium, High")
    recommended_departure_time: str = Field(
        ...,
        description="Recommended departure time in HH:MM format",
    )


class LogTripResponse(BaseModel):
    """Response schema for module 4 trip logging endpoint."""

    status: str
    message: str


class UserPatternsResponse(BaseModel):
    """Response schema for module 4 user behavior patterns."""

    most_frequent_destination: str
    usual_departure_hour: int
    most_common_day_type: str
    personalized_message: str


class UserPatternsRequest(BaseModel):
    """Request schema for module 4 user behavior patterns endpoint."""

    user_id: str = Field(..., min_length=1, description="User ID to analyze")


class PersonalizedTipRequest(BaseModel):
    """Request schema for module 4 personalized tip endpoint."""

    user_id: str = Field(..., min_length=1, description="User ID")
    destination: str = Field(..., min_length=1, description="Today's destination")
    predicted_traffic_level: str = Field(
        ...,
        description="Today's predicted traffic level: Low, Medium, High",
    )
    recommended_departure_time: str = Field(
        ...,
        description="Baseline recommended departure time in HH:MM format",
    )
    day_of_week: Optional[str] = Field(
        default=None,
        description="Optional day name/number. Examples: Monday, mon, 0-6",
    )
    weather_main: Optional[str] = Field(
        default="Clear",
        description="Optional weather condition for behavior model context",
    )


class PersonalizedTipResponse(BaseModel):
    """Response schema for module 4 personalized travel tip."""

    personalized_tip: str


class RouteSummary(BaseModel):
    """Simple route summary for map-first combined API responses."""

    route_name: str
    distance_km: float
    estimated_duration_min: int
    traffic_level: str


class DecisionRoute(BaseModel):
    """Decision-intelligence score row for one route option."""

    route_name: str
    route_type: str
    distance_km: float
    travel_time_min: int
    predicted_traffic: str
    parking_probability: float
    personalization_score: float
    traffic_score: float
    time_score: float
    parking_score: float
    decision_score: float


class RouteDecision(BaseModel):
    """Decision-intelligence payload returned by smart-route-analysis."""

    best_route: Optional[DecisionRoute]
    backup_route: Optional[DecisionRoute]
    all_routes_ranked: list[DecisionRoute]


class RouteExplanation(BaseModel):
    """Human-readable explanation block for route recommendation."""

    why_this_route: list[str]
    risk_warning: str


class ParkingOption(BaseModel):
    """One nearby parking option for destination decision support."""

    name: str
    predicted_occupancy: float
    availability_probability: float
    walking_time_min: int
    parking_score: float
    recommendation_label: str


class BestParkingOption(BaseModel):
    """Top-ranked parking option from parking intelligence."""

    name: str
    parking_score: float
    recommendation_label: str


class TrafficTimelinePoint(BaseModel):
    """Frontend-friendly timeline point for traffic visualization."""

    time: str
    traffic_level: str
    color_hint: str


class SimulationRouteUpdate(BaseModel):
    """Route update row returned by simulation endpoint."""

    route_name: str
    route_key: str
    distance_km: float
    original_duration_min: int
    updated_duration_min: int
    added_delay_minutes: int
    original_traffic: str
    updated_traffic: str
    simulated_cost: float
    is_now_best: bool


class SimulateEventRequest(BaseModel):
    """Request schema for real-time event simulation endpoint."""

    event_type: str = Field(
        default="traffic_spike",
        description="traffic_spike, road_block, accident, congestion_near_destination",
    )
    affected_route: str = Field(
        default="selected_route",
        description="selected_route or alternate_1/alternate_2...",
    )
    delay_minutes: int = Field(default=10, ge=1, le=120)
    selected_route_summary: Optional[RouteSummary] = None
    alternate_route_summaries: Optional[list[RouteSummary]] = None
    current_predicted_traffic: Optional[str] = Field(
        default="Medium",
        description="Current traffic context: Low, Medium, High",
    )


class SimulateEventResponse(BaseModel):
    """Response schema for real-time traffic simulation."""

    event_type: str
    affected_route: str
    added_delay_minutes: int
    updated_routes: list[SimulationRouteUpdate]
    reroute_recommendation: str
    simulation_summary: str
    best_route_name: str


class SmartRouteAnalysisRequest(BaseModel):
    """Request schema for map-based orchestration endpoint."""

    user_id: str = Field(..., min_length=1, description="User ID for personalization")
    start_lat: float = Field(..., ge=-90, le=90, description="Start latitude")
    start_lng: float = Field(..., ge=-180, le=180, description="Start longitude")
    end_lat: float = Field(..., ge=-90, le=90, description="Destination latitude")
    end_lng: float = Field(..., ge=-180, le=180, description="Destination longitude")
    current_time: Optional[str] = Field(
        default=None,
        description="Optional ISO datetime. Example: 2026-03-10T08:07:00",
    )
    preferred_arrival_hour: Optional[int] = Field(
        default=None,
        ge=0,
        le=23,
        description="Optional target arrival hour (0-23).",
    )
    arrival_by_time: Optional[str] = Field(
        default=None,
        description="Optional target arrival time in HH:MM format.",
    )
    start_address: Optional[str] = Field(
        default="Current Location",
        description="Optional display label for start location.",
    )
    destination_address: Optional[str] = Field(
        default="Destination",
        description="Optional display label for destination location.",
    )
    selected_route_distance_km: Optional[float] = Field(
        default=None,
        gt=0,
        description="Optional selected route distance from frontend map data.",
    )
    selected_route_duration_min: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional selected route duration (minutes) from frontend map data.",
    )
    alternate_route_distances_km: Optional[list[float]] = Field(
        default=None,
        description="Optional alternate route distances (km).",
    )
    alternate_route_durations_min: Optional[list[int]] = Field(
        default=None,
        description="Optional alternate route durations (minutes).",
    )


class SmartRouteAnalysisResponse(BaseModel):
    """Combined response schema for map-based smart route analysis."""

    selected_route_summary: RouteSummary
    alternate_route_summaries: list[RouteSummary]
    route_decision: RouteDecision
    predicted_future_traffic: str
    recommended_departure_time: str
    recommended_traffic_level: str
    target_arrival_time: str
    estimated_travel_minutes: int
    departure_buffer_minutes: int
    is_running_late: bool
    next_time_slot_recommendations: list[CheckedSlot]
    parking_availability: str
    parking_probability: float
    parking_suggestion: str
    parking_options: list[ParkingOption]
    best_parking_option: BestParkingOption
    arrival_probability: float
    arrival_probability_label: str
    traffic_confidence: float
    parking_confidence: float
    traffic_timeline: list[TrafficTimelinePoint]
    recommended_departure_marker: str
    arrival_marker: str
    explanation: RouteExplanation
    personalized_tip: str
    destination_type: str
    weather_main: str


def parse_day_of_week(day_value: str) -> int:
    """Convert input day string to integer weekday value expected by model."""
    normalized = day_value.strip().lower()

    # Accept numeric strings like "0", "1", ..., "6"
    if normalized.isdigit():
        day_number = int(normalized)
        if 0 <= day_number <= 6:
            return day_number

    # Accept textual day names like "Monday" or "mon"
    if normalized in DAY_NAME_TO_INT:
        return DAY_NAME_TO_INT[normalized]

    raise ValueError(
        "Invalid day_of_week. Use Monday-Sunday (or short names) or a number string 0-6."
    )


def normalize_holiday(value: str) -> Optional[str]:
    """Map common 'no holiday' values to None so it matches training behavior."""
    normalized = value.strip().lower()
    if normalized in {"", "none", "null", "na", "nan"}:
        return None
    return value


def build_feature_row(
    *,
    hour: int,
    day_of_week: int,
    weather_main: str,
    temp: float,
    rain_1h: float,
    holiday: str,
) -> dict:
    """Build one model input row using the same feature schema as training."""
    return {
        "hour": hour,
        "day_of_week": day_of_week,
        "weather_main": weather_main,
        "temp": temp,
        "rain_1h": rain_1h,
        "holiday": normalize_holiday(holiday),
    }


def predict_traffic_levels(feature_rows: list[dict]) -> list[str]:
    """Run batch prediction with the trained pipeline and return traffic labels."""
    model_input = pd.DataFrame(feature_rows)
    predictions = model.predict(model_input)
    return [str(level) for level in predictions]


def validate_time_hhmm(value: str) -> str:
    """Validate HH:MM time format and return unchanged value."""
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValueError("recommended_departure_time must be in HH:MM format.") from exc
    return value


def day_value_to_type(day_value: str) -> Optional[str]:
    """Convert a day value to 'weekday' or 'weekend' using existing parser."""
    try:
        day_number = parse_day_of_week(str(day_value))
    except ValueError:
        return None
    return "weekend" if day_number >= 5 else "weekday"


def build_personalized_pattern_message(
    destination: str, departure_hour: int, day_type: str
) -> str:
    """Create a short user-facing summary from discovered patterns."""
    day_label = "weekdays" if day_type == "weekday" else "weekends"
    return (
        f"You most often travel to {destination} around {departure_hour:02d}:00 on "
        f"{day_label}. We will prioritize similar departure suggestions."
    )


def load_trip_history_dataframe() -> pd.DataFrame:
    """Load trip history CSV with basic file checks."""
    if not TRIP_HISTORY_FILE.exists():
        raise ValueError("No trip history found yet. Please log trips first.")

    try:
        history_df = pd.read_csv(TRIP_HISTORY_FILE)
    except Exception as exc:
        raise ValueError("Failed to read trip history.") from exc

    if history_df.empty:
        raise ValueError("No trip history found yet. Please log trips first.")
    return history_df


def normalize_traffic_from_history(value: str) -> Optional[str]:
    """Safely normalize traffic values from historical rows."""
    try:
        return parse_traffic_level(str(value))
    except ValueError:
        return None


def shift_time_by_minutes(time_value: str, minutes_delta: int) -> str:
    """Shift HH:MM time by given minutes and return HH:MM."""
    parsed_time = datetime.strptime(time_value, "%H:%M")
    shifted = parsed_time + timedelta(minutes=minutes_delta)
    return shifted.strftime("%H:%M")


def format_hour_label(hour_value: int) -> str:
    """Format integer hour as simple human-friendly label (e.g., 8 AM)."""
    return datetime(2000, 1, 1, hour_value, 0).strftime("%I %p").lstrip("0")


def parse_traffic_level(value: str) -> str:
    """Normalize and validate traffic level text."""
    normalized = value.strip().lower()
    mapping = {"low": "Low", "medium": "Medium", "high": "High"}
    if normalized not in mapping:
        raise ValueError("Invalid traffic_level. Use Low, Medium, or High.")
    return mapping[normalized]


def normalize_delhi_traffic_level(value: str) -> str:
    """Normalize Delhi dataset traffic labels to Low/Medium/High."""
    normalized = str(value).strip().lower()
    if normalized in {"low"}:
        return "Low"
    if normalized in {"medium"}:
        return "Medium"
    if normalized in {"high", "very high", "severe"}:
        return "High"
    raise ValueError("Invalid Delhi traffic label.")


def delhi_day_type_from_index(day_index: int) -> str:
    """Convert weekday index to Delhi dataset day type."""
    return "Weekend" if day_index >= 5 else "Weekday"


def delhi_time_of_day_from_hour(hour: int) -> str:
    """Map hour to Delhi dataset time buckets."""
    if 7 <= hour <= 10:
        return "Morning Peak"
    if 17 <= hour <= 21:
        return "Evening Peak"
    if 11 <= hour <= 16:
        return "Afternoon"
    return "Night"


def map_weather_to_delhi_condition(weather_main: str, temp: float) -> str:
    """Map weather values to categories used in Delhi traffic training data."""
    normalized = normalize_weather_main(weather_main).strip().lower()
    if normalized in {"rain", "drizzle", "thunderstorm"}:
        return "Rain"
    if normalized in {"fog", "mist", "haze", "smoke", "clouds"}:
        return "Fog"
    if temp >= 307:
        return "Heatwave"
    return "Clear"


def normalize_area_label(address: Optional[str], fallback: str) -> str:
    """Extract a stable area token from a place/address label."""
    if not address:
        return fallback
    cleaned = str(address).strip()
    if not cleaned:
        return fallback
    # Keep only the first comma-separated location part (example: 'Dwarka').
    return cleaned.split(",")[0].strip().title() or fallback


def infer_road_type_from_distance(distance_km: float) -> str:
    """Infer road type from route length for Delhi traffic model features."""
    if distance_km >= 18:
        return "Highway"
    if distance_km >= 6:
        return "Main Road"
    return "Inner Road"


def estimate_speed_kmph_for_context(hour: int, weather_condition: str) -> float:
    """Estimate plausible speed for legacy traffic endpoint when route speed is unknown."""
    if 7 <= hour <= 10 or 17 <= hour <= 21:
        base_speed = 18.0
    elif 22 <= hour <= 23 or 0 <= hour <= 5:
        base_speed = 42.0
    else:
        base_speed = 30.0

    if weather_condition == "Rain":
        base_speed -= 7.0
    elif weather_condition == "Fog":
        base_speed -= 5.0
    elif weather_condition == "Heatwave":
        base_speed -= 2.0

    return max(8.0, min(70.0, base_speed))


def build_delhi_traffic_feature_row(
    *,
    start_area: str,
    end_area: str,
    distance_km: float,
    hour: int,
    day_index: int,
    weather_main: str,
    temp: float,
    avg_speed_kmph: float,
) -> dict:
    """Build one feature row using Delhi traffic model schema."""
    weather_condition = map_weather_to_delhi_condition(weather_main, temp=temp)
    return {
        "start_area": start_area,
        "end_area": end_area,
        "distance_km": round(max(0.1, float(distance_km)), 3),
        "time_of_day": delhi_time_of_day_from_hour(int(hour)),
        "day_of_week": delhi_day_type_from_index(int(day_index)),
        "weather_condition": weather_condition,
        "road_type": infer_road_type_from_distance(float(distance_km)),
        "average_speed_kmph": round(max(5.0, float(avg_speed_kmph)), 2),
    }


def predict_traffic_levels_delhi(feature_rows: list[dict]) -> list[str]:
    """Run batch prediction with Delhi traffic model and normalize labels."""
    if delhi_traffic_model is None:
        raise ValueError("Delhi traffic model is not available.")
    model_input = pd.DataFrame(feature_rows)
    predictions = delhi_traffic_model.predict(model_input)
    return [normalize_delhi_traffic_level(str(level)) for level in predictions]


def predict_route_traffic_level(
    *,
    start_address: Optional[str],
    destination_address: Optional[str],
    distance_km: float,
    duration_min: int,
    hour: int,
    day_index: int,
    weather_main: str,
    temp: float,
) -> str:
    """
    Predict route traffic level.
    Prefer Delhi model when available; otherwise fallback to legacy traffic model.
    """
    if delhi_traffic_model is not None:
        avg_speed_kmph = max(5.0, distance_km / max(0.1, duration_min / 60))
        row = build_delhi_traffic_feature_row(
            start_area=normalize_area_label(start_address, "Delhi Start"),
            end_area=normalize_area_label(destination_address, "Delhi Destination"),
            distance_km=distance_km,
            hour=hour,
            day_index=day_index,
            weather_main=weather_main,
            temp=temp,
            avg_speed_kmph=avg_speed_kmph,
        )
        return parse_traffic_level(predict_traffic_levels_delhi([row])[0])

    legacy_row = build_feature_row(
        hour=hour,
        day_of_week=day_index,
        weather_main=weather_main,
        temp=temp,
        rain_1h=0.0,
        holiday="None",
    )
    return parse_traffic_level(predict_traffic_levels([legacy_row])[0])


def is_holiday_flag(value: str) -> bool:
    """Convert common holiday inputs to a boolean flag."""
    normalized = value.strip().lower()
    return normalized in {"yes", "y", "true", "1", "holiday"}


def normalize_holiday_text(value: str) -> str:
    """Normalize holiday input to the labels used during parking model training."""
    return "Yes" if is_holiday_flag(value) else "No"


def predict_parking_availability_ml(
    *,
    area_type: str,
    hour: int,
    day_of_week: str,
    holiday: str,
    traffic_level: str,
) -> str:
    """
    Predict parking availability with the trained Module 3 model.
    Falls back to rule logic if model is unavailable.
    """
    day_index = parse_day_of_week(day_of_week)
    day_name = DAY_INDEX_TO_NAME[day_index]
    normalized_traffic = parse_traffic_level(traffic_level)
    normalized_holiday = normalize_holiday_text(holiday)

    model_input = pd.DataFrame(
        [
            {
                "area_type": area_type.strip().lower(),
                "hour": hour,
                "day_of_week": day_name,
                "holiday": normalized_holiday,
                "traffic_level": normalized_traffic,
            }
        ]
    )

    if parking_model is None:
        # Safe fallback: keep endpoint working if model file is missing.
        return predict_parking_availability_rule(
            area_type=area_type,
            hour=hour,
            day_of_week=day_of_week,
            holiday=holiday,
            traffic_level=normalized_traffic,
        )

    prediction = parking_model.predict(model_input)[0]
    return str(prediction)


def normalize_destination_type(value: str) -> str:
    """Validate and normalize destination type for Module 2."""
    normalized = value.strip().lower()
    if normalized not in VALID_DESTINATION_TYPES:
        allowed = ", ".join(sorted(VALID_DESTINATION_TYPES))
        raise ValueError(f"Invalid destination_type. Use one of: {allowed}.")
    return normalized


def resolve_day_context(
    day_of_week: Optional[str], current_time: Optional[str]
) -> tuple[str, int]:
    """Resolve day name/index either from request day or from current time."""
    if day_of_week is not None:
        day_index = parse_day_of_week(day_of_week)
    else:
        day_index = parse_current_time(current_time).weekday()
    return DAY_INDEX_TO_NAME[day_index], day_index


def resolve_preferred_arrival_hour(
    preferred_arrival_hour: Optional[int], current_time: Optional[str]
) -> int:
    """
    Resolve preferred arrival hour.
    Fallback for older clients: use next hour from current time.
    """
    if preferred_arrival_hour is not None:
        return preferred_arrival_hour

    base_dt = parse_current_time(current_time)
    return min(23, base_dt.hour + 1)


def resolve_departure_traffic_level(
    traffic_level: Optional[str],
    *,
    day_index: int,
    preferred_arrival_hour: int,
    weather_main: str,
    temp: float,
    rain_1h: float,
    holiday: str,
) -> str:
    """
    Resolve traffic level for Module 2.
    Use request value when provided; otherwise infer from the traffic model.
    """
    if traffic_level is not None:
        return parse_traffic_level(traffic_level)

    if delhi_traffic_model is not None:
        weather_condition = map_weather_to_delhi_condition(weather_main, temp=temp)
        estimated_speed = estimate_speed_kmph_for_context(
            hour=preferred_arrival_hour,
            weather_condition=weather_condition,
        )
        delhi_row = build_delhi_traffic_feature_row(
            start_area="Delhi Start",
            end_area="Delhi Destination",
            distance_km=8.0,
            hour=preferred_arrival_hour,
            day_index=day_index,
            weather_main=weather_main,
            temp=temp,
            avg_speed_kmph=estimated_speed,
        )
        predicted_level = predict_traffic_levels_delhi([delhi_row])[0]
    else:
        row = build_feature_row(
            hour=preferred_arrival_hour,
            day_of_week=day_index,
            weather_main=weather_main,
            temp=temp,
            rain_1h=rain_1h,
            holiday=holiday,
        )
        predicted_level = predict_traffic_levels([row])[0]
    return parse_traffic_level(predicted_level)


def predict_best_departure_hour_ml(
    *,
    day_name: str,
    weather_main: str,
    temp: float,
    rain_1h: float,
    holiday: str,
    destination_type: str,
    preferred_arrival_hour: int,
    traffic_level: str,
) -> int:
    """
    Predict best departure hour for Module 2 using trained model.
    """
    normalized_holiday = normalize_holiday_text(holiday)
    normalized_destination = normalize_destination_type(destination_type)
    normalized_traffic = parse_traffic_level(traffic_level)

    model_input = pd.DataFrame(
        [
            {
                "day_of_week": day_name,
                "weather_main": weather_main.strip(),
                "temp": temp,
                "rain_1h": rain_1h,
                "holiday": normalized_holiday,
                "destination_type": normalized_destination,
                "preferred_arrival_hour": preferred_arrival_hour,
                "traffic_level": normalized_traffic,
            }
        ]
    )

    if departure_model is None:
        # Fallback heuristic to keep endpoint working if model is unavailable.
        offset = {"Low": 0, "Medium": 1, "High": 2}[normalized_traffic]
        if normalized_destination in {"office", "station", "market"}:
            offset += 1
        predicted_hour = preferred_arrival_hour - min(3, offset)
    else:
        raw_prediction = departure_model.predict(model_input)[0]
        predicted_hour = int(round(float(raw_prediction)))

    # Keep recommendations realistic: do not suggest later than arrival,
    # and avoid suggesting more than 3 hours early in this MVP.
    min_allowed_hour = max(0, preferred_arrival_hour - 3)
    max_allowed_hour = preferred_arrival_hour
    predicted_hour = max(min_allowed_hour, min(max_allowed_hour, predicted_hour))
    return predicted_hour


def normalize_weather_main(value: Optional[str]) -> str:
    """Normalize weather text with a safe fallback."""
    if value is None:
        return "Clear"
    cleaned = value.strip()
    return cleaned if cleaned else "Clear"


def predict_usual_departure_hour_ml(
    *,
    user_id: str,
    day_name: str,
    weather_main: str,
    destination: str,
    hour: int,
    traffic_level: str,
) -> int:
    """
    Predict user's usual departure hour from the trained Module 4 model.
    Falls back to history pattern when model is unavailable.
    """
    normalized_traffic = parse_traffic_level(traffic_level)
    normalized_user_id = user_id.strip().lower()
    destination_clean = canonicalize_destination_for_behavior(destination)
    weather_clean = normalize_weather_main(weather_main).strip().title()
    destination_tokens = destination_match_tokens(destination)

    # First preference: destination-specific user history (if available).
    user_history: Optional[pd.DataFrame] = None
    try:
        history_df = load_trip_history_dataframe()
        user_history = history_df[
            history_df["user_id"].astype(str).str.strip().str.lower() == normalized_user_id
        ].copy()
        if not user_history.empty:
            destination_mask = user_history["destination"].astype(str).apply(
                lambda value: destination_matches_query(value, destination_tokens)
            )
            destination_history = user_history[destination_mask].copy()
            departure_hours = pd.to_numeric(
                destination_history["departure_hour"], errors="coerce"
            ).dropna()
            if not departure_hours.empty:
                return int(departure_hours.mode().iloc[0])
    except ValueError:
        user_history = None

    model_input = pd.DataFrame(
        [
            {
                "user_id": normalized_user_id,
                "day_of_week": day_name,
                "weather_main": weather_clean,
                "destination": destination_clean,
                "hour": hour,
                "traffic_level": normalized_traffic,
            }
        ]
    )

    if user_behavior_model is not None:
        raw_prediction = user_behavior_model.predict(model_input)[0]
        predicted_hour = int(round(float(raw_prediction)))
        return max(0, min(23, predicted_hour))

    # Fallback: use overall user pattern if model is unavailable.
    if user_history is not None and not user_history.empty:
        departure_hours = pd.to_numeric(user_history["departure_hour"], errors="coerce").dropna()
        if not departure_hours.empty:
            return int(departure_hours.mode().iloc[0])

    # Final fallback: use provided contextual hour.
    return max(0, min(23, int(hour)))


def haversine_distance_km(
    start_lat: float, start_lng: float, end_lat: float, end_lng: float
) -> float:
    """Compute straight-line distance (km) between two coordinates."""
    earth_radius_km = 6371.0
    lat1 = radians(start_lat)
    lon1 = radians(start_lng)
    lat2 = radians(end_lat)
    lon2 = radians(end_lng)

    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    a = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return max(0.1, earth_radius_km * c)


def estimate_duration_minutes(distance_km: float, traffic_level: str) -> int:
    """Estimate travel duration from distance and traffic level."""
    speeds_kmph = {"Low": 42.0, "Medium": 32.0, "High": 24.0}
    normalized_traffic = parse_traffic_level(traffic_level)
    speed = speeds_kmph[normalized_traffic]
    minutes = int(round((distance_km / speed) * 60))
    return max(5, minutes)


def estimate_route_traffic_from_delay(
    reference_duration_min: int,
    candidate_duration_min: int,
    fallback_level: str,
) -> str:
    """Infer route-level traffic category using relative delay."""
    baseline = max(1, reference_duration_min)
    ratio = candidate_duration_min / baseline

    if ratio <= 1.05:
        return "Low" if fallback_level == "Low" else "Medium"
    if ratio <= 1.20:
        return "Medium" if fallback_level != "High" else "High"
    return "High"


def derive_weather_context(current_dt: datetime) -> tuple[str, float, float]:
    """
    Derive lightweight weather context for hackathon orchestration.
    Replace with real weather API integration later if needed.
    """
    month = current_dt.month
    hour = current_dt.hour

    if month in {6, 7, 8, 9}:
        # Monsoon-like heuristic.
        if 7 <= hour <= 10 or 16 <= hour <= 20:
            return ("Rain", 300.0, 0.7)
        return ("Clouds", 301.5, 0.2)

    if month in {12, 1, 2}:
        return ("Clear", 286.0, 0.0)

    # Mild conditions for remaining months.
    return ("Clouds", 294.5, 0.1)


def infer_destination_type(day_index: int, arrival_hour: int, distance_km: float) -> str:
    """Infer destination type from simple day/time/distance heuristics."""
    is_weekend = day_index >= 5

    if not is_weekend and 7 <= arrival_hour <= 10:
        return "office"
    if is_weekend and 12 <= arrival_hour <= 21:
        return "mall"
    if 17 <= arrival_hour <= 21:
        return "market"
    if distance_km >= 25:
        return "station"
    return "residential"


def infer_destination_type_from_address(destination_address: Optional[str]) -> Optional[str]:
    """
    Infer destination type from destination label keywords.
    Returns None when no strong keyword match is found.
    """
    if not destination_address:
        return None

    text = destination_address.strip().lower()
    if not text:
        return None

    station_keywords = [
        "station",
        "railway",
        "metro",
        "isbt",
        "terminal",
        "airport",
    ]
    mall_keywords = ["mall", "citywalk", "plaza"]
    market_keywords = ["market", "bazar", "bazaar", "chowk", "mandi"]
    office_keywords = [
        "office",
        "business",
        "district centre",
        "district center",
        "place",
        "it park",
        "tech",
    ]
    residential_keywords = ["vihar", "enclave", "nagar", "colony", "sector", "residential"]

    if any(keyword in text for keyword in station_keywords):
        return "station"
    if any(keyword in text for keyword in mall_keywords):
        return "mall"
    if any(keyword in text for keyword in market_keywords):
        return "market"
    if any(keyword in text for keyword in office_keywords):
        return "office"
    if any(keyword in text for keyword in residential_keywords):
        return "residential"
    return None


BEHAVIOR_KNOWN_DESTINATIONS = {
    "Nehru Place Office",
    "Connaught Place",
    "India Gate",
    "Dwarka Sector 21 Metro Station",
    "Saket Select Citywalk Mall",
    "Janakpuri Residential",
    "Chandni Chowk Market",
    "Karol Bagh Market",
    "Lajpat Nagar Market",
    "New Delhi Railway Station",
    "Anand Vihar Isbt",
    "Kashmere Gate Metro Station",
    "Rohini Residential",
}

BEHAVIOR_DESTINATION_KEYWORD_MAP = [
    ("india gate", "India Gate"),
    ("connaught", "Connaught Place"),
    ("nehru place", "Nehru Place Office"),
    ("select citywalk", "Saket Select Citywalk Mall"),
    ("saket", "Saket Select Citywalk Mall"),
    ("chandni chowk", "Chandni Chowk Market"),
    ("karol bagh", "Karol Bagh Market"),
    ("lajpat nagar", "Lajpat Nagar Market"),
    ("new delhi railway", "New Delhi Railway Station"),
    ("railway station", "New Delhi Railway Station"),
    ("anand vihar", "Anand Vihar Isbt"),
    ("kashmere gate", "Kashmere Gate Metro Station"),
    ("dwarka sector 21", "Dwarka Sector 21 Metro Station"),
    ("rohini", "Rohini Residential"),
    ("janakpuri", "Janakpuri Residential"),
]

BEHAVIOR_TYPE_REFERENCE_DESTINATION = {
    "office": "Nehru Place Office",
    "mall": "Saket Select Citywalk Mall",
    "market": "Chandni Chowk Market",
    "station": "New Delhi Railway Station",
    "residential": "Rohini Residential",
}


def normalize_destination_token(destination: str) -> str:
    """Short destination label from first comma-separated part."""
    cleaned = str(destination).strip()
    if not cleaned:
        return ""
    return cleaned.split(",")[0].strip().title()


def canonicalize_destination_for_behavior(destination: str) -> str:
    """
    Map free-text destination to behavior-model-friendly Delhi labels.
    This avoids same prediction for every unseen full address.
    """
    short_label = normalize_destination_token(destination)
    text = str(destination).strip().lower()
    short_text = short_label.lower()
    combined = f"{text} {short_text}".strip()

    for keyword, canonical in BEHAVIOR_DESTINATION_KEYWORD_MAP:
        if keyword in combined:
            return canonical

    if short_label in BEHAVIOR_KNOWN_DESTINATIONS:
        return short_label

    inferred_type = infer_destination_type_from_address(destination)
    if inferred_type in BEHAVIOR_TYPE_REFERENCE_DESTINATION:
        return BEHAVIOR_TYPE_REFERENCE_DESTINATION[inferred_type]

    return short_label or "Connaught Place"


def destination_match_tokens(destination: str) -> set[str]:
    """Build robust tokens for fuzzy destination matching in trip history."""
    tokens: set[str] = set()
    short_label = normalize_destination_token(destination)
    raw = str(destination).strip().lower()

    if raw:
        tokens.add(raw)
    if short_label:
        tokens.add(short_label.lower())
        for part in short_label.lower().replace("-", " ").split():
            if len(part) >= 4:
                tokens.add(part)

    canonical = canonicalize_destination_for_behavior(destination).lower()
    if canonical:
        tokens.add(canonical)
        for part in canonical.replace("-", " ").split():
            if len(part) >= 4:
                tokens.add(part)

    return tokens


def destination_matches_query(history_destination: str, query_tokens: set[str]) -> bool:
    """Check if a history destination is similar to query destination tokens."""
    history_raw = str(history_destination).strip().lower()
    history_short = normalize_destination_token(str(history_destination)).lower()
    for token in query_tokens:
        if token and (token in history_raw or token in history_short):
            return True
    return False


def get_user_history_counts_for_destination(user_id: str, destination: str) -> tuple[int, int]:
    """
    Return (user_history_count, destination_history_count) from trip history CSV.
    Safely returns (0, 0) when history file is missing/unreadable.
    """
    normalized_user_id = user_id.strip().lower()
    destination_tokens = destination_match_tokens(destination)

    try:
        history_df = load_trip_history_dataframe()
    except ValueError:
        return (0, 0)

    user_history = history_df[
        history_df["user_id"].astype(str).str.strip().str.lower() == normalized_user_id
    ].copy()
    if user_history.empty:
        return (0, 0)

    destination_mask = user_history["destination"].astype(str).apply(
        lambda value: destination_matches_query(value, destination_tokens)
    )
    destination_history = user_history[destination_mask].copy()
    return (int(len(user_history)), int(len(destination_history)))


def build_route_summaries(
    *,
    predicted_future_traffic: str,
    fallback_distance_km: float,
    selected_route_distance_km: Optional[float],
    selected_route_duration_min: Optional[int],
    alternate_route_distances_km: Optional[list[float]],
    alternate_route_durations_min: Optional[list[int]],
) -> tuple[RouteSummary, list[RouteSummary]]:
    """Build selected and alternate route summaries for frontend cards."""
    normalized_traffic = parse_traffic_level(predicted_future_traffic)

    main_distance = float(selected_route_distance_km or fallback_distance_km)
    main_distance = round(max(0.1, main_distance), 2)

    if selected_route_duration_min is not None and selected_route_duration_min > 0:
        main_duration = int(selected_route_duration_min)
    else:
        main_duration = estimate_duration_minutes(main_distance, normalized_traffic)

    selected_summary = RouteSummary(
        route_name="Main Route",
        distance_km=main_distance,
        estimated_duration_min=main_duration,
        traffic_level=normalized_traffic,
    )

    alternate_summaries: list[RouteSummary] = []
    if alternate_route_distances_km and alternate_route_durations_min:
        alt_count = min(
            len(alternate_route_distances_km),
            len(alternate_route_durations_min),
        )
        for idx in range(alt_count):
            alt_distance = round(max(0.1, float(alternate_route_distances_km[idx])), 2)
            alt_duration = max(5, int(alternate_route_durations_min[idx]))
            alt_traffic = estimate_route_traffic_from_delay(
                main_duration,
                alt_duration,
                normalized_traffic,
            )
            alternate_summaries.append(
                RouteSummary(
                    route_name=f"Alternate Route {idx + 1}",
                    distance_km=alt_distance,
                    estimated_duration_min=alt_duration,
                    traffic_level=alt_traffic,
                )
            )
    else:
        # Create synthetic alternates when map route metrics are not supplied.
        fallback_variants = [(1.08, 1.10), (1.15, 1.22)]
        for idx, (distance_factor, duration_factor) in enumerate(fallback_variants):
            alt_distance = round(max(0.1, main_distance * distance_factor), 2)
            alt_duration = max(5, int(round(main_duration * duration_factor)))
            alt_traffic = estimate_route_traffic_from_delay(
                main_duration,
                alt_duration,
                normalized_traffic,
            )
            alternate_summaries.append(
                RouteSummary(
                    route_name=f"Alternate Route {idx + 1}",
                    distance_km=alt_distance,
                    estimated_duration_min=alt_duration,
                    traffic_level=alt_traffic,
                )
            )

    return selected_summary, alternate_summaries


def parking_availability_to_probability(availability: str) -> float:
    """
    Convert parking label to probability score for route decisioning.

    Higher value means parking is easier, so it should raise final decision score.
    """
    normalized = parse_traffic_level(availability)
    return {"Low": 0.3, "Medium": 0.6, "High": 0.85}[normalized]


def resolve_route_traffic_for_decision(
    *,
    route_summary: RouteSummary,
    selected_route_duration_min: int,
    selected_route_traffic: str,
) -> str:
    """
    Return route-specific traffic for decision scoring.

    Today:
    - Use route_summary.traffic_level when available.
    Fallback:
    - Approximate by duration delta against selected route.

    Future improvement hook:
    - Replace fallback with real per-route model inference for each alternative.
    """
    declared_traffic = str(route_summary.traffic_level).strip()
    if declared_traffic:
        return parse_traffic_level(declared_traffic)

    return estimate_route_traffic_from_delay(
        selected_route_duration_min,
        int(route_summary.estimated_duration_min),
        parse_traffic_level(selected_route_traffic),
    )


def calibrate_slot_traffic_level(
    *,
    predicted_level: str,
    slot_dt: datetime,
    weather_main: str,
    rain_1h: float,
    holiday: str,
) -> str:
    """
    Apply context calibration to slot-level traffic output.

    Why this exists:
    - Raw model output can be too smooth across many slots.
    - City traffic normally rises in peak commute windows.
    - This keeps model signal while preventing unrealistic all-day "Low" timelines.

    Future improvement hook:
    - Replace these floors with per-slot live signals (speed/delay/API telemetry).
    """
    normalized_predicted = parse_traffic_level(predicted_level)
    slot_hour = slot_dt.hour
    weekend = slot_dt.weekday() >= 5
    holiday_flag = is_holiday_flag(holiday)
    weather_clean = normalize_weather_main(weather_main).strip().lower()

    # Higher rank means heavier traffic.
    rank = TRAFFIC_PRIORITY[normalized_predicted]
    minimum_rank = 0

    morning_peak = 7 <= slot_hour <= 10
    evening_peak = 17 <= slot_hour <= 21
    shoulder_window = 11 <= slot_hour <= 13 or 16 <= slot_hour <= 17

    # Peak commute should rarely stay all-day low on working days.
    if not holiday_flag:
        if morning_peak or evening_peak:
            minimum_rank = max(minimum_rank, 1)
        elif not weekend and shoulder_window:
            minimum_rank = max(minimum_rank, 1)

    # Weather/rain can push traffic above baseline.
    if rain_1h >= 2.5:
        minimum_rank = max(minimum_rank, 2 if (morning_peak or evening_peak) else 1)
    elif rain_1h >= 0.8:
        minimum_rank = max(minimum_rank, 1)

    if weather_clean in {"thunderstorm"}:
        minimum_rank = max(minimum_rank, 2 if (morning_peak or evening_peak) else 1)
    elif weather_clean in {"rain", "drizzle"}:
        minimum_rank = max(minimum_rank, 1)
    elif weather_clean in {"fog", "mist", "haze", "smoke"} and (
        6 <= slot_hour <= 11 or 17 <= slot_hour <= 22
    ):
        minimum_rank = max(minimum_rank, 1)

    adjusted_rank = max(rank, minimum_rank)
    adjusted_rank = max(0, min(2, adjusted_rank))
    return {0: "Low", 1: "Medium", 2: "High"}[adjusted_rank]


def predict_next_time_slot_recommendations(
    *,
    day_index: int,
    weather_main: str,
    temp: float,
    rain_1h: float,
    holiday: str,
    current_dt: datetime,
    start_address: Optional[str] = None,
    destination_address: Optional[str] = None,
    route_distance_km: Optional[float] = None,
    route_duration_min: Optional[int] = None,
    slot_count: int = 6,
    target_end_dt: Optional[datetime] = None,
    max_slots: int = 96,
) -> list[CheckedSlot]:
    """Predict traffic for the next N upcoming 15-minute slots."""
    first_slot = ceil_to_next_interval(current_dt, interval_minutes=15)
    if target_end_dt is not None:
        end_slot = floor_to_previous_interval(target_end_dt, interval_minutes=15)
        slot_datetimes: list[datetime] = []
        pointer = first_slot
        while pointer <= end_slot and len(slot_datetimes) < max_slots:
            slot_datetimes.append(pointer)
            pointer += timedelta(minutes=15)
    else:
        slot_datetimes = [first_slot + timedelta(minutes=15 * idx) for idx in range(slot_count)]

    if not slot_datetimes:
        return []

    if (
        delhi_traffic_model is not None
        and route_distance_km is not None
        and route_duration_min is not None
    ):
        base_speed = max(5.0, route_distance_km / max(0.1, route_duration_min / 60))
        delhi_rows: list[dict] = []
        for slot_dt in slot_datetimes:
            slot_day_index = slot_dt.weekday() if target_end_dt is not None else day_index
            tod = delhi_time_of_day_from_hour(slot_dt.hour)
            speed_factor = {
                "Morning Peak": 0.72,
                "Evening Peak": 0.7,
                "Afternoon": 0.9,
                "Night": 1.15,
            }[tod]
            adjusted_speed = max(5.0, min(75.0, base_speed * speed_factor))
            delhi_rows.append(
                build_delhi_traffic_feature_row(
                    start_area=normalize_area_label(start_address, "Delhi Start"),
                    end_area=normalize_area_label(destination_address, "Delhi Destination"),
                    distance_km=route_distance_km,
                    hour=slot_dt.hour,
                    day_index=slot_day_index,
                    weather_main=weather_main,
                    temp=temp,
                    avg_speed_kmph=adjusted_speed,
                )
            )
        predictions = predict_traffic_levels_delhi(delhi_rows)
    else:
        feature_rows = [
            build_feature_row(
                hour=slot_dt.hour,
                day_of_week=slot_dt.weekday() if target_end_dt is not None else day_index,
                weather_main=weather_main,
                temp=temp,
                rain_1h=rain_1h,
                holiday=holiday,
            )
            for slot_dt in slot_datetimes
        ]
        predictions = predict_traffic_levels(feature_rows)

    calibrated_slots: list[CheckedSlot] = []
    for slot_dt, predicted_level in zip(slot_datetimes, predictions):
        calibrated_level = calibrate_slot_traffic_level(
            predicted_level=str(predicted_level),
            slot_dt=slot_dt,
            weather_main=weather_main,
            rain_1h=rain_1h,
            holiday=holiday,
        )
        calibrated_slots.append(
            CheckedSlot(
                time=slot_dt.strftime("%H:%M"),
                traffic=calibrated_level,
            )
        )
    return calibrated_slots


def build_personalized_tip_text(
    *,
    user_id: str,
    destination: str,
    predicted_traffic_level: str,
    recommended_departure_time: str,
    day_of_week: Optional[str],
    weather_main: Optional[str],
) -> str:
    """Generate personalized tip using the trained behavior model."""
    today_traffic = parse_traffic_level(predicted_traffic_level)
    baseline_time = validate_time_hhmm(recommended_departure_time)
    day_name, _day_index = resolve_day_context(day_of_week, None)
    weather_clean = normalize_weather_main(weather_main)

    destination_clean = normalize_destination_token(destination) or destination.strip()
    baseline_hour = datetime.strptime(baseline_time, "%H:%M").hour
    user_history_count, destination_history_count = get_user_history_counts_for_destination(
        user_id=user_id,
        destination=destination_clean,
    )
    minimum_history_records = 3

    # If we do not have enough history, return today's traffic-driven tip directly.
    if user_history_count < minimum_history_records or destination_history_count == 0:
        if user_history_count == 0:
            history_msg = "We don't have enough travel history for your account yet."
        elif destination_history_count == 0:
            history_msg = (
                f"We don't have enough travel history for {destination_clean} yet."
            )
        else:
            history_msg = (
                f"We have limited history ({user_history_count} trips) for better personalization."
            )

        if today_traffic == "High":
            return (
                f"{history_msg} Based on today's predicted High traffic for "
                f"{destination_clean}, leave at {baseline_time} or 15 minutes earlier."
            )
        if today_traffic == "Medium":
            return (
                f"{history_msg} Based on today's predicted Medium traffic for "
                f"{destination_clean}, leaving at {baseline_time} is recommended."
            )
        return (
            f"{history_msg} Based on today's predicted Low traffic for "
            f"{destination_clean}, {baseline_time} should be comfortable."
        )

    # Predict stable learned habit.
    usual_departure_hour = predict_usual_departure_hour_ml(
        user_id=user_id,
        day_name=day_name,
        weather_main="Clear",
        destination=destination_clean,
        hour=baseline_hour,
        traffic_level="Low",
    )

    # Predict today's context-aware behavior (kept for future extension).
    _today_behavior_hour = predict_usual_departure_hour_ml(
        user_id=user_id,
        day_name=day_name,
        weather_main=weather_clean,
        destination=destination_clean,
        hour=baseline_hour,
        traffic_level=today_traffic,
    )

    usual_hour_label = format_hour_label(usual_departure_hour)
    traffic_is_heavier = TRAFFIC_PRIORITY[today_traffic] > TRAFFIC_PRIORITY["Medium"]

    if traffic_is_heavier:
        return (
            f"Based on your learned travel behavior, you usually leave around "
            f"{usual_hour_label} for {destination_clean}. Today traffic is heavier than usual, "
            f"so leaving at {baseline_time} is recommended."
        )

    if today_traffic == "Low":
        return (
            f"Based on your learned travel behavior, you usually leave around "
            f"{usual_hour_label} for {destination_clean}. Traffic looks lighter today, "
            f"so {baseline_time} should work comfortably."
        )

    return (
        f"Based on your learned travel behavior, you usually leave around "
        f"{usual_hour_label} for {destination_clean}. Today's traffic is normal, "
        f"so {baseline_time} is a good plan."
    )


def parking_suggestion(availability: str) -> str:
    """Return a helpful user-facing suggestion based on parking level."""
    suggestions = {
        "Low": "Parking is likely limited. Consider arriving earlier or using paid parking.",
        "Medium": "Parking may be available with some wait. Keep a backup parking option.",
        "High": "Parking is likely available. Standard arrival time should work.",
    }
    return suggestions[availability]


def predict_parking_availability_rule(
    *,
    area_type: str,
    hour: int,
    day_of_week: str,
    holiday: str,
    traffic_level: str,
) -> str:
    """
    Rule-based parking prediction for Module 3.
    Hackathon MVP logic:
    1) Start from a medium parking baseline.
    2) Apply traffic impact (stronger in office/mall/market/station).
    3) Apply simple area/time/day/holiday adjustments.
    """
    day_number = parse_day_of_week(day_of_week)
    weekend = day_number >= 5
    holiday_flag = is_holiday_flag(holiday)
    traffic = parse_traffic_level(traffic_level)
    area = area_type.strip().lower()
    congestion_sensitive_areas = {"office", "mall", "market", "station"}

    # Score meaning: 0=Low, 1=Medium, 2=High parking availability.
    score = 1  # Start from Medium availability.

    # Traffic is the main signal: higher congestion tends to reduce parking.
    score += {"Low": 1, "Medium": 0, "High": -1}[traffic]

    # Make traffic impact stronger in dense/commercial areas.
    if area in congestion_sensitive_areas and traffic == "High":
        score -= 1
    if area in congestion_sensitive_areas and traffic == "Low":
        score += 0  # Explicitly keep simple behavior for low congestion.

    # Area/time/day adjustments (simple hackathon rules)
    if area == "office":
        # Weekday office rush hours usually have limited parking.
        if not weekend and not holiday_flag and (8 <= hour <= 11 or 16 <= hour <= 19):
            score -= 1
        # Off-hours and holidays usually improve parking around offices.
        if weekend or holiday_flag:
            score += 1
    elif area == "mall":
        # Malls are usually crowded on weekend/holiday afternoons and evenings.
        if weekend and 12 <= hour <= 21:
            score -= 1
        if holiday_flag and 12 <= hour <= 21:
            score -= 1
        # Weekday mornings are relatively easier.
        if not weekend and 8 <= hour <= 10:
            score += 1
    elif area == "residential":
        # Residential streets are typically easier late night/early morning.
        if hour >= 22 or hour <= 6:
            score += 1
        # Weekday evening return-home window can be tight.
        if not weekend and 18 <= hour <= 21:
            score -= 1
    elif area == "market":
        # Markets are busy around shopping/business windows.
        if 9 <= hour <= 14:
            score -= 1
        # Evening peak for markets.
        if 17 <= hour <= 20:
            score -= 1
        if weekend and 15 <= hour <= 20:
            score -= 1
        if holiday_flag and 10 <= hour <= 20:
            score -= 1
    elif area == "station":
        # Commuter peaks around stations reduce parking availability.
        if 6 <= hour <= 10 or 17 <= hour <= 20:
            score -= 1
        if holiday_flag and 9 <= hour <= 20:
            score -= 1
        # Late-night station areas can be relatively less crowded.
        if hour >= 22 or hour <= 5:
            score += 1
    else:
        # Beginner-friendly fallback for unknown area types.
        pass

    # Keep score inside valid bounds and convert back to label.
    score = max(0, min(2, score))
    return {0: "Low", 1: "Medium", 2: "High"}[score]


def predict_slots_in_range(
    *,
    start_hour: int,
    end_hour: int,
    day_of_week: int,
    weather_main: str,
    temp: float,
    rain_1h: float,
    holiday: str,
) -> list[CheckedSlot]:
    """
    Generate 15-minute slots in an hour range and predict traffic for each slot.
    """
    slots = generate_departure_slots(start_hour, end_hour, 15)

    if delhi_traffic_model is not None:
        weather_condition = map_weather_to_delhi_condition(weather_main, temp=temp)
        delhi_rows = []
        for slot in slots:
            estimated_speed = estimate_speed_kmph_for_context(
                hour=int(slot["hour"]),
                weather_condition=weather_condition,
            )
            delhi_rows.append(
                build_delhi_traffic_feature_row(
                    start_area="Delhi Start",
                    end_area="Delhi Destination",
                    distance_km=8.0,
                    hour=int(slot["hour"]),
                    day_index=day_of_week,
                    weather_main=weather_main,
                    temp=temp,
                    avg_speed_kmph=estimated_speed,
                )
            )
        predictions = predict_traffic_levels_delhi(delhi_rows)
    else:
        feature_rows = [
            build_feature_row(
                hour=slot["hour"],
                day_of_week=day_of_week,
                weather_main=weather_main,
                temp=temp,
                rain_1h=rain_1h,
                holiday=holiday,
            )
            for slot in slots
        ]
        predictions = predict_traffic_levels(feature_rows)

    return [
        CheckedSlot(time=slot["display_time"], traffic=parse_traffic_level(predicted_level))
        for slot, predicted_level in zip(slots, predictions)
    ]


def append_trip_to_csv(trip_row: dict) -> None:
    """
    Append one trip to local CSV storage.
    Creates the file with header on first write.
    """
    with TRIP_HISTORY_LOCK:
        TRIP_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_exists = TRIP_HISTORY_FILE.exists()
        with TRIP_HISTORY_FILE.open("a", newline="", encoding="utf-8") as file_obj:
            writer = csv.DictWriter(file_obj, fieldnames=TRIP_HISTORY_COLUMNS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(trip_row)


def parse_current_time(value: Optional[str]) -> datetime:
    """Parse ISO datetime input or fallback to current local time."""
    if value is None:
        return datetime.now()

    try:
        # Accept common ISO values like 2026-03-10T08:07:00
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            "Invalid current_time format. Use ISO format like 2026-03-10T08:07:00."
        ) from exc


def parse_time_hhmm(value: str) -> tuple[int, int]:
    """Parse HH:MM string and return (hour, minute)."""
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValueError("arrival_by_time must be in HH:MM format.") from exc
    return parsed.hour, parsed.minute


def resolve_target_arrival_datetime(
    *,
    reference_dt: datetime,
    arrival_by_time: Optional[str],
    preferred_arrival_hour: Optional[int],
) -> datetime:
    """
    Resolve arrival target datetime from request.
    Priority: arrival_by_time (HH:MM) > preferred_arrival_hour > +60 minutes fallback.
    """
    if arrival_by_time:
        hour, minute = parse_time_hhmm(arrival_by_time)
        target_dt = reference_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target_dt <= reference_dt:
            target_dt += timedelta(days=1)
        return target_dt

    if preferred_arrival_hour is not None:
        target_dt = reference_dt.replace(
            hour=int(preferred_arrival_hour),
            minute=0,
            second=0,
            microsecond=0,
        )
        if target_dt <= reference_dt:
            target_dt += timedelta(days=1)
        return target_dt

    # Backward-compatible fallback when frontend does not send arrival target.
    return reference_dt + timedelta(minutes=60)


def combine_date_with_time(reference_dt: datetime, hhmm: str) -> datetime:
    """Combine reference date with HH:MM string."""
    hour, minute = parse_time_hhmm(hhmm)
    return reference_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)


def estimate_departure_from_arrival(
    *,
    target_arrival_dt: datetime,
    route_duration_min: int,
    traffic_level: str,
    weather_main: str,
) -> tuple[datetime, int, int]:
    """
    Compute a safe departure time so user can reach by arrival target.
    Returns (departure_dt, total_travel_minutes_with_buffer, buffer_minutes).
    """
    normalized_traffic = parse_traffic_level(traffic_level)
    base_buffer = {"Low": 5, "Medium": 10, "High": 15}[normalized_traffic]
    weather = normalize_weather_main(weather_main).strip().lower()
    if weather in {"rain", "drizzle", "thunderstorm", "fog", "haze"}:
        base_buffer += 5

    total_travel_minutes = max(5, int(route_duration_min)) + base_buffer
    departure_dt = target_arrival_dt - timedelta(minutes=total_travel_minutes)
    return departure_dt, total_travel_minutes, base_buffer


def ceil_to_next_interval(dt: datetime, interval_minutes: int = 15) -> datetime:
    """Round time up to the next 15-minute boundary."""
    rounded = dt.replace(second=0, microsecond=0)
    remainder = rounded.minute % interval_minutes
    if remainder == 0:
        return rounded
    return rounded + timedelta(minutes=interval_minutes - remainder)


def floor_to_previous_interval(dt: datetime, interval_minutes: int = 15) -> datetime:
    """Round time down to the previous 15-minute boundary."""
    rounded = dt.replace(second=0, microsecond=0)
    remainder = rounded.minute % interval_minutes
    if remainder == 0:
        return rounded
    return rounded - timedelta(minutes=remainder)


def recommend_best_departure(
    *,
    day_of_week: Optional[str],
    weather_main: str,
    temp: float,
    rain_1h: float,
    holiday: str,
    destination_type: str,
    preferred_arrival_hour: Optional[int],
    traffic_level: Optional[str],
    current_time: Optional[str],
    horizon_minutes: int,
) -> BestTimeResponse:
    """
    Module 2 logic:
    Predict best departure hour using trained departure model.
    Respect horizon_minutes as a maximum look-back window in whole hours
    (rounded up with a minimum 1-hour horizon for hour-level output).
    """
    day_name, day_index = resolve_day_context(day_of_week, current_time)
    arrival_hour = resolve_preferred_arrival_hour(preferred_arrival_hour, current_time)
    resolved_traffic = resolve_departure_traffic_level(
        traffic_level,
        day_index=day_index,
        preferred_arrival_hour=arrival_hour,
        weather_main=weather_main,
        temp=temp,
        rain_1h=rain_1h,
        holiday=holiday,
    )

    best_hour = predict_best_departure_hour_ml(
        day_name=day_name,
        weather_main=weather_main,
        temp=temp,
        rain_1h=rain_1h,
        holiday=holiday,
        destination_type=destination_type,
        preferred_arrival_hour=arrival_hour,
        traffic_level=resolved_traffic,
    )
    lookback_hours = max(1, min(3, (int(horizon_minutes) + 59) // 60))
    earliest_allowed_hour = max(0, arrival_hour - lookback_hours)
    best_hour = max(earliest_allowed_hour, min(arrival_hour, best_hour))

    recommended_time = f"{best_hour:02d}:00"
    return BestTimeResponse(
        recommended_departure_time=recommended_time,
        recommended_traffic_level=resolved_traffic,
        evaluated_slots=[
            SlotPrediction(
                departure_time=recommended_time,
                predicted_traffic_level=resolved_traffic,
            )
        ],
        rule=(
            "Predicted best departure hour using trained departure_model.pkl "
            "from destination, weather, holiday, and traffic context, constrained "
            "by horizon_minutes."
        ),
    )


@app.get("/health")
def health() -> dict:
    """Simple health check endpoint."""
    return {"status": "ok"}


@app.post("/predict", response_model=TrafficResponse)
def predict_traffic(request: TrafficRequest) -> TrafficResponse:
    """Predict traffic level from one input record."""
    try:
        day_number = parse_day_of_week(request.day_of_week)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if delhi_traffic_model is not None:
        weather_condition = map_weather_to_delhi_condition(request.weather_main, request.temp)
        estimated_speed = estimate_speed_kmph_for_context(
            hour=request.hour,
            weather_condition=weather_condition,
        )
        delhi_row = build_delhi_traffic_feature_row(
            start_area="Delhi Start",
            end_area="Delhi Destination",
            distance_km=8.0,
            hour=request.hour,
            day_index=day_number,
            weather_main=request.weather_main,
            temp=request.temp,
            avg_speed_kmph=estimated_speed,
        )
        prediction = predict_traffic_levels_delhi([delhi_row])[0]
    else:
        row = build_feature_row(
            hour=request.hour,
            day_of_week=day_number,
            weather_main=request.weather_main,
            temp=request.temp,
            rain_1h=request.rain_1h,
            holiday=request.holiday,
        )
        prediction = predict_traffic_levels([row])[0]

    return TrafficResponse(predicted_traffic_level=prediction)


@app.post("/best-time-to-leave", response_model=BestTimeResponse)
def best_time_to_leave(request: BestTimeRequest) -> BestTimeResponse:
    """Recommend best departure time (Module 2 model-based)."""
    try:
        return recommend_best_departure(
            day_of_week=request.day_of_week,
            weather_main=request.weather_main,
            temp=request.temp,
            rain_1h=request.rain_1h,
            holiday=request.holiday,
            destination_type=request.destination_type,
            preferred_arrival_hour=request.preferred_arrival_hour,
            traffic_level=request.traffic_level,
            current_time=request.current_time,
            horizon_minutes=request.horizon_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/predict-slots", response_model=MultiSlotResponse)
def predict_slots(request: MultiSlotRequest) -> MultiSlotResponse:
    """
    Predict traffic for multiple generated 15-minute slots using the same model.
    """
    try:
        day_number = parse_day_of_week(request.day_of_week)
        checked_slots = predict_slots_in_range(
            start_hour=request.start_hour,
            end_hour=request.end_hour,
            day_of_week=day_number,
            weather_main=request.weather_main,
            temp=request.temp,
            rain_1h=request.rain_1h,
            holiday=request.holiday,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    slot_predictions = [
        SlotPrediction(
            departure_time=slot.time,
            predicted_traffic_level=slot.traffic,
        )
        for slot in checked_slots
    ]
    return MultiSlotResponse(slot_predictions=slot_predictions)


@app.post("/recommend-departure", response_model=RecommendDepartureResponse)
def recommend_departure(request: MultiSlotRequest) -> RecommendDepartureResponse:
    """
    Recommend the best departure slot from predicted 15-minute slots.
    Priority rule: Low > Medium > High, tie-break by earliest time.
    """
    try:
        day_number = parse_day_of_week(request.day_of_week)
        checked_slots = predict_slots_in_range(
            start_hour=request.start_hour,
            end_hour=request.end_hour,
            day_of_week=day_number,
            weather_main=request.weather_main,
            temp=request.temp,
            rain_1h=request.rain_1h,
            holiday=request.holiday,
        )
        best = choose_best_departure_slot(
            [{"time": slot.time, "traffic": slot.traffic} for slot in checked_slots]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RecommendDepartureResponse(
        recommended_departure_time=best["best_time"],
        predicted_traffic_level=best["best_traffic_level"],
        checked_slots=checked_slots,
    )


@app.post("/parking-predict", response_model=ParkingPredictResponse)
def parking_predict(request: ParkingPredictRequest) -> ParkingPredictResponse:
    """
    Module 3 endpoint: predict parking availability using the trained ML model.
    """
    try:
        availability = predict_parking_availability_ml(
            area_type=request.area_type,
            hour=request.hour,
            day_of_week=request.day_of_week,
            holiday=request.holiday,
            traffic_level=request.traffic_level,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ParkingPredictResponse(
        parking_availability=availability,
        suggestion=parking_suggestion(availability),
    )


@app.post("/log-trip", response_model=LogTripResponse)
def log_trip(request: LogTripRequest) -> LogTripResponse:
    """
    Module 4 endpoint: store trip history for lightweight personalization.
    """
    try:
        # Reuse existing validators to keep inputs consistent across modules.
        parse_day_of_week(request.day_of_week)
        normalized_traffic = parse_traffic_level(request.traffic_level)
        validated_time = validate_time_hhmm(request.recommended_departure_time)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    trip_row = {
        "user_id": request.user_id.strip().lower(),
        "source": request.source.strip(),
        "destination": request.destination.strip(),
        "day_of_week": request.day_of_week.strip(),
        "departure_hour": request.departure_hour,
        "weather_main": request.weather_main.strip(),
        "traffic_level": normalized_traffic,
        "recommended_departure_time": validated_time,
        # Store event creation time for future behavior analysis.
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }

    try:
        append_trip_to_csv(trip_row)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Failed to save trip history.") from exc

    return LogTripResponse(
        status="saved",
        message="Trip history logged successfully",
    )


@app.post("/user-patterns", response_model=UserPatternsResponse)
def user_patterns(request: UserPatternsRequest) -> UserPatternsResponse:
    """
    Module 4 endpoint: read stored trip history and return simple behavior patterns.
    """
    try:
        history_df = load_trip_history_dataframe()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    required_columns = {"user_id", "destination", "departure_hour", "day_of_week"}
    if not required_columns.issubset(set(history_df.columns)):
        raise HTTPException(
            status_code=500,
            detail="Trip history file format is invalid.",
        )

    # Filter only this user's records.
    user_history = history_df[
        history_df["user_id"].astype(str).str.strip().str.lower()
        == request.user_id.strip().lower()
    ].copy()
    if user_history.empty:
        raise HTTPException(
            status_code=404,
            detail="No trip history found for this user.",
        )

    # Most common destination.
    most_frequent_destination = str(user_history["destination"].astype(str).mode().iloc[0])

    # Most common departure hour.
    departure_hours = pd.to_numeric(user_history["departure_hour"], errors="coerce").dropna()
    if departure_hours.empty:
        raise HTTPException(
            status_code=400,
            detail="No valid departure_hour values found for this user.",
        )
    usual_departure_hour = int(departure_hours.mode().iloc[0])

    # Determine if user mostly travels on weekdays or weekends.
    day_types = user_history["day_of_week"].apply(day_value_to_type).dropna()
    most_common_day_type = (
        str(day_types.mode().iloc[0]) if not day_types.empty else "weekday"
    )

    return UserPatternsResponse(
        most_frequent_destination=most_frequent_destination,
        usual_departure_hour=usual_departure_hour,
        most_common_day_type=most_common_day_type,
        personalized_message=build_personalized_pattern_message(
            most_frequent_destination,
            usual_departure_hour,
            most_common_day_type,
        ),
    )


@app.post("/personalized-tip", response_model=PersonalizedTipResponse)
def personalized_tip(request: PersonalizedTipRequest) -> PersonalizedTipResponse:
    """
    Module 4 endpoint: generate personalized tip using trained behavior model.
    """
    try:
        tip_text = build_personalized_tip_text(
            user_id=request.user_id,
            destination=request.destination,
            predicted_traffic_level=request.predicted_traffic_level,
            recommended_departure_time=request.recommended_departure_time,
            day_of_week=request.day_of_week,
            weather_main=request.weather_main,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PersonalizedTipResponse(personalized_tip=tip_text)


@app.post("/simulate-event", response_model=SimulateEventResponse)
def simulate_event(request: SimulateEventRequest) -> SimulateEventResponse:
    """
    Feature 5 endpoint: simulate sudden traffic events and reroute suggestions.
    """

    def to_dict(model_obj: BaseModel) -> dict:
        if hasattr(model_obj, "model_dump"):
            return model_obj.model_dump()  # pydantic v2
        return model_obj.dict()  # pydantic v1

    try:
        current_traffic = parse_traffic_level(request.current_predicted_traffic or "Medium")

        if request.selected_route_summary is None:
            selected_summary = RouteSummary(
                route_name="Main Route",
                distance_km=6.0,
                estimated_duration_min=18,
                traffic_level=current_traffic,
            )
        else:
            selected_summary = request.selected_route_summary

        if request.alternate_route_summaries:
            alternate_summaries = request.alternate_route_summaries
        else:
            alt_1_duration = max(5, selected_summary.estimated_duration_min + 4)
            alt_2_duration = max(5, selected_summary.estimated_duration_min + 8)
            alternate_summaries = [
                RouteSummary(
                    route_name="Alternate Route 1",
                    distance_km=round(selected_summary.distance_km * 1.1, 2),
                    estimated_duration_min=alt_1_duration,
                    traffic_level=estimate_route_traffic_from_delay(
                        selected_summary.estimated_duration_min,
                        alt_1_duration,
                        selected_summary.traffic_level,
                    ),
                ),
                RouteSummary(
                    route_name="Alternate Route 2",
                    distance_km=round(selected_summary.distance_km * 1.2, 2),
                    estimated_duration_min=alt_2_duration,
                    traffic_level=estimate_route_traffic_from_delay(
                        selected_summary.estimated_duration_min,
                        alt_2_duration,
                        selected_summary.traffic_level,
                    ),
                ),
            ]

        simulation_payload = simulate_traffic_event(
            selected_route_summary=to_dict(selected_summary),
            alternate_route_summaries=[to_dict(item) for item in alternate_summaries],
            current_predicted_traffic=current_traffic,
            simulated_delay_minutes=request.delay_minutes,
            event_type=request.event_type,
            affected_route=request.affected_route,
        )
        return SimulateEventResponse(**simulation_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/smart-route-analysis", response_model=SmartRouteAnalysisResponse)
def smart_route_analysis(request: SmartRouteAnalysisRequest) -> SmartRouteAnalysisResponse:
    """
    Master orchestration endpoint for map-first frontend flow.
    It derives context from coordinates + current time and combines
    outputs from traffic, departure, parking, and personalization modules.
    """
    try:
        current_dt = parse_current_time(request.current_time)
        target_arrival_dt = resolve_target_arrival_datetime(
            reference_dt=current_dt,
            arrival_by_time=request.arrival_by_time,
            preferred_arrival_hour=request.preferred_arrival_hour,
        )
        day_index = target_arrival_dt.weekday()
        day_name = DAY_INDEX_TO_NAME[day_index]
        slot_day_index = current_dt.weekday()
        arrival_hour = target_arrival_dt.hour

        weather_main, temp, rain_1h = derive_weather_context(target_arrival_dt)
        holiday_for_traffic = "None"
        holiday_flag = "No"

        fallback_distance_km = haversine_distance_km(
            request.start_lat,
            request.start_lng,
            request.end_lat,
            request.end_lng,
        )
        selected_distance_km = max(
            0.1, float(request.selected_route_distance_km or fallback_distance_km)
        )
        selected_duration_min = (
            int(request.selected_route_duration_min)
            if request.selected_route_duration_min is not None
            else estimate_duration_minutes(selected_distance_km, "Medium")
        )
        selected_duration_min = max(5, selected_duration_min)

        destination_type = (
            infer_destination_type_from_address(request.destination_address)
            or infer_destination_type(
                day_index,
                arrival_hour,
                selected_distance_km,
            )
        )

        predicted_future_traffic = predict_route_traffic_level(
            start_address=request.start_address,
            destination_address=request.destination_address,
            distance_km=selected_distance_km,
            duration_min=selected_duration_min,
            hour=arrival_hour,
            day_index=day_index,
            weather_main=weather_main,
            temp=temp,
        )

        model_best_departure = recommend_best_departure(
            day_of_week=day_name,
            weather_main=weather_main,
            temp=temp,
            rain_1h=rain_1h,
            holiday=holiday_flag,
            destination_type=destination_type,
            preferred_arrival_hour=arrival_hour,
            traffic_level=predicted_future_traffic,
            current_time=target_arrival_dt.isoformat(timespec="seconds"),
            horizon_minutes=120,
        )
        model_departure_dt = combine_date_with_time(
            target_arrival_dt,
            model_best_departure.recommended_departure_time,
        )
        if model_departure_dt > target_arrival_dt:
            model_departure_dt -= timedelta(days=1)

        arrival_based_departure_dt, estimated_travel_minutes, departure_buffer_minutes = (
            estimate_departure_from_arrival(
                target_arrival_dt=target_arrival_dt,
                route_duration_min=selected_duration_min,
                traffic_level=predicted_future_traffic,
                weather_main=weather_main,
            )
        )

        # Final recommendation is primarily arrival-aware.
        # Use model's earlier suggestion only when it is close (<=30 min earlier),
        # otherwise avoid overly-early departure recommendations.
        model_early_gap_min = (
            arrival_based_departure_dt - model_departure_dt
        ).total_seconds() / 60
        if 0 <= model_early_gap_min <= 30:
            recommended_departure_dt = model_departure_dt
        else:
            recommended_departure_dt = arrival_based_departure_dt

        is_running_late = recommended_departure_dt < current_dt
        if is_running_late:
            # If recommended time is already past, suggest leaving now.
            recommended_departure_dt = current_dt
        recommended_departure_time = recommended_departure_dt.strftime("%H:%M")

        next_slots = predict_next_time_slot_recommendations(
            day_index=slot_day_index,
            weather_main=weather_main,
            temp=temp,
            rain_1h=rain_1h,
            holiday=holiday_for_traffic,
            current_dt=current_dt,
            start_address=request.start_address,
            destination_address=request.destination_address,
            route_distance_km=selected_distance_km,
            route_duration_min=selected_duration_min,
            target_end_dt=target_arrival_dt,
            max_slots=96,
        )
        timeline_payload = build_traffic_timeline(
            next_time_slot_recommendations=next_slots,
            recommended_departure_time=recommended_departure_time,
            target_arrival_time=target_arrival_dt.strftime("%H:%M"),
        )
        traffic_timeline = [TrafficTimelinePoint(**item) for item in timeline_payload["traffic_timeline"]]

        parking_availability = predict_parking_availability_ml(
            area_type=destination_type,
            hour=arrival_hour,
            day_of_week=day_name,
            holiday=holiday_flag,
            traffic_level=predicted_future_traffic,
        )
        parking_probability = parking_availability_to_probability(parking_availability)
        parking_intelligence = generate_parking_options(
            destination_lat=request.end_lat,
            destination_lng=request.end_lng,
            parking_availability=parking_availability,
            destination_context=destination_type,
        )
        parking_options = [ParkingOption(**item) for item in parking_intelligence["parking_options"]]
        best_parking_option = BestParkingOption(**parking_intelligence["best_parking_option"])

        arrival_probability, arrival_probability_label = calculate_arrival_probability(
            predicted_travel_time_min=selected_duration_min,
            departure_buffer_min=departure_buffer_minutes,
            predicted_traffic_level=predicted_future_traffic,
        )

        traffic_confidence = calculate_traffic_confidence(
            predicted_traffic_level=predicted_future_traffic,
            weather_main=weather_main,
            rain_1h=rain_1h,
        )
        parking_confidence = calculate_parking_confidence(
            parking_availability=parking_availability,
            destination_type=destination_type,
            traffic_level=predicted_future_traffic,
        )

        explanation = RouteExplanation(
            **generate_route_explanation(
                predicted_traffic_level=predicted_future_traffic,
                travel_time_min=selected_duration_min,
                parking_availability=parking_availability,
                departure_buffer_min=departure_buffer_minutes,
                arrival_probability=arrival_probability,
            )
        )

        destination_label = (request.destination_address or "Destination").strip()
        tip_text = build_personalized_tip_text(
            user_id=request.user_id,
            destination=destination_label,
            predicted_traffic_level=predicted_future_traffic,
            recommended_departure_time=recommended_departure_time,
            day_of_week=day_name,
            weather_main=weather_main,
        )

        selected_route_summary, alternate_route_summaries = build_route_summaries(
            predicted_future_traffic=predicted_future_traffic,
            fallback_distance_km=fallback_distance_km,
            selected_route_distance_km=request.selected_route_distance_km,
            selected_route_duration_min=request.selected_route_duration_min,
            alternate_route_distances_km=request.alternate_route_distances_km,
            alternate_route_durations_min=request.alternate_route_durations_min,
        )

        # Decision Intelligence Layer:
        # Combine traffic, travel time, parking ease, and personalization into one score.
        # Personalization is currently a placeholder and can be replaced with a real route-specific model signal.
        route_candidates: list[dict] = []
        personalization_placeholder = 0.7
        all_route_summaries = [selected_route_summary, *alternate_route_summaries]

        for index, route_summary in enumerate(all_route_summaries):
            route_candidates.append(
                {
                    "route_name": route_summary.route_name,
                    "route_type": "selected" if index == 0 else "alternate",
                    "distance_km": route_summary.distance_km,
                    "travel_time_min": int(route_summary.estimated_duration_min),
                    "predicted_traffic": resolve_route_traffic_for_decision(
                        route_summary=route_summary,
                        selected_route_duration_min=selected_route_summary.estimated_duration_min,
                        selected_route_traffic=predicted_future_traffic,
                    ),
                    # Current parking model returns destination-level availability,
                    # so every route uses the same base probability for now.
                    "parking_probability": parking_probability,
                    "personalization_score": personalization_placeholder,
                }
            )

        scored_routes = calculate_weighted_route_scores(route_candidates)
        best_route, backup_route, all_routes_ranked = select_best_and_backup(scored_routes)
        route_decision = RouteDecision(
            best_route=best_route,
            backup_route=backup_route,
            all_routes_ranked=all_routes_ranked,
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SmartRouteAnalysisResponse(
        selected_route_summary=selected_route_summary,
        alternate_route_summaries=alternate_route_summaries,
        route_decision=route_decision,
        predicted_future_traffic=predicted_future_traffic,
        recommended_departure_time=recommended_departure_time,
        recommended_traffic_level=model_best_departure.recommended_traffic_level,
        target_arrival_time=target_arrival_dt.strftime("%H:%M"),
        estimated_travel_minutes=estimated_travel_minutes,
        departure_buffer_minutes=departure_buffer_minutes,
        is_running_late=is_running_late,
        next_time_slot_recommendations=next_slots,
        parking_availability=parking_availability,
        parking_probability=parking_probability,
        parking_suggestion=parking_suggestion(parking_availability),
        parking_options=parking_options,
        best_parking_option=best_parking_option,
        arrival_probability=arrival_probability,
        arrival_probability_label=arrival_probability_label,
        traffic_confidence=traffic_confidence,
        parking_confidence=parking_confidence,
        traffic_timeline=traffic_timeline,
        recommended_departure_marker=timeline_payload["recommended_departure_marker"],
        arrival_marker=timeline_payload["arrival_marker"],
        explanation=explanation,
        personalized_tip=tip_text,
        destination_type=destination_type,
        weather_main=weather_main,
    )
