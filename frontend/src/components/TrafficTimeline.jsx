function TrafficTimeline({
  timeline = [],
  recommendedDeparture = "",
  arrivalMarker = "",
}) {
  if (!Array.isArray(timeline) || timeline.length === 0) {
    return <p className="muted-text">Timeline data not available for this run.</p>;
  }

  return (
    <div className="traffic-timeline-wrap">
      {timeline.map((slot, idx) => {
        const level = String(slot?.traffic_level || "moderate").toLowerCase();
        const levelClass =
          level === "high" ? "is-high" : level === "low" ? "is-low" : "is-moderate";
        const isDeparture = slot?.time === recommendedDeparture;
        const isArrival = slot?.time === arrivalMarker;

        return (
          <div
            key={`${slot?.time}-${idx}`}
            className={`traffic-timeline-slot ${levelClass} ${
              isDeparture || isArrival ? "is-marker" : ""
            }`}
          >
            <div className="timeline-slot-time">{slot?.time}</div>
            <div className="timeline-slot-level">{level}</div>
            <div className="timeline-slot-badge">
              {isDeparture ? "Departure" : isArrival ? "Arrival" : slot?.color_hint || ""}
            </div>
          </div>
        );
      })}
    </div>
  );
}

window.TrafficTimeline = TrafficTimeline;

