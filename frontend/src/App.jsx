const { useEffect, useRef, useState } = React;

const DEFAULT_CENTER = [28.6139, 77.209];
const TRAFFIC_COLOR_BY_LEVEL = {
  Low: "#16a34a",
  Medium: "#f59e0b",
  High: "#ef4444",
};
const TRAFFIC_PENALTY_SCORE = { Low: 0, Medium: 6, High: 14 };
const HOUR_MARKERS = Array.from({ length: 12 }, (_, idx) => ({
  index: idx,
  hour12: idx === 0 ? 12 : idx,
  label: String(idx === 0 ? 12 : idx),
}));
const MINUTE_MARKERS = Array.from({ length: 12 }, (_, idx) => ({
  index: idx,
  minute: idx * 5,
  label: String(idx * 5).padStart(2, "0"),
}));

const TILE_PROVIDERS = [
  {
    name: "OpenStreetMap",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    options: {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    },
  },
  {
    name: "CartoDB Light",
    url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    options: {
      maxZoom: 20,
      attribution:
        '&copy; OpenStreetMap contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    },
  },
  {
    name: "CartoDB Dark",
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    options: {
      maxZoom: 20,
      attribution:
        '&copy; OpenStreetMap contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    },
  },
];

function ensureStylesheet(href) {
  return new Promise((resolve, reject) => {
    const timeoutMs = 4000;
    let settled = false;

    const existing = Array.from(document.querySelectorAll("link[rel='stylesheet']")).find(
      (link) => link.href && link.href.includes(href)
    );

    const complete = () => {
      if (!settled) {
        settled = true;
        resolve();
      }
    };
    const fail = () => {
      if (!settled) {
        settled = true;
        reject(new Error("Failed to load map stylesheet."));
      }
    };

    if (existing) {
      if (existing.sheet) {
        complete();
        return;
      }

      const timer = setTimeout(() => {
        clearTimeout(timer);
        fail();
      }, 3000);
      existing.addEventListener(
        "load",
        () => {
          clearTimeout(timer);
          complete();
        },
        { once: true }
      );
      existing.addEventListener(
        "error",
        () => {
          clearTimeout(timer);
          fail();
        },
        { once: true }
      );
      return;
    }

    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;

    const timer = setTimeout(() => {
      // Fallback CSS exists in App.css; continue even if external CSS is slow.
      complete();
    }, timeoutMs);

    link.onload = () => {
      clearTimeout(timer);
      complete();
    };
    link.onerror = () => {
      clearTimeout(timer);
      fail();
    };
    document.head.appendChild(link);
  });
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const timeoutMs = 10000;
    let finished = false;
    const timeoutId = setTimeout(() => {
      if (!finished) {
        finished = true;
        reject(new Error("Map script load timed out."));
      }
    }, timeoutMs);

    const markResolved = () => {
      if (!finished) {
        finished = true;
        clearTimeout(timeoutId);
        resolve();
      }
    };

    const markRejected = () => {
      if (!finished) {
        finished = true;
        clearTimeout(timeoutId);
        reject(new Error("Failed to load map script."));
      }
    };

    const existing = Array.from(document.querySelectorAll("script")).find(
      (script) => script.src && script.src.includes(src)
    );
    if (existing) {
      if (window.L) {
        markResolved();
        return;
      }
      existing.addEventListener("load", markResolved, { once: true });
      existing.addEventListener("error", markRejected, { once: true });
      return;
    }

    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = markResolved;
    script.onerror = markRejected;
    document.body.appendChild(script);
  });
}

async function ensureLeafletLoaded() {
  if (window.L) {
    return;
  }

  const cdnCandidates = [
    {
      css: "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
      js: "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
    },
    {
      css: "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css",
      js: "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js",
    },
  ];

  let lastError = null;
  for (const candidate of cdnCandidates) {
    try {
      await ensureStylesheet(candidate.css);
      await loadScript(candidate.js);
      if (window.L) {
        return;
      }
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error("Leaflet failed to load from available CDNs.");
}

function classifyTrafficLevel(distanceKm, durationMin) {
  const hours = Math.max(0.05, durationMin / 60);
  const averageSpeed = distanceKm / hours;
  if (averageSpeed >= 38) {
    return "Low";
  }
  if (averageSpeed >= 26) {
    return "Medium";
  }
  return "High";
}

function formatDuration(minutes) {
  const total = Math.max(1, Math.round(minutes));
  const hours = Math.floor(total / 60);
  const mins = total % 60;
  if (hours === 0) {
    return `${mins} min`;
  }
  return `${hours}h ${mins}m`;
}

function formatDistance(km) {
  return `${km.toFixed(1)} km`;
}

function formatDecisionScore(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "N/A";
  }
  return numeric.toFixed(2);
}

function parseHourFromTime(value) {
  if (!value || typeof value !== "string") {
    return null;
  }
  const [hourPart] = value.split(":");
  const hour = Number(hourPart);
  if (!Number.isFinite(hour) || hour < 0 || hour > 23) {
    return null;
  }
  return hour;
}

function buildLocalNowIso() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  const hh = String(now.getHours()).padStart(2, "0");
  const min = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}T${hh}:${min}:${ss}`;
}

function fallbackCoordinateLabel(lat, lng) {
  return `Pinned Location (${lat.toFixed(5)}, ${lng.toFixed(5)})`;
}

function parseTimeParts(value) {
  if (!value || typeof value !== "string") {
    return null;
  }
  const [hourPart, minutePart] = value.split(":");
  const hour = Number(hourPart);
  const minute = Number(minutePart);
  if (
    !Number.isFinite(hour) ||
    !Number.isFinite(minute) ||
    hour < 0 ||
    hour > 23 ||
    minute < 0 ||
    minute > 59
  ) {
    return null;
  }
  return { hour, minute };
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function toTimeString(hour, minute) {
  return `${pad2(hour)}:${pad2(minute)}`;
}

function hour24To12(hour24) {
  const period = hour24 >= 12 ? "PM" : "AM";
  const remainder = hour24 % 12;
  return { hour12: remainder === 0 ? 12 : remainder, period };
}

function hour12To24(hour12, period) {
  if (period === "AM") {
    return hour12 === 12 ? 0 : hour12;
  }
  return hour12 === 12 ? 12 : hour12 + 12;
}

function formatTimeHHMM(dateObj) {
  const hh = String(dateObj.getHours()).padStart(2, "0");
  const mm = String(dateObj.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

function ceilToNextQuarter(dateObj) {
  const dt = new Date(dateObj);
  dt.setSeconds(0, 0);
  const mod = dt.getMinutes() % 15;
  if (mod !== 0) {
    dt.setMinutes(dt.getMinutes() + (15 - mod));
  }
  return dt;
}

function floorToQuarter(dateObj) {
  const dt = new Date(dateObj);
  dt.setSeconds(0, 0);
  const mod = dt.getMinutes() % 15;
  if (mod !== 0) {
    dt.setMinutes(dt.getMinutes() - mod);
  }
  return dt;
}

function computeArrivalAwareFallback({
  arrivalTime,
  routeDurationMin,
  predictedTrafficLevel,
}) {
  const parsed = parseTimeParts(arrivalTime);
  if (!parsed) {
    return null;
  }

  const now = new Date();
  const targetArrival = new Date(now);
  targetArrival.setHours(parsed.hour, parsed.minute, 0, 0);
  if (targetArrival <= now) {
    targetArrival.setDate(targetArrival.getDate() + 1);
  }

  const trafficLevel = predictedTrafficLevel || "Medium";
  const bufferMinutes =
    trafficLevel === "High" ? 15 : trafficLevel === "Low" ? 5 : 10;
  const totalTravelMinutes = Math.max(5, Math.round(routeDurationMin)) + bufferMinutes;
  const departure = new Date(targetArrival.getTime() - totalTravelMinutes * 60000);

  const isRunningLate = departure < now;
  const finalDeparture = isRunningLate ? now : departure;

  return {
    recommended_departure_time: formatTimeHHMM(finalDeparture),
    target_arrival_time: arrivalTime,
    estimated_travel_minutes: totalTravelMinutes,
    departure_buffer_minutes: bufferMinutes,
    is_running_late: isRunningLate,
  };
}

function buildArrivalSlotFallback(arrivalTime, predictedTrafficLevel) {
  const parsed = parseTimeParts(arrivalTime);
  if (!parsed) {
    return null;
  }

  const now = new Date();
  const targetArrival = new Date(now);
  targetArrival.setHours(parsed.hour, parsed.minute, 0, 0);
  if (targetArrival <= now) {
    targetArrival.setDate(targetArrival.getDate() + 1);
  }

  const start = ceilToNextQuarter(now);
  const end = floorToQuarter(targetArrival);
  const trafficLabel = predictedTrafficLevel || "Medium";

  const slots = [];
  const pointer = new Date(start);
  while (pointer <= end && slots.length < 96) {
    slots.push({ time: formatTimeHHMM(pointer), traffic: trafficLabel });
    pointer.setMinutes(pointer.getMinutes() + 15);
  }

  return slots;
}

function scoreRoute(route) {
  const trafficPenalty = TRAFFIC_PENALTY_SCORE[route.trafficLevel] ?? 10;
  // Lower score is better: prioritize faster ETA, then traffic, then distance.
  return route.durationMin + trafficPenalty + route.distanceKm * 0.7;
}

function findBestRouteIndex(routeList) {
  if (!routeList || routeList.length === 0) {
    return 0;
  }

  let bestIdx = 0;
  let bestScore = scoreRoute(routeList[0]);

  for (let idx = 1; idx < routeList.length; idx += 1) {
    const currentScore = scoreRoute(routeList[idx]);
    const currentRoute = routeList[idx];
    const bestRoute = routeList[bestIdx];

    if (currentScore < bestScore) {
      bestScore = currentScore;
      bestIdx = idx;
      continue;
    }

    if (Math.abs(currentScore - bestScore) < 0.1) {
      if (currentRoute.durationMin < bestRoute.durationMin) {
        bestIdx = idx;
      } else if (
        currentRoute.durationMin === bestRoute.durationMin &&
        currentRoute.distanceKm < bestRoute.distanceKm
      ) {
        bestIdx = idx;
      }
    }
  }

  return bestIdx;
}

async function searchPlaces(query, signal) {
  const encoded = encodeURIComponent(query.trim());
  if (!encoded) {
    return [];
  }
  const url = `https://nominatim.openstreetmap.org/search?format=jsonv2&limit=6&q=${encoded}`;
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error("Failed to fetch location suggestions.");
  }
  const rows = await response.json();
  return rows.map((row) => ({
    label: row.display_name,
    lat: Number(row.lat),
    lng: Number(row.lon),
  }));
}

async function geocodeSinglePlace(query) {
  const rows = await searchPlaces(query);
  if (!rows.length) {
    throw new Error("Location not found. Please try a different place.");
  }
  return rows[0];
}

async function reverseGeocode(lat, lng) {
  const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${encodeURIComponent(
    lat
  )}&lon=${encodeURIComponent(lng)}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error("Could not resolve map location.");
  }
  const payload = await response.json();
  return payload.display_name || fallbackCoordinateLabel(lat, lng);
}

function dedupeOsrmRoutes(rawRoutes) {
  const uniqueRoutes = [];
  const seen = new Set();

  for (const route of rawRoutes || []) {
    const coordinates = Array.isArray(route?.geometry?.coordinates)
      ? route.geometry.coordinates
      : [];
    if (!coordinates.length) {
      continue;
    }

    const distanceKm = Number(route.distance || 0) / 1000;
    const durationMin = Number(route.duration || 0) / 60;
    const midPoint = coordinates[Math.floor(coordinates.length / 2)] || coordinates[0];
    const signature = [
      distanceKm.toFixed(2),
      durationMin.toFixed(1),
      Number(midPoint?.[0] || 0).toFixed(4),
      Number(midPoint?.[1] || 0).toFixed(4),
    ].join("|");

    if (seen.has(signature)) {
      continue;
    }
    seen.add(signature);
    uniqueRoutes.push(route);
  }

  return uniqueRoutes;
}

async function fetchRouteAlternatives(start, end) {
  // Ask routing service for up to 5 alternatives. If alternates are unavailable,
  // service typically returns only one main route.
  const basePath = `${start.lng},${start.lat};${end.lng},${end.lat}`;
  const queryCandidates = [
    "overview=full&alternatives=5&steps=false&geometries=geojson",
    "overview=full&alternatives=true&steps=false&geometries=geojson",
    "overview=full&alternatives=false&steps=false&geometries=geojson",
  ];

  let payload = null;
  let lastError = null;

  for (const query of queryCandidates) {
    const url = `https://router.project-osrm.org/route/v1/driving/${basePath}?${query}`;
    try {
      const response = await fetch(url);
      if (!response.ok) {
        lastError = new Error(`Route service returned ${response.status}.`);
        continue;
      }

      const candidatePayload = await response.json();
      if (
        candidatePayload.code === "Ok" &&
        Array.isArray(candidatePayload.routes) &&
        candidatePayload.routes.length > 0
      ) {
        payload = candidatePayload;
        break;
      }
      lastError = new Error("No driving route found for these points.");
    } catch (error) {
      lastError = error;
    }
  }

  if (!payload) {
    throw new Error(lastError?.message || "Could not fetch routes. Please retry.");
  }

  const uniqueRoutes = dedupeOsrmRoutes(payload.routes);
  if (!uniqueRoutes.length) {
    throw new Error("No driving route found for these points.");
  }

  const limitedRoutes = uniqueRoutes.slice(0, 5);
  return limitedRoutes.map((route, index) => {
    const distanceKm = route.distance / 1000;
    const durationMin = route.duration / 60;
    const trafficLevel = classifyTrafficLevel(distanceKm, durationMin);
    const coordinates = route.geometry.coordinates.map((coord) => [coord[1], coord[0]]);

    return {
      routeName: index === 0 ? "Main Route" : `Alternate Route ${index}`,
      distanceKm,
      durationMin,
      trafficLevel,
      color: TRAFFIC_COLOR_BY_LEVEL[trafficLevel],
      coordinates,
    };
  });
}

function parseAlternateRouteIndex(routeName) {
  const match = /^Alternate Route\s+(\d+)$/i.exec(String(routeName || "").trim());
  if (!match) {
    return null;
  }
  const numeric = Number(match[1]);
  if (!Number.isFinite(numeric) || numeric < 1) {
    return null;
  }
  return numeric;
}

function toFrontendRouteIndexFromRouteName(routeName, selectedRouteIndex, routeCount) {
  const cleaned = String(routeName || "").trim();
  if (cleaned === "Main Route") {
    return selectedRouteIndex;
  }

  const altIndex = parseAlternateRouteIndex(cleaned);
  if (altIndex === null) {
    return null;
  }

  const otherRouteIndices = Array.from({ length: routeCount }, (_, idx) => idx).filter(
    (idx) => idx !== selectedRouteIndex
  );
  return otherRouteIndices[altIndex - 1] ?? null;
}

function toFrontendRouteIndexFromRouteKey(routeKey, selectedRouteIndex, routeCount) {
  const normalized = String(routeKey || "").trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  if (normalized === "selected_route") {
    return selectedRouteIndex;
  }
  const match = /^alternate_(\d+)$/.exec(normalized);
  if (!match) {
    return null;
  }
  const altIndex = Number(match[1]);
  if (!Number.isFinite(altIndex) || altIndex < 1) {
    return null;
  }
  const otherRouteIndices = Array.from({ length: routeCount }, (_, idx) => idx).filter(
    (idx) => idx !== selectedRouteIndex
  );
  return otherRouteIndices[altIndex - 1] ?? null;
}

function normalizeTrafficLabel(level) {
  const normalized = String(level || "").trim().toLowerCase();
  if (normalized === "low") {
    return "Low";
  }
  if (normalized === "high") {
    return "High";
  }
  return "Medium";
}

function attachRouteDecisionIndices(routeDecision, routeList, selectedRouteIndex) {
  if (!routeDecision || !Array.isArray(routeDecision.all_routes_ranked)) {
    return routeDecision;
  }

  const allRanked = routeDecision.all_routes_ranked.map((item) => ({
    ...item,
    route_index: toFrontendRouteIndexFromRouteName(
      item.route_name,
      selectedRouteIndex,
      routeList.length
    ),
  }));

  const bestRoute = routeDecision.best_route
    ? {
        ...routeDecision.best_route,
        route_index: toFrontendRouteIndexFromRouteName(
          routeDecision.best_route.route_name,
          selectedRouteIndex,
          routeList.length
        ),
      }
    : null;

  const backupRoute = routeDecision.backup_route
    ? {
        ...routeDecision.backup_route,
        route_index: toFrontendRouteIndexFromRouteName(
          routeDecision.backup_route.route_name,
          selectedRouteIndex,
          routeList.length
        ),
      }
    : null;

  return {
    ...routeDecision,
    best_route: bestRoute,
    backup_route: backupRoute,
    all_routes_ranked: allRanked,
  };
}

function SuggestionList({ suggestions, onSelect }) {
  if (!suggestions.length) {
    return null;
  }

  return (
    <div className="suggestions-list">
      {suggestions.map((item, idx) => (
        <button
          key={`${item.label}-${idx}`}
          type="button"
          onClick={() => onSelect(item)}
          className="suggestion-item"
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

function AnalogTimePicker({ value, onChange }) {
  const parsed = parseTimeParts(value) || { hour: 9, minute: 0 };
  const [mode, setMode] = useState("hour");
  const { hour12, period } = hour24To12(parsed.hour);
  const activeMinute = Math.round(parsed.minute / 5) * 5 % 60;
  const handStep = mode === "hour" ? (hour12 % 12) * 5 : parsed.minute;
  const handRotation = handStep * 6;

  const updatePeriod = (nextPeriod) => {
    const nextHour = hour12To24(hour12, nextPeriod);
    onChange(toTimeString(nextHour, parsed.minute));
  };

  const updateHour = (nextHour12) => {
    const nextHour = hour12To24(nextHour12, period);
    onChange(toTimeString(nextHour, parsed.minute));
    setMode("minute");
  };

  const updateMinute = (nextMinute) => {
    onChange(toTimeString(parsed.hour, nextMinute));
  };

  const setNow = () => {
    const now = new Date();
    const roundedMinute = Math.round(now.getMinutes() / 5) * 5;
    if (roundedMinute >= 60) {
      const plusHour = (now.getHours() + 1) % 24;
      onChange(toTimeString(plusHour, 0));
      return;
    }
    onChange(toTimeString(now.getHours(), roundedMinute));
  };

  return (
    <div className="analog-time-picker">
      <div className="analog-time-top">
        <div className="analog-mode-tabs">
          <button
            type="button"
            className={mode === "hour" ? "analog-mode-btn active" : "analog-mode-btn"}
            onClick={() => setMode("hour")}
          >
            Hour
          </button>
          <button
            type="button"
            className={mode === "minute" ? "analog-mode-btn active" : "analog-mode-btn"}
            onClick={() => setMode("minute")}
          >
            Minute
          </button>
        </div>

        <div className="analog-time-readout">{value}</div>
      </div>

      <div className="analog-period-toggle">
        <button
          type="button"
          className={period === "AM" ? "period-btn active" : "period-btn"}
          onClick={() => updatePeriod("AM")}
        >
          AM
        </button>
        <button
          type="button"
          className={period === "PM" ? "period-btn active" : "period-btn"}
          onClick={() => updatePeriod("PM")}
        >
          PM
        </button>
      </div>

      <div className="analog-dial">
        <span className="analog-center-dot" />
        <span
          className="analog-hand"
          style={{ transform: `rotate(${handRotation}deg)` }}
          aria-hidden="true"
        />

        {(mode === "hour" ? HOUR_MARKERS : MINUTE_MARKERS).map((marker) => {
          const angle = marker.index * 30 - 90;
          const radians = angle * (Math.PI / 180);
          const radius = mode === "hour" ? 76 : 82;
          const x = Math.cos(radians) * radius;
          const y = Math.sin(radians) * radius;
          const selected =
            mode === "hour" ? marker.hour12 === hour12 : marker.minute === activeMinute;

          return (
            <button
              key={`${mode}-${marker.index}`}
              type="button"
              className={selected ? "dial-marker selected" : "dial-marker"}
              style={{
                left: `calc(50% + ${x}px)`,
                top: `calc(50% + ${y}px)`,
              }}
              onClick={() => {
                if (mode === "hour") {
                  updateHour(marker.hour12);
                } else {
                  updateMinute(marker.minute);
                }
              }}
            >
              {marker.label}
            </button>
          );
        })}
      </div>

      <div className="analog-time-actions">
        <button type="button" className="analog-action-btn" onClick={setNow}>
          Set Now
        </button>
        <input
          type="time"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="analog-time-fallback"
        />
      </div>
    </div>
  );
}

function AnalysisDashboardModal({
  open,
  onClose,
  analysis,
  arrivalTime,
  onSimulateTrafficSpike,
  simulationLoading,
  simulationResult,
}) {
  const [activeFeature, setActiveFeature] = useState("overview");

  useEffect(() => {
    if (open) {
      setActiveFeature("overview");
    }
  }, [open]);

  if (!open || !analysis) {
    return null;
  }

  const rankedRoutes = Array.isArray(analysis?.route_decision?.all_routes_ranked)
    ? analysis.route_decision.all_routes_ranked
    : [];
  const explanationPoints = Array.isArray(analysis?.explanation?.why_this_route)
    ? analysis.explanation.why_this_route
    : [];
  const arrivalProbability = Number(analysis?.arrival_probability);
  const arrivalProbabilityPercent = Number.isFinite(arrivalProbability)
    ? Math.round(arrivalProbability * 100)
    : null;
  const trafficConfidence = Number(analysis?.traffic_confidence);
  const parkingConfidence = Number(analysis?.parking_confidence);
  const parkingOptions = Array.isArray(analysis?.parking_options) ? analysis.parking_options : [];
  const bestParkingOption = analysis?.best_parking_option || null;
  const trafficTimeline = Array.isArray(analysis?.traffic_timeline) ? analysis.traffic_timeline : [];
  const TrafficTimelineComponent = window.TrafficTimeline;

  return ReactDOM.createPortal(
    <div className="analysis-modal-backdrop" onClick={onClose}>
      <div
        className="analysis-modal-glass"
        role="dialog"
        aria-modal="true"
        aria-label="AI Analysis Dashboard"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="analysis-modal-header">
          <h2>AI Analysis Dashboard</h2>
          <button type="button" className="analysis-close-btn" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="analysis-tab-bar">
          <button
            type="button"
            className={activeFeature === "overview" ? "analysis-tab-btn active" : "analysis-tab-btn"}
            onClick={() => setActiveFeature("overview")}
          >
            Overview
          </button>
          <button
            type="button"
            className={activeFeature === "decision" ? "analysis-tab-btn active" : "analysis-tab-btn"}
            onClick={() => setActiveFeature("decision")}
          >
            Feature 1: Decision
          </button>
          <button
            type="button"
            className={
              activeFeature === "explanation" ? "analysis-tab-btn active" : "analysis-tab-btn"
            }
            onClick={() => setActiveFeature("explanation")}
          >
            Feature 2: Explanation
          </button>
          <button
            type="button"
            className={
              activeFeature === "probability" ? "analysis-tab-btn active" : "analysis-tab-btn"
            }
            onClick={() => setActiveFeature("probability")}
          >
            Feature 3: Arrival
          </button>
          <button
            type="button"
            className={
              activeFeature === "confidence" ? "analysis-tab-btn active" : "analysis-tab-btn"
            }
            onClick={() => setActiveFeature("confidence")}
          >
            Feature 4: Confidence
          </button>
          <button
            type="button"
            className={
              activeFeature === "simulation" ? "analysis-tab-btn active" : "analysis-tab-btn"
            }
            onClick={() => setActiveFeature("simulation")}
          >
            Feature 5: Simulation
          </button>
          <button
            type="button"
            className={activeFeature === "parking" ? "analysis-tab-btn active" : "analysis-tab-btn"}
            onClick={() => setActiveFeature("parking")}
          >
            Feature 6: Parking
          </button>
          <button
            type="button"
            className={activeFeature === "timeline" ? "analysis-tab-btn active" : "analysis-tab-btn"}
            onClick={() => setActiveFeature("timeline")}
          >
            Feature 7: Timeline
          </button>
          <button
            type="button"
            className={activeFeature === "slots" ? "analysis-tab-btn active" : "analysis-tab-btn"}
            onClick={() => setActiveFeature("slots")}
          >
            Slots
          </button>
        </div>

        {activeFeature === "overview" ? (
          <>
            <div className="analysis-stats-grid">
              <div className="analysis-stat-card">
                <label>Predicted Future Traffic</label>
                <strong>{analysis.predicted_future_traffic}</strong>
              </div>
              <div className="analysis-stat-card">
                <label>Target Arrival</label>
                <strong>{analysis.target_arrival_time || arrivalTime}</strong>
              </div>
              <div className="analysis-stat-card">
                <label>Best Time To Leave</label>
                <strong>{analysis.recommended_departure_time}</strong>
              </div>
              <div className="analysis-stat-card">
                <label>Travel (with buffer)</label>
                <strong>
                  {analysis.estimated_travel_minutes
                    ? `${analysis.estimated_travel_minutes} min`
                    : "N/A"}
                </strong>
              </div>
              <div className="analysis-stat-card">
                <label>Parking Availability</label>
                <strong>{analysis.parking_availability}</strong>
              </div>
              <div className="analysis-stat-card">
                <label>Parking Suggestion</label>
                <strong>{analysis.parking_suggestion}</strong>
              </div>
            </div>

            <section className="analysis-block">
              <h4>Personalized Tip</h4>
              <p>{analysis.personalized_tip}</p>
            </section>
          </>
        ) : null}

        {activeFeature === "decision" ? (
          <>
            <section className="analysis-block">
              <h4>How Score Is Calculated</h4>
              <p className="analysis-formula">
                Decision Score = (Traffic Score x 0.4) + (Time Score x 0.3) + (Parking Score x
                0.2) + (Personalization Score x 0.1)
              </p>
              <p className="analysis-note-inline">
                Distance is used only as tie-break when all route scores are equal.
              </p>
              {analysis?.route_decision?.best_route ? (
                <p>
                  <strong>Best Route:</strong> {analysis.route_decision.best_route.route_name} (
                  {formatDecisionScore(analysis.route_decision.best_route.decision_score)})
                </p>
              ) : null}
              {analysis?.route_decision?.backup_route ? (
                <p>
                  <strong>Backup Route:</strong> {analysis.route_decision.backup_route.route_name} (
                  {formatDecisionScore(analysis.route_decision.backup_route.decision_score)})
                </p>
              ) : null}
            </section>

            {rankedRoutes.length ? (
              <section className="analysis-block">
                <h4>Route Ranking Breakdown</h4>
                <div className="analysis-rank-grid">
                  {rankedRoutes.map((item, idx) => (
                    <div key={`${item.route_name}-${idx}`} className="analysis-rank-item">
                      <div className="analysis-rank-head">
                        <strong>
                          #{idx + 1} {item.route_name}
                        </strong>
                        <span>Score: {formatDecisionScore(item.decision_score)}</span>
                      </div>
                      <div className="analysis-rank-meta">
                        <span>ETA: {item.travel_time_min} min</span>
                        <span>Distance: {Number(item.distance_km).toFixed(1)} km</span>
                        <span>Traffic: {item.predicted_traffic}</span>
                      </div>
                      <div className="analysis-rank-meta">
                        <span>Traffic Score: {formatDecisionScore(item.traffic_score)}</span>
                        <span>Time Score: {formatDecisionScore(item.time_score)}</span>
                        <span>Parking Score: {formatDecisionScore(item.parking_score)}</span>
                        <span>
                          Personalization: {formatDecisionScore(item.personalization_score)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}
          </>
        ) : null}

        {activeFeature === "explanation" ? (
          <section className="analysis-block">
            <h4>Explanation Engine</h4>
            {explanationPoints.length ? (
              <ul className="analysis-list">
                {explanationPoints.map((reason, idx) => (
                  <li key={`why-${idx}`}>{reason}</li>
                ))}
              </ul>
            ) : (
              <p>No detailed explanation available for this run.</p>
            )}
            <p>
              <strong>Risk Warning:</strong> {analysis?.explanation?.risk_warning || "N/A"}
            </p>
          </section>
        ) : null}

        {activeFeature === "probability" ? (
          <section className="analysis-block">
            <h4>Arrival Probability</h4>
            <div className="analysis-prob-card">
              <strong>
                {arrivalProbabilityPercent !== null ? `${arrivalProbabilityPercent}%` : "N/A"}
              </strong>
              <span>{analysis.arrival_probability_label || "Probability label unavailable."}</span>
            </div>
            <div className="analysis-rank-meta">
              <span>Buffer: {analysis.departure_buffer_minutes || 0} min</span>
              <span>Travel Time: {analysis.estimated_travel_minutes || "N/A"} min</span>
              <span>Traffic: {analysis.predicted_future_traffic}</span>
            </div>
          </section>
        ) : null}

        {activeFeature === "confidence" ? (
          <section className="analysis-block">
            <h4>Confidence Scores</h4>
            <div className="analysis-confidence-grid">
              <div className="analysis-confidence-item">
                <label>Traffic Confidence</label>
                <strong>
                  {Number.isFinite(trafficConfidence)
                    ? `${Math.round(trafficConfidence * 100)}%`
                    : "N/A"}
                </strong>
                <div className="analysis-progress-track">
                  <span
                    className="analysis-progress-fill"
                    style={{ width: `${Math.round((trafficConfidence || 0) * 100)}%` }}
                  />
                </div>
              </div>
              <div className="analysis-confidence-item">
                <label>Parking Confidence</label>
                <strong>
                  {Number.isFinite(parkingConfidence)
                    ? `${Math.round(parkingConfidence * 100)}%`
                    : "N/A"}
                </strong>
                <div className="analysis-progress-track">
                  <span
                    className="analysis-progress-fill"
                    style={{ width: `${Math.round((parkingConfidence || 0) * 100)}%` }}
                  />
                </div>
              </div>
            </div>
          </section>
        ) : null}

        {activeFeature === "simulation" ? (
          <section className="analysis-block">
            <h4>Real-Time Simulation Engine</h4>
            <p className="analysis-note-inline">
              Trigger a sudden event and see reroute guidance instantly.
            </p>
            <button
              type="button"
              className="simulate-btn"
              disabled={simulationLoading}
              onClick={onSimulateTrafficSpike}
            >
              {simulationLoading ? "Simulating..." : "Simulate Traffic Spike"}
            </button>

            {simulationResult ? (
              <div className="simulation-result-box">
                <p>
                  <strong>Summary:</strong> {simulationResult.simulation_summary}
                </p>
                <p>
                  <strong>Reroute Recommendation:</strong>{" "}
                  {simulationResult.reroute_recommendation}
                </p>
                <div className="simulation-route-grid">
                  {(simulationResult.updated_routes || []).map((item, idx) => (
                    <div
                      key={`${item.route_name}-${idx}`}
                      className={`simulation-route-item ${item.is_now_best ? "is-now-best" : ""}`}
                    >
                      <strong>{item.route_name}</strong>
                      <span>
                        {item.original_duration_min} min -> {item.updated_duration_min} min
                      </span>
                      <span>
                        Traffic: {item.original_traffic} -> {item.updated_traffic}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="muted-text">No simulation run yet.</p>
            )}
          </section>
        ) : null}

        {activeFeature === "parking" ? (
          <section className="analysis-block">
            <h4>Best Parking Nearby</h4>
            {parkingOptions.length ? (
              <div className="parking-option-grid">
                {parkingOptions.map((option, idx) => {
                  const isBest = bestParkingOption?.name === option.name;
                  return (
                    <div
                      key={`${option.name}-${idx}`}
                      className={`parking-option-card ${isBest ? "is-best" : ""}`}
                    >
                      <div className="parking-head">
                        <strong>{option.name}</strong>
                        {isBest ? <span className="parking-best-pill">Best</span> : null}
                      </div>
                      <p>Occupancy: {Math.round(Number(option.predicted_occupancy) * 100)}%</p>
                      <p>
                        Availability: {Math.round(Number(option.availability_probability) * 100)}%
                      </p>
                      <p>Walking Time: {option.walking_time_min} min</p>
                      <p>
                        Score: {formatDecisionScore(option.parking_score)} |{" "}
                        {option.recommendation_label}
                      </p>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="muted-text">Parking options are not available.</p>
            )}
          </section>
        ) : null}

        {activeFeature === "timeline" ? (
          <section className="analysis-block">
            <h4>Timeline Traffic Visualization</h4>
            {TrafficTimelineComponent ? (
              <TrafficTimelineComponent
                timeline={trafficTimeline}
                recommendedDeparture={analysis?.recommended_departure_marker}
                arrivalMarker={analysis?.arrival_marker}
              />
            ) : (
              <p className="muted-text">Timeline component unavailable.</p>
            )}
          </section>
        ) : null}

        {activeFeature === "slots" ? (
          <section className="analysis-block">
            <h4>15-Minute Slots Until Arrival</h4>
            <div className="analysis-slot-wrap">
              {(analysis.next_time_slot_recommendations || []).map((slot, idx) => (
                <span key={`${slot.time}-${idx}`} className="slot-chip">
                  {slot.time} - {slot.traffic}
                </span>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </div>,
    document.body
  );
}

function App() {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const routeLayerRef = useRef(null);
  const markerLayerRef = useRef(null);
  const tileLayerRef = useRef(null);
  const tileProbeTimeoutRef = useRef(null);
  const invalidateTimersRef = useRef([]);
  const resizeObserverRef = useRef(null);
  const mapPickModeRef = useRef("off");

  const [userId, setUserId] = useState("u1");
  const [startQuery, setStartQuery] = useState("Connaught Place, New Delhi");
  const [endQuery, setEndQuery] = useState("India Gate, New Delhi");
  const [arrivalTime, setArrivalTime] = useState("09:00");
  const [mapPickMode, setMapPickMode] = useState("off");
  const [mapPickLoading, setMapPickLoading] = useState(false);
  const [startLocation, setStartLocation] = useState(null);
  const [endLocation, setEndLocation] = useState(null);
  const [startSuggestions, setStartSuggestions] = useState([]);
  const [endSuggestions, setEndSuggestions] = useState([]);

  const [routes, setRoutes] = useState([]);
  const [selectedRouteIndex, setSelectedRouteIndex] = useState(0);
  const [bestRouteIndex, setBestRouteIndex] = useState(0);
  const [analysisRouteIndex, setAnalysisRouteIndex] = useState(0);
  const [simulatedBestRouteIndex, setSimulatedBestRouteIndex] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [isAnalysisModalOpen, setIsAnalysisModalOpen] = useState(false);
  const [simulationResult, setSimulationResult] = useState(null);

  const [routingLoading, setRoutingLoading] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [simulationLoading, setSimulationLoading] = useState(false);
  const [mapReady, setMapReady] = useState(false);
  const [mapStatusMessage, setMapStatusMessage] = useState("Loading map...");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    if (!isAnalysisModalOpen) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        setIsAnalysisModalOpen(false);
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isAnalysisModalOpen]);

  useEffect(() => {
    mapPickModeRef.current = mapPickMode;
  }, [mapPickMode]);

  useEffect(() => {
    let active = true;

    const clearInvalidateTimers = () => {
      invalidateTimersRef.current.forEach((timerId) => clearTimeout(timerId));
      invalidateTimersRef.current = [];
    };

    const scheduleInvalidate = () => {
      clearInvalidateTimers();
      [0, 200, 700, 1400].forEach((delayMs) => {
        const timerId = setTimeout(() => {
          if (mapRef.current) {
            mapRef.current.invalidateSize();
            if (delayMs >= 700) {
              const center = mapRef.current.getCenter();
              const zoom = mapRef.current.getZoom();
              mapRef.current.setView(center, zoom, { animate: false });
            }
          }
        }, delayMs);
        invalidateTimersRef.current.push(timerId);
      });
    };

    const initMap = async () => {
      setMapReady(false);
      setMapStatusMessage("Loading map library...");

      try {
        await ensureLeafletLoaded();
      } catch (error) {
        if (active) {
          setMapReady(false);
          setMapStatusMessage(
            "Map library failed to load. Check internet and refresh the page."
          );
        }
        return;
      }

      if (!active || mapRef.current || !mapContainerRef.current) {
        return;
      }

      // Wait for layout to settle so Leaflet initializes with correct size.
      await new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve))
      );
      if (!active || !mapContainerRef.current) {
        return;
      }
      if (mapContainerRef.current.clientHeight < 120) {
        await new Promise((resolve) => setTimeout(resolve, 220));
      }

      const map = window.L.map(mapContainerRef.current, { zoomControl: true }).setView(
        DEFAULT_CENTER,
        12
      );

      map.on("click", async (event) => {
        const currentMode = mapPickModeRef.current;
        if (currentMode !== "start" && currentMode !== "end") {
          return;
        }

        const pickedLat = Number(event.latlng.lat);
        const pickedLng = Number(event.latlng.lng);
        const defaultLabel = fallbackCoordinateLabel(pickedLat, pickedLng);

        setErrorMessage("");
        setMapPickLoading(true);
        try {
          let pickedLabel = defaultLabel;
          try {
            pickedLabel = await reverseGeocode(pickedLat, pickedLng);
          } catch (error) {
            // Keep coordinate fallback when reverse geocoding fails.
          }

          const pickedLocation = {
            label: pickedLabel,
            lat: pickedLat,
            lng: pickedLng,
          };

          if (currentMode === "start") {
            setStartLocation(pickedLocation);
            setStartQuery(pickedLabel);
            setStartSuggestions([]);
          } else {
            setEndLocation(pickedLocation);
            setEndQuery(pickedLabel);
            setEndSuggestions([]);
          }

          // Reset route/analysis after manual point updates.
          setRoutes([]);
          setAnalysis(null);
          setSimulationResult(null);
          setSelectedRouteIndex(0);
          setBestRouteIndex(0);
          setSimulatedBestRouteIndex(null);
          setAnalysisRouteIndex(0);
          setMapPickMode("off");
        } finally {
          setMapPickLoading(false);
        }
      });

      mapRef.current = map;
      routeLayerRef.current = window.L.layerGroup().addTo(map);
      markerLayerRef.current = window.L.layerGroup().addTo(map);

      const loadProviderAt = (providerIndex) => {
        if (!active || !mapRef.current) {
          return;
        }

        const provider = TILE_PROVIDERS[providerIndex];
        if (!provider) {
          setMapReady(false);
          setMapStatusMessage(
            "Map tiles are blocked on this network. Try VPN or different internet."
          );
          return;
        }

        setMapStatusMessage(`Loading map tiles (${provider.name})...`);
        if (tileProbeTimeoutRef.current) {
          clearTimeout(tileProbeTimeoutRef.current);
        }
        if (tileLayerRef.current) {
          mapRef.current.removeLayer(tileLayerRef.current);
        }

        let tileLoaded = false;
        let tileErrorCount = 0;
        const layer = window.L.tileLayer(provider.url, {
          ...provider.options,
          crossOrigin: true,
        });

        layer.on("tileload", () => {
          tileLoaded = true;
          if (!mapReady) {
            setMapReady(true);
          }
          setMapStatusMessage("");
          scheduleInvalidate();
        });

        layer.on("tileerror", () => {
          tileErrorCount += 1;
          if (tileErrorCount >= 5 && !tileLoaded) {
            loadProviderAt(providerIndex + 1);
          }
        });

        tileLayerRef.current = layer;
        layer.addTo(mapRef.current);

        // If no tile appears quickly, auto-switch provider.
        tileProbeTimeoutRef.current = setTimeout(() => {
          if (!tileLoaded) {
            loadProviderAt(providerIndex + 1);
          }
        }, 4500);
      };

      loadProviderAt(0);
      scheduleInvalidate();

      // Force layout refresh for edge cases where container size settles late.
      setTimeout(() => {
        if (mapRef.current) {
          mapRef.current.invalidateSize();
        }
      }, 120);

      if (window.ResizeObserver && mapContainerRef.current) {
        resizeObserverRef.current = new ResizeObserver(() => {
          if (mapRef.current) {
            mapRef.current.invalidateSize();
          }
        });
        resizeObserverRef.current.observe(mapContainerRef.current);
      }
    };

    initMap();

    const onResize = () => {
      if (mapRef.current) {
        mapRef.current.invalidateSize();
      }
    };
    window.addEventListener("resize", onResize);

    return () => {
      active = false;
      window.removeEventListener("resize", onResize);
      if (tileProbeTimeoutRef.current) {
        clearTimeout(tileProbeTimeoutRef.current);
      }
      clearInvalidateTimers();
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
      }
      if (tileLayerRef.current && mapRef.current) {
        mapRef.current.removeLayer(tileLayerRef.current);
      }
      if (mapRef.current) {
        mapRef.current.remove();
      }
      setMapReady(false);
      setMapStatusMessage("Loading map...");
      mapRef.current = null;
      routeLayerRef.current = null;
      markerLayerRef.current = null;
      tileLayerRef.current = null;
      tileProbeTimeoutRef.current = null;
      resizeObserverRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (startQuery.trim().length < 3) {
      setStartSuggestions([]);
      return;
    }

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const suggestions = await searchPlaces(startQuery, controller.signal);
        setStartSuggestions(suggestions);
      } catch (error) {
        if (error.name !== "AbortError") {
          setStartSuggestions([]);
        }
      }
    }, 300);

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [startQuery]);

  useEffect(() => {
    if (endQuery.trim().length < 3) {
      setEndSuggestions([]);
      return;
    }

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const suggestions = await searchPlaces(endQuery, controller.signal);
        setEndSuggestions(suggestions);
      } catch (error) {
        if (error.name !== "AbortError") {
          setEndSuggestions([]);
        }
      }
    }, 300);

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [endQuery]);

  useEffect(() => {
    if (!mapRef.current || !routeLayerRef.current || !markerLayerRef.current) {
      return;
    }

    routeLayerRef.current.clearLayers();
    markerLayerRef.current.clearLayers();

    if (startLocation) {
      window.L.circleMarker([startLocation.lat, startLocation.lng], {
        radius: 8,
        color: "#0b6bcb",
        weight: 2,
        fillColor: "#55a7ff",
        fillOpacity: 0.9,
      })
        .bindTooltip("Start", { direction: "top" })
        .addTo(markerLayerRef.current);
    }
    if (endLocation) {
      window.L.circleMarker([endLocation.lat, endLocation.lng], {
        radius: 8,
        color: "#b42318",
        weight: 2,
        fillColor: "#f97066",
        fillOpacity: 0.92,
      })
        .bindTooltip("Destination", { direction: "top" })
        .addTo(markerLayerRef.current);
    }

    if (!routes.length) {
      return;
    }

    routes.forEach((route, idx) => {
      const isSelected = idx === selectedRouteIndex;
      const polyline = window.L.polyline(route.coordinates, {
        color: route.color,
        weight: isSelected ? 7 : 4,
        opacity: isSelected ? 0.92 : 0.55,
        dashArray: isSelected ? null : "8, 8",
      });
      polyline.addTo(routeLayerRef.current);
      polyline.on("click", () => setSelectedRouteIndex(idx));
    });

    const focusRoute = routes[selectedRouteIndex] || routes[0];
    if (focusRoute && focusRoute.coordinates.length) {
      mapRef.current.fitBounds(window.L.latLngBounds(focusRoute.coordinates), {
        padding: [40, 40],
      });
    }
  }, [routes, selectedRouteIndex, startLocation, endLocation]);

  const runSmartAnalysis = async (resolvedStart, resolvedEnd, routeList, routeIndex) => {
    const selectedRoute = routeList[routeIndex] || routeList[0];
    const alternateRoutes = routeList.filter((_, idx) => idx !== routeIndex);
    const preferredArrivalHour = parseHourFromTime(arrivalTime);
    const currentTimeForModel = buildLocalNowIso();

    const payload = {
      user_id: userId || "u1",
      start_lat: resolvedStart.lat,
      start_lng: resolvedStart.lng,
      end_lat: resolvedEnd.lat,
      end_lng: resolvedEnd.lng,
      start_address: resolvedStart.label,
      destination_address: resolvedEnd.label,
      selected_route_distance_km: Number(selectedRoute.distanceKm.toFixed(2)),
      selected_route_duration_min: Math.max(1, Math.round(selectedRoute.durationMin)),
      alternate_route_distances_km: alternateRoutes.map((r) =>
        Number(r.distanceKm.toFixed(2))
      ),
      alternate_route_durations_min: alternateRoutes.map((r) =>
        Math.max(1, Math.round(r.durationMin))
      ),
    };
    if (preferredArrivalHour !== null) {
      payload.preferred_arrival_hour = preferredArrivalHour;
    }
    if (arrivalTime) {
      payload.arrival_by_time = arrivalTime;
    }
    if (currentTimeForModel) {
      payload.current_time = currentTimeForModel;
    }

    setAnalysisRouteIndex(routeIndex);
    setSimulationResult(null);
    setSimulatedBestRouteIndex(null);
    setAnalysisLoading(true);
    try {
      const response = await window.ApiService.smartRouteAnalysis(payload);
      const responseWithIndexedDecision = {
        ...response,
        route_decision: attachRouteDecisionIndices(
          response?.route_decision,
          routeList,
          routeIndex
        ),
      };
      const missingArrivalFields =
        responseWithIndexedDecision?.target_arrival_time == null ||
        responseWithIndexedDecision?.estimated_travel_minutes == null ||
        responseWithIndexedDecision?.departure_buffer_minutes == null;
      const backendSlots = Array.isArray(
        responseWithIndexedDecision?.next_time_slot_recommendations
      )
        ? responseWithIndexedDecision.next_time_slot_recommendations
        : [];
      const slotFallback = buildArrivalSlotFallback(
        arrivalTime,
        responseWithIndexedDecision?.predicted_future_traffic
      );
      const shouldUseSlotFallback =
        Array.isArray(slotFallback) &&
        slotFallback.length > 0 &&
        backendSlots.length < slotFallback.length;

      let finalAnalysis = responseWithIndexedDecision;
      if (missingArrivalFields) {
        const fallback = computeArrivalAwareFallback({
          arrivalTime,
          routeDurationMin: selectedRoute.durationMin,
          predictedTrafficLevel: responseWithIndexedDecision?.predicted_future_traffic,
        });
        const updatedTip =
          fallback && typeof responseWithIndexedDecision?.personalized_tip === "string"
            ? responseWithIndexedDecision.personalized_tip.replace(
                /\b\d{2}:\d{2}\b/g,
                fallback.recommended_departure_time
              )
            : responseWithIndexedDecision?.personalized_tip;
        finalAnalysis = fallback
          ? {
              ...responseWithIndexedDecision,
              ...fallback,
              personalized_tip: updatedTip,
              next_time_slot_recommendations: shouldUseSlotFallback
                ? slotFallback
                : backendSlots,
            }
          : responseWithIndexedDecision;
      } else {
        finalAnalysis = {
          ...responseWithIndexedDecision,
          next_time_slot_recommendations: shouldUseSlotFallback
            ? slotFallback
            : backendSlots,
        };
      }
      setAnalysis(finalAnalysis);
      setIsAnalysisModalOpen(true);
    } finally {
      setAnalysisLoading(false);
    }
  };

  const handleSimulateTrafficSpike = async () => {
    if (!analysis || !routes.length) {
      setErrorMessage("Run AI analysis first, then simulate event.");
      return;
    }

    setErrorMessage("");
    setSimulationLoading(true);
    try {
      const payload = {
        event_type: "traffic_spike",
        affected_route: "selected_route",
        delay_minutes: 12,
        selected_route_summary: analysis.selected_route_summary,
        alternate_route_summaries: analysis.alternate_route_summaries,
        current_predicted_traffic: analysis.predicted_future_traffic,
      };
      const result = await window.ApiService.simulateEvent(payload);
      setSimulationResult(result);

      setRoutes((prevRoutes) => {
        const updatedByIndex = new Map();
        (result.updated_routes || []).forEach((item) => {
          const routeIdx = toFrontendRouteIndexFromRouteName(
            item.route_name,
            analysisRouteIndex,
            prevRoutes.length
          );
          if (routeIdx !== null) {
            updatedByIndex.set(routeIdx, item);
          }
        });

        return prevRoutes.map((route, idx) => {
          const update = updatedByIndex.get(idx);
          if (!update) {
            return route;
          }

          const updatedTraffic = normalizeTrafficLabel(update.updated_traffic);
          return {
            ...route,
            durationMin: Math.max(1, Number(update.updated_duration_min) || route.durationMin),
            trafficLevel: updatedTraffic,
            color: TRAFFIC_COLOR_BY_LEVEL[updatedTraffic],
          };
        });
      });

      const recommendedIdx = toFrontendRouteIndexFromRouteKey(
        result.reroute_recommendation,
        analysisRouteIndex,
        routes.length
      );
      if (recommendedIdx !== null) {
        setSimulatedBestRouteIndex(recommendedIdx);
        setBestRouteIndex(recommendedIdx);
      }
    } catch (error) {
      setErrorMessage(error.message || "Failed to simulate traffic event.");
    } finally {
      setSimulationLoading(false);
    }
  };

  const handleShowRoutes = async () => {
    setErrorMessage("");
    setIsAnalysisModalOpen(false);
    setRoutingLoading(true);
    try {
      const resolvedStart = startLocation || (await geocodeSinglePlace(startQuery));
      const resolvedEnd = endLocation || (await geocodeSinglePlace(endQuery));

      setStartLocation(resolvedStart);
      setEndLocation(resolvedEnd);
      setStartQuery(resolvedStart.label);
      setEndQuery(resolvedEnd.label);
      setStartSuggestions([]);
      setEndSuggestions([]);

      const routeList = await fetchRouteAlternatives(resolvedStart, resolvedEnd);
      const bestIdx = findBestRouteIndex(routeList);

      setRoutes(routeList);
      setBestRouteIndex(bestIdx);
      setSelectedRouteIndex(bestIdx);

      await runSmartAnalysis(resolvedStart, resolvedEnd, routeList, bestIdx);
    } catch (error) {
      setErrorMessage(error.message || "Failed to build route.");
    } finally {
      setRoutingLoading(false);
    }
  };

  const handleAnalyzeSelectedRoute = async () => {
    if (!routes.length || !startLocation || !endLocation) {
      setErrorMessage("Please generate a route first.");
      return;
    }

    setErrorMessage("");
    setIsAnalysisModalOpen(false);
    try {
      await runSmartAnalysis(startLocation, endLocation, routes, selectedRouteIndex);
    } catch (error) {
      setErrorMessage(error.message || "Failed to run AI route analysis.");
    }
  };

  const hasAnalysis = Boolean(analysis);

  return (
    <div className="map-app-shell">
      <div className="map-canvas" ref={mapContainerRef} />
      {(!mapReady || mapStatusMessage) && <div className="map-status">{mapStatusMessage}</div>}

      <aside className="overlay-panel">
        <header className="panel-header">
          <h1>Smart Navigation AI</h1>
          <p>Map-first route planning with traffic, departure, parking, and personalization insights.</p>
        </header>

        <div className="control-block">
          <label>User ID</label>
          <input value={userId} onChange={(event) => setUserId(event.target.value)} />
        </div>

        <div className="control-block">
          <label>Starting Point</label>
          <input
            value={startQuery}
            onChange={(event) => {
              setStartQuery(event.target.value);
              setStartLocation(null);
            }}
            placeholder="Search start location"
          />
          <SuggestionList
            suggestions={startSuggestions}
            onSelect={(item) => {
              setStartLocation(item);
              setStartQuery(item.label);
              setStartSuggestions([]);
            }}
          />
        </div>

        <div className="control-block">
          <label>Destination</label>
          <input
            value={endQuery}
            onChange={(event) => {
              setEndQuery(event.target.value);
              setEndLocation(null);
            }}
            placeholder="Search destination"
          />
          <SuggestionList
            suggestions={endSuggestions}
            onSelect={(item) => {
              setEndLocation(item);
              setEndQuery(item.label);
              setEndSuggestions([]);
            }}
          />
        </div>

        <div className="control-block">
          <label>Arrival Time (Reach By)</label>
          <AnalogTimePicker value={arrivalTime} onChange={setArrivalTime} />
          <p className="control-note">
            AI uses this time as your target arrival (hour-level for MVP model).
          </p>
        </div>

        <div className="control-block map-pick-block">
          <label>Select Points By Clicking Map</label>
          <div className="map-pick-buttons">
            <button
              type="button"
              className={mapPickMode === "start" ? "map-pick-btn active" : "map-pick-btn"}
              onClick={() => setMapPickMode(mapPickMode === "start" ? "off" : "start")}
            >
              {mapPickMode === "start" ? "Click Map: Start" : "Pick Start on Map"}
            </button>
            <button
              type="button"
              className={mapPickMode === "end" ? "map-pick-btn active" : "map-pick-btn"}
              onClick={() => setMapPickMode(mapPickMode === "end" ? "off" : "end")}
            >
              {mapPickMode === "end" ? "Click Map: Destination" : "Pick Destination on Map"}
            </button>
          </div>
          <p className="control-note">
            {mapPickLoading
              ? "Capturing selected point..."
              : mapPickMode === "off"
              ? "Choose Start or Destination, then click on map."
              : mapPickMode === "start"
              ? "Map click mode active: select Starting Point."
              : "Map click mode active: select Destination."}
          </p>
        </div>

        <div className="button-group">
          <button type="button" onClick={handleShowRoutes} disabled={routingLoading}>
            {routingLoading ? "Loading Routes..." : "Show Routes + AI Analysis"}
          </button>
          <button
            type="button"
            className="secondary-btn"
            onClick={handleAnalyzeSelectedRoute}
            disabled={analysisLoading || !routes.length}
          >
            {analysisLoading ? "Analyzing..." : "Analyze Selected Route"}
          </button>
          <button
            type="button"
            className="tertiary-btn"
            onClick={handleSimulateTrafficSpike}
            disabled={simulationLoading || !analysis}
          >
            {simulationLoading ? "Simulating..." : "Simulate Traffic Spike"}
          </button>
        </div>

        {errorMessage ? <div className="error-box">{errorMessage}</div> : null}

        <section className="section-card">
          <h3>Route Options</h3>
          {!routes.length ? (
            <p className="muted-text">Select start and destination to view main and alternate routes.</p>
          ) : (
            <>
              <p className="context-note">Showing {routes.length} unique possible route options.</p>
              <div className="route-list">
                {routes.map((route, idx) => {
                  const active = idx === selectedRouteIndex;
                  const isBest = idx === bestRouteIndex;
                  const isSimulatedBest = idx === simulatedBestRouteIndex;
                  return (
                    <button
                      key={`${route.routeName}-${idx}`}
                      type="button"
                      className={`route-item ${active ? "active-route" : ""}`}
                      onClick={() => setSelectedRouteIndex(idx)}
                    >
                      <div className="route-item-header">
                        <strong>{route.routeName}</strong>
                        <span style={{ color: route.color }}>
                          Current: {route.trafficLevel}
                        </span>
                    </div>
                    {isBest ? <span className="best-route-tag">Best Route</span> : null}
                    {isSimulatedBest ? (
                      <span className="sim-best-route-tag">Simulation Best</span>
                    ) : null}
                    <small>
                      {formatDistance(route.distanceKm)} | {formatDuration(route.durationMin)}
                    </small>
                  </button>
                );
                })}
              </div>
            </>
          )}
        </section>

        <section className="section-card">
          <h3>Analysis Dashboard</h3>
          {!hasAnalysis ? (
            <p className="muted-text">
              Click `Show Routes + AI Analysis` to open the full AI dashboard.
            </p>
          ) : (
            <div className="insights-stack">
              <p className="muted-text">
                Latest analysis is ready. Open the detailed full-screen dashboard.
              </p>
              {simulationResult?.simulation_summary ? (
                <p className="simulation-summary-inline">{simulationResult.simulation_summary}</p>
              ) : null}
              <button
                type="button"
                className="open-analysis-btn"
                onClick={() => setIsAnalysisModalOpen(true)}
              >
                Open AI Dashboard
              </button>
            </div>
          )}
        </section>
      </aside>

      <AnalysisDashboardModal
        open={isAnalysisModalOpen && hasAnalysis}
        onClose={() => setIsAnalysisModalOpen(false)}
        analysis={analysis}
        arrivalTime={arrivalTime}
        onSimulateTrafficSpike={handleSimulateTrafficSpike}
        simulationLoading={simulationLoading}
        simulationResult={simulationResult}
      />
    </div>
  );
}

window.App = App;
