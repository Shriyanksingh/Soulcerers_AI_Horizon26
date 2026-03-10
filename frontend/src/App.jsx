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

async function fetchRouteAlternatives(start, end) {
  const url = `https://router.project-osrm.org/route/v1/driving/${start.lng},${start.lat};${end.lng},${end.lat}?overview=full&alternatives=true&steps=false&geometries=geojson`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error("Could not fetch routes. Please retry.");
  }
  const payload = await response.json();
  if (payload.code !== "Ok" || !payload.routes || payload.routes.length === 0) {
    throw new Error("No driving route found for these points.");
  }

  return payload.routes.map((route, index) => {
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
  const [analysis, setAnalysis] = useState(null);

  const [routingLoading, setRoutingLoading] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [mapReady, setMapReady] = useState(false);
  const [mapStatusMessage, setMapStatusMessage] = useState("Loading map...");
  const [errorMessage, setErrorMessage] = useState("");

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
          setSelectedRouteIndex(0);
          setBestRouteIndex(0);
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

    setAnalysisLoading(true);
    try {
      const response = await window.ApiService.smartRouteAnalysis(payload);
      const missingArrivalFields =
        response?.target_arrival_time == null ||
        response?.estimated_travel_minutes == null ||
        response?.departure_buffer_minutes == null;
      const backendSlots = Array.isArray(response?.next_time_slot_recommendations)
        ? response.next_time_slot_recommendations
        : [];
      const slotFallback = buildArrivalSlotFallback(
        arrivalTime,
        response?.predicted_future_traffic
      );
      const shouldUseSlotFallback =
        Array.isArray(slotFallback) &&
        slotFallback.length > 0 &&
        backendSlots.length < slotFallback.length;

      if (missingArrivalFields) {
        const fallback = computeArrivalAwareFallback({
          arrivalTime,
          routeDurationMin: selectedRoute.durationMin,
          predictedTrafficLevel: response?.predicted_future_traffic,
        });
        const updatedTip =
          fallback && typeof response?.personalized_tip === "string"
            ? response.personalized_tip.replace(
                /\b\d{2}:\d{2}\b/g,
                fallback.recommended_departure_time
              )
            : response?.personalized_tip;
        setAnalysis(
          fallback
            ? {
                ...response,
                ...fallback,
                personalized_tip: updatedTip,
                next_time_slot_recommendations: shouldUseSlotFallback
                  ? slotFallback
                  : backendSlots,
              }
            : response
        );
      } else {
        setAnalysis({
          ...response,
          next_time_slot_recommendations: shouldUseSlotFallback
            ? slotFallback
            : backendSlots,
        });
      }
    } finally {
      setAnalysisLoading(false);
    }
  };

  const handleShowRoutes = async () => {
    setErrorMessage("");
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
    try {
      await runSmartAnalysis(startLocation, endLocation, routes, selectedRouteIndex);
    } catch (error) {
      setErrorMessage(error.message || "Failed to run AI route analysis.");
    }
  };

  const selectedRoute = routes[selectedRouteIndex] || null;
  const bestRoute = routes[bestRouteIndex] || null;
  const selectedIsBest = selectedRouteIndex === bestRouteIndex;

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
        </div>

        {errorMessage ? <div className="error-box">{errorMessage}</div> : null}

        <section className="section-card">
          <h3>Route Options</h3>
          {!routes.length ? (
            <p className="muted-text">Select start and destination to view main and alternate routes.</p>
          ) : (
            <div className="route-list">
              {routes.map((route, idx) => {
                const active = idx === selectedRouteIndex;
                const isBest = idx === bestRouteIndex;
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
                    {analysis && active ? (
                      <span className="future-route-tag">
                        Future (AI): {analysis.predicted_future_traffic}
                      </span>
                    ) : null}
                    <small>
                      {formatDistance(route.distanceKm)} | {formatDuration(route.durationMin)}
                    </small>
                  </button>
                );
              })}
            </div>
          )}
        </section>

        <section className="section-card">
          <h3>AI Insights</h3>
          {!analysis ? (
            <p className="muted-text">Run route analysis to see traffic prediction, best departure, parking, and personalized tip.</p>
          ) : (
            <div className="insights-stack">
              <p className="context-note">
                Route cards show current traffic from route speed. AI insight below is future prediction.
              </p>
              <p>
                <strong>Predicted Future Traffic:</strong> {analysis.predicted_future_traffic}
              </p>
              <p>
                <strong>Target Arrival Time:</strong>{" "}
                {analysis.target_arrival_time || arrivalTime}
              </p>
              <p>
                <strong>Best Time To Leave:</strong> {analysis.recommended_departure_time}
              </p>
              <p>
                <strong>Estimated Travel (incl. buffer):</strong>{" "}
                {analysis.estimated_travel_minutes
                  ? `${analysis.estimated_travel_minutes} min`
                  : "N/A"}
              </p>
              <p>
                <strong>Delay Buffer Added:</strong>{" "}
                {analysis.departure_buffer_minutes
                  ? `${analysis.departure_buffer_minutes} min`
                  : "N/A"}
              </p>
              {analysis.is_running_late ? (
                <p className="late-note">
                  You are already behind target arrival. Leave immediately for best chance.
                </p>
              ) : null}
              <p>
                <strong>Recommended Traffic Level:</strong> {analysis.recommended_traffic_level}
              </p>
              <p>
                <strong>Parking Availability:</strong> {analysis.parking_availability}
              </p>
              <p>
                <strong>Parking Suggestion:</strong> {analysis.parking_suggestion}
              </p>
              <p>
                <strong>Personalized Tip:</strong> {analysis.personalized_tip}
              </p>
              <div className="slot-box">
                <strong>15-Minute Slots Until Arrival</strong>
                <div className="slot-chip-wrap">
                  {(analysis.next_time_slot_recommendations || []).map((slot, idx) => (
                    <span key={`${slot.time}-${idx}`} className="slot-chip">
                      {slot.time} - {slot.traffic}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}
        </section>

        {selectedRoute ? (
          <section className="section-card compact-card">
            <h3>Selected Route Snapshot</h3>
            <p>
              {formatDistance(selectedRoute.distanceKm)} | {formatDuration(selectedRoute.durationMin)} |{" "}
              <span style={{ color: selectedRoute.color }}>{selectedRoute.trafficLevel}</span>
            </p>
            <p className="best-route-line">
              {selectedIsBest
                ? "This is the best route based on ETA, traffic, and distance."
                : `Best route is ${bestRoute?.routeName || "another option"} (faster/cleaner).`}
            </p>
          </section>
        ) : null}
      </aside>
    </div>
  );
}

window.App = App;
