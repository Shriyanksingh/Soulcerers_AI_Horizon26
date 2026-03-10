const BASE_URL_CANDIDATES = [
  "http://127.0.0.1:8010",
];

async function postToSingleBase(baseUrl, path, payload) {
  let response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    const networkError = new Error(
      `Cannot reach backend at ${baseUrl}. Start backend using run_latest_backend_8010.bat.`
    );
    networkError.code = "BACKEND_UNREACHABLE";
    throw networkError;
  }

  let data = {};
  try {
    data = await response.json();
  } catch (error) {
    // Keep default empty object if backend did not return JSON.
  }

  if (!response.ok) {
    const message =
      data?.detail || data?.message || `Request failed (${response.status})`;
    const error = new Error(message);
    error.httpStatus = response.status;
    throw error;
  }
  return data;
}

// Reusable helper for all POST APIs (single latest backend target).
async function postRequest(path, payload, options = {}) {
  const { validator, requireLatest = false } = options;
  let lastError = new Error("Request failed.");

  for (const baseUrl of BASE_URL_CANDIDATES) {
    try {
      const data = await postToSingleBase(baseUrl, path, payload);
      if (validator && !validator(data) && requireLatest) {
        const error = new Error(
          `Connected backend (${baseUrl}) is outdated. Start latest backend on 8010.`
        );
        error.code = "OUTDATED_BACKEND";
        throw error;
      }
      return data;
    } catch (error) {
      // Do not fail over for user/input errors from a reachable backend.
      if (error?.httpStatus && error.httpStatus < 500) {
        throw error;
      }
      // Explicit compatibility errors should be surfaced directly.
      if (error?.code === "OUTDATED_BACKEND") {
        throw error;
      }
      lastError = error;
    }
  }
  throw lastError;
}

function isSmartRouteResponseV4(data) {
  return (
    data &&
    typeof data === "object" &&
    typeof data.target_arrival_time === "string" &&
    Number.isFinite(Number(data.estimated_travel_minutes)) &&
    Number.isFinite(Number(data.departure_buffer_minutes)) &&
    typeof data.is_running_late === "boolean" &&
    Array.isArray(data.next_time_slot_recommendations) &&
    Number.isFinite(Number(data.arrival_probability)) &&
    typeof data.arrival_probability_label === "string" &&
    Number.isFinite(Number(data.traffic_confidence)) &&
    Number.isFinite(Number(data.parking_confidence)) &&
    data.explanation &&
    Array.isArray(data.explanation.why_this_route) &&
    typeof data.explanation.risk_warning === "string" &&
    Array.isArray(data.parking_options) &&
    data.best_parking_option &&
    typeof data.best_parking_option.name === "string" &&
    Number.isFinite(Number(data.best_parking_option.parking_score)) &&
    Array.isArray(data.traffic_timeline) &&
    typeof data.recommended_departure_marker === "string" &&
    typeof data.arrival_marker === "string"
  );
}

// Expose API methods on window for other script files.
window.ApiService = {
  predictTraffic: (payload) => postRequest("/predict", payload),
  bestTimeToLeave: (payload) => postRequest("/best-time-to-leave", payload),
  predictParking: (payload) => postRequest("/parking-predict", payload),
  getPersonalizedTip: (payload) => postRequest("/personalized-tip", payload),
  smartRouteAnalysis: (payload) =>
    postRequest("/smart-route-analysis", payload, {
      validator: isSmartRouteResponseV4,
      requireLatest: true,
    }),
  simulateEvent: (payload) => postRequest("/simulate-event", payload),
};
