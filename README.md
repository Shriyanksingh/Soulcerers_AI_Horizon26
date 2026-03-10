# Smart Navigation AI (Delhi)

Map-first smart navigation project with FastAPI + React + Leaflet.

It combines:
- traffic prediction,
- best departure recommendation,
- parking intelligence,
- user personalization,
- explainable route decisioning,
- timeline visualization,
- real-time simulation for demo scenarios.

---

## 1) What It Does

You select:
- start location,
- destination,
- target arrival time.

System returns:
- predicted future traffic,
- recommended departure time,
- route decision ranking (best + backup),
- parking availability and nearby parking options,
- arrival probability,
- confidence scores,
- explanation of recommendation,
- 15-minute traffic timeline until arrival.

---

## 2) Feature Set (Current)

### Feature 1: Decision Intelligence
- Weighted route scoring:
  - Traffic score (0.4)
  - Time score (0.3)
  - Parking score (0.2)
  - Personalization score (0.1)
- Selects best route and backup route.

### Feature 2: Explanation Engine
- Rule-based human-readable reasoning.
- Adds `why_this_route[]` and `risk_warning`.

### Feature 3: Arrival Probability
- Estimates chance of reaching on time.
- Returns numeric probability + label.

### Feature 4: Confidence Scores
- Traffic confidence + parking confidence heuristics.

### Feature 5: Real-Time Simulation Engine
- Endpoint: `POST /simulate-event`
- Simulates traffic spike/block/accident and reroute recommendation.

### Feature 6: Parking Intelligence Upgrade
- Generates nearby parking options (demo-safe deterministic mock logic).
- Highlights best parking option.

### Feature 7: Timeline Traffic Visualization
- Converts slot predictions into frontend timeline objects.
- Includes departure and arrival markers.

---

## 3) Architecture

```text
Frontend (React + Leaflet, no build pipeline)
    |
    | HTTP JSON
    v
FastAPI Backend (backend/app.py)
    |
    | orchestration across modules
    v
ML models + decision/explain/probability/confidence/simulation/timeline engines
```

---

## 4) Tech Stack

| Layer | Stack |
|---|---|
| Frontend | React (browser scripts), Leaflet, custom Node static server |
| Backend | FastAPI, Uvicorn |
| ML | scikit-learn, pandas, joblib |
| Data | CSV datasets + local trip history CSV |
| Maps | OpenStreetMap, OSRM, Nominatim |

---

## 5) Project Structure

```text
backend/
  app.py
  slot_utils.py
  decision_engine.py
  explain_engine.py
  probability_utils.py
  confidence_utils.py
  parking_intelligence.py
  timeline_utils.py
  simulation_engine.py

frontend/
  index.html
  server.js
  src/
    App.jsx
    App.css
    services/
      api.js
    components/
      TrafficTimeline.jsx

modules/
  generate_delhi_module_datasets.py
  module1_traffic_prediction/
  module2_best_time_to_leave/
  module3_parking_availability/
  module4_user_behavior_learning/

data/
  module1/
  module2/
  module3/
  module4/

models/
  module1/
  module2/
  module3/
  module4/

run_latest_backend_8010.bat
run_frontend_5173.bat
run_smart_nav_stack.bat
```

---

## 6) Run (Windows)

### One-click
```powershell
Set-Location -LiteralPath "C:\Users\LENOVO\OneDrive\Desktop\aimodeltraffic"
cmd /c ".\run_smart_nav_stack.bat"
```

### Manual
Backend terminal:
```powershell
Set-Location -LiteralPath "C:\Users\LENOVO\OneDrive\Desktop\aimodeltraffic"
cmd /c ".\run_latest_backend_8010.bat"
```

Frontend terminal:
```powershell
Set-Location -LiteralPath "C:\Users\LENOVO\OneDrive\Desktop\aimodeltraffic"
cmd /c ".\run_frontend_5173.bat"
```

Open:
- Frontend: `http://127.0.0.1:5173`
- Backend health: `http://127.0.0.1:8010/health`

---

## 7) API Overview

### Core

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | health check |
| POST | `/predict` | traffic prediction |
| POST | `/best-time-to-leave` | departure recommendation |
| POST | `/parking-predict` | parking availability |
| POST | `/personalized-tip` | personalization text |
| POST | `/smart-route-analysis` | full orchestration output |
| POST | `/simulate-event` | real-time event simulation |

### Supporting

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/predict-slots` | slot-wise traffic |
| POST | `/recommend-departure` | best slot |
| POST | `/log-trip` | save trip history |
| POST | `/user-patterns` | user behavior summary |

---

## 8) `POST /smart-route-analysis` (Current Response)

Existing + upgraded fields include:
- `selected_route_summary`
- `alternate_route_summaries`
- `route_decision`
- `predicted_future_traffic`
- `recommended_departure_time`
- `target_arrival_time`
- `estimated_travel_minutes`
- `departure_buffer_minutes`
- `next_time_slot_recommendations`
- `parking_availability`
- `parking_probability`
- `parking_options`
- `best_parking_option`
- `arrival_probability`
- `arrival_probability_label`
- `traffic_confidence`
- `parking_confidence`
- `traffic_timeline`
- `recommended_departure_marker`
- `arrival_marker`
- `explanation`
- `personalized_tip`

Example request:
```json
{
  "user_id": "u1",
  "start_lat": 28.6139,
  "start_lng": 77.2090,
  "end_lat": 28.6129,
  "end_lng": 77.2295,
  "current_time": "2026-03-10T08:00:00",
  "arrival_by_time": "09:00",
  "start_address": "Connaught Place, New Delhi",
  "destination_address": "India Gate, New Delhi",
  "selected_route_distance_km": 6.5,
  "selected_route_duration_min": 22,
  "alternate_route_distances_km": [7.1, 7.4],
  "alternate_route_durations_min": [25, 28]
}
```

---

## 9) `POST /simulate-event` Example

Request:
```json
{
  "event_type": "traffic_spike",
  "affected_route": "selected_route",
  "delay_minutes": 12
}
```

Response shape:
```json
{
  "event_type": "traffic_spike",
  "affected_route": "selected_route",
  "added_delay_minutes": 12,
  "updated_routes": [],
  "reroute_recommendation": "alternate_1",
  "simulation_summary": "Traffic spike detected. Alternate route is now safer.",
  "best_route_name": "Alternate Route 1"
}
```

---

## 10) Frontend UX (Current)

- Analog arrival-time picker.
- Route options with main/alternates.
- Full-screen AI Analysis Dashboard tabs:
  - Overview
  - Feature 1: Decision
  - Feature 2: Explanation
  - Feature 3: Arrival
  - Feature 4: Confidence
  - Feature 5: Simulation
  - Feature 6: Parking
  - Feature 7: Timeline
  - Slots
- Side action: `Simulate Traffic Spike`.

---

## 11) Troubleshooting

### `run_*.bat` not recognized (PowerShell)
```powershell
cmd /c ".\run_latest_backend_8010.bat"
cmd /c ".\run_frontend_5173.bat"
```

### Backend not reachable
1. Start backend on `8010`.
2. Verify:
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8010/health" -UseBasicParsing
```
3. Hard refresh frontend (`Ctrl + F5`).

### Port already in use
```powershell
netstat -ano | findstr :8010
netstat -ano | findstr :5173
Stop-Process -Id <PID> -Force
```

---

## 12) Demo Flow (Hackathon)

1. Open app.
2. Set start + destination.
3. Set arrival time.
4. Click `Show Routes + AI Analysis`.
5. Open AI dashboard and show Feature 1–7 tabs.
6. Run `Simulate Traffic Spike` and explain reroute.

---

## 13) Note

Frontend API validator expects latest backend response schema (including parking intelligence + timeline fields).  
If frontend shows “outdated backend”, restart backend and refresh frontend.

