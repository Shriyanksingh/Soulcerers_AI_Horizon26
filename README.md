# Smart Navigation AI (Delhi)

Map-first smart navigation app that combines:
- future traffic prediction,
- best time to leave,
- parking availability prediction,
- personalized travel tips from user behavior.

It includes a FastAPI backend (ML orchestration) and a React + Leaflet frontend (route and map UX).

---

## 1. What This Project Does

You select:
- start location,
- destination,
- arrival target time.

The system returns:
- predicted future traffic for the route,
- recommended departure time (arrival-aware),
- 15-minute traffic slots until arrival,
- parking availability at destination,
- personalized tip based on user history.

---

## 2. Key Features

- Map-first route planning (OSM + OSRM + Nominatim)
- Main + alternate route support
- AI route analysis endpoint: `/smart-route-analysis`
- Analog clock style arrival-time picker in UI
- Modular ML setup:
  - Module 1: traffic prediction
  - Module 2: best departure recommendation
  - Module 3: parking prediction
  - Module 4: user behavior personalization

---

## 3. High-Level Architecture

```text
Frontend (React + Leaflet)
    |
    | HTTP JSON
    v
FastAPI Backend (backend/app.py)
    |
    | model inference + orchestration
    v
models/module* + data/module4/trip_history.csv
```

---

## 4. Tech Stack

| Layer | Stack |
|---|---|
| Frontend | React (browser scripts), Leaflet, custom Node static server |
| Backend | FastAPI, Uvicorn |
| ML | scikit-learn, pandas, joblib |
| Data | CSV datasets + local trip history CSV |
| Maps | OpenStreetMap, OSRM, Nominatim |

---

## 5. Project Structure

```text
backend/
  app.py                             # FastAPI backend + all APIs
  slot_utils.py                      # slot helper functions

frontend/
  index.html
  server.js
  src/
    App.jsx
    App.css
    services/api.js

modules/
  generate_delhi_module_datasets.py
  module1_traffic_prediction/
    prepare_dataset.py
    train_random_forest.py
    train_delhi_traffic_model.py
  module2_best_time_to_leave/
    train_departure_model.py
  module3_parking_availability/
    train_parking_model.py
  module4_user_behavior_learning/
    train_user_behavior_model.py

data/
  module1/
    delhi/
    processed/
    legacy_archive/
  module2/
  module3/
  module4/

models/
  module1/
  module2/
  module3/
  module4/

logs/                               # runtime logs/errors/output files

run_latest_backend_8010.bat
run_frontend_5173.bat
run_smart_nav_stack.bat
```

---

## 6. Quick Start (Windows)

### Option A: One-click (recommended)

From project root:

```powershell
Set-Location -LiteralPath "C:\Users\LENOVO\OneDrive\Desktop\aimodeltraffic"
cmd /c ".\run_smart_nav_stack.bat"
```

### Option B: Manual start

Terminal 1 (backend):

```powershell
Set-Location -LiteralPath "C:\Users\LENOVO\OneDrive\Desktop\aimodeltraffic"
cmd /c ".\run_latest_backend_8010.bat"
```

Terminal 2 (frontend):

```powershell
Set-Location -LiteralPath "C:\Users\LENOVO\OneDrive\Desktop\aimodeltraffic"
cmd /c ".\run_frontend_5173.bat"
```

Open:
- Frontend: `http://127.0.0.1:5173`
- Backend health: `http://127.0.0.1:8010/health`

---

## 7. Important Runtime Note

Frontend API client now targets only:
- `http://127.0.0.1:8010`

There is no fallback to `8000` anymore.  
If backend `8010` is not running, frontend will show a clear connectivity error.

---

## 8. API Overview

### Core Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | health check |
| POST | `/predict` | traffic prediction |
| POST | `/best-time-to-leave` | best departure time |
| POST | `/parking-predict` | parking availability |
| POST | `/personalized-tip` | personalized suggestion |
| POST | `/smart-route-analysis` | combined map-first intelligence |

### Supporting Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/predict-slots` | slot-wise traffic prediction |
| POST | `/recommend-departure` | best slot selection |
| POST | `/log-trip` | save trip history |
| POST | `/user-patterns` | summarize user behavior |

---

## 9. Main Endpoint Example

### `POST /smart-route-analysis` request (example)

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

### Response includes

- `predicted_future_traffic`
- `recommended_departure_time`
- `target_arrival_time`
- `estimated_travel_minutes`
- `departure_buffer_minutes`
- `next_time_slot_recommendations`
- `parking_availability`
- `personalized_tip`
- `selected_route_summary`
- `alternate_route_summaries`

---

## 10. ML Models and Data

| Module | Goal | Model File | Training Script |
|---|---|---|---|
| Module 1 | Traffic prediction | `models/module1/traffic_model_delhi.pkl`, `models/module1/traffic_model.pkl` | `modules/module1_traffic_prediction/train_delhi_traffic_model.py`, `modules/module1_traffic_prediction/train_random_forest.py` |
| Module 2 | Best departure hour | `models/module2/departure_model.pkl` | `modules/module2_best_time_to_leave/train_departure_model.py` |
| Module 3 | Parking availability | `models/module3/parking_model.pkl` | `modules/module3_parking_availability/train_parking_model.py` |
| Module 4 | User behavior | `models/module4/user_behavior_model.pkl` | `modules/module4_user_behavior_learning/train_user_behavior_model.py` |

### Dataset generation

```powershell
python modules/generate_delhi_module_datasets.py
```

This creates:
- `data/module2/departure_dataset.csv`
- `data/module3/parking_dataset.csv`
- `data/module4/user_behavior_dataset.csv`

---

## 11. Frontend UX Notes

- Arrival time selection uses an analog clock picker (hour/minute dial + AM/PM).
- Manual fallback `time` input is also available for exact entry.
- Route cards show current (speed-derived) traffic and AI future traffic separately.

---

## 12. Troubleshooting

### A) `run_*.bat is not recognized`

Use:

```powershell
cmd /c ".\run_latest_backend_8010.bat"
cmd /c ".\run_frontend_5173.bat"
```

And ensure you are inside project root:

```powershell
Set-Location -LiteralPath "C:\Users\LENOVO\OneDrive\Desktop\aimodeltraffic"
```

### B) Frontend shows `Failed to fetch` / backend unreachable

1. Start backend on `8010`.
2. Check `http://127.0.0.1:8010/health`.
3. Refresh frontend.

### C) Port already in use

Find process:

```powershell
netstat -ano | findstr :8010
netstat -ano | findstr :5173
```

Kill process:

```powershell
Stop-Process -Id <PID> -Force
```

---

## 13. Suggested Demo Flow

1. Open frontend map.
2. Pick start and destination (search or map click).
3. Set arrival time from analog clock.
4. Click `Show Routes + AI Analysis`.
5. Explain outputs:
   - future traffic,
   - recommended departure,
   - slot timeline,
   - parking prediction,
   - personalized tip.

---

## 14. Status

Current project state is optimized for local Windows demo and hackathon-style iteration, with clear backend orchestration and modular ML training scripts.
