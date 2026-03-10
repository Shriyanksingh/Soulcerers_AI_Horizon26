const dayOptions = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

const weatherOptions = ["Clear", "Clouds", "Rain", "Snow", "Mist", "Haze"];
const areaOptions = ["office", "mall", "residential", "market", "station"];
const trafficOptions = ["Low", "Medium", "High"];

function InputForm({
  formData,
  onChange,
  onPredictTraffic,
  onBestTime,
  onPredictParking,
  onPersonalizedTip,
  loading,
}) {
  const setField = (event) => {
    const { name, value } = event.target;
    onChange(name, value);
  };

  return (
    <section className="form-card">
      <h2>Input Form</h2>
      <p className="section-note">
        Use the defaults to test quickly, then change fields to try other scenarios.
      </p>

      <div className="form-grid">
        <label>
          User ID
          <input name="user_id" value={formData.user_id} onChange={setField} />
        </label>

        <label>
          Source
          <input name="source" value={formData.source} onChange={setField} />
        </label>

        <label>
          Destination
          <input name="destination" value={formData.destination} onChange={setField} />
        </label>

        <label>
          Hour
          <input
            name="hour"
            type="number"
            min="0"
            max="23"
            value={formData.hour}
            onChange={setField}
          />
        </label>

        <label>
          Day Of Week
          <select name="day_of_week" value={formData.day_of_week} onChange={setField}>
            {dayOptions.map((day) => (
              <option key={day} value={day}>
                {day}
              </option>
            ))}
          </select>
        </label>

        <label>
          Weather
          <select name="weather_main" value={formData.weather_main} onChange={setField}>
            {weatherOptions.map((weather) => (
              <option key={weather} value={weather}>
                {weather}
              </option>
            ))}
          </select>
        </label>

        <label>
          Temperature
          <input name="temp" type="number" step="0.1" value={formData.temp} onChange={setField} />
        </label>

        <label>
          Rain (1h)
          <input
            name="rain_1h"
            type="number"
            step="0.1"
            min="0"
            value={formData.rain_1h}
            onChange={setField}
          />
        </label>

        <label>
          Holiday
          <input name="holiday" value={formData.holiday} onChange={setField} />
        </label>

        <label>
          Area Type
          <select name="area_type" value={formData.area_type} onChange={setField}>
            {areaOptions.map((area) => (
              <option key={area} value={area}>
                {area}
              </option>
            ))}
          </select>
        </label>

        <label>
          Destination Type
          <select name="destination_type" value={formData.destination_type} onChange={setField}>
            {areaOptions.map((area) => (
              <option key={area} value={area}>
                {area}
              </option>
            ))}
          </select>
        </label>

        <label>
          Preferred Arrival Hour
          <input
            name="preferred_arrival_hour"
            type="number"
            min="0"
            max="23"
            value={formData.preferred_arrival_hour}
            onChange={setField}
          />
        </label>

        <label>
          Predicted Traffic Level
          <select
            name="predicted_traffic_level"
            value={formData.predicted_traffic_level}
            onChange={setField}
          >
            {trafficOptions.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </label>

        <label>
          Recommended Departure Time
          <input
            name="recommended_departure_time"
            value={formData.recommended_departure_time}
            onChange={setField}
          />
        </label>
      </div>

      <div className="button-row">
        <button type="button" onClick={onPredictTraffic} disabled={loading.traffic}>
          Predict Traffic
        </button>
        <button type="button" onClick={onBestTime} disabled={loading.departure}>
          Best Time To Leave
        </button>
        <button type="button" onClick={onPredictParking} disabled={loading.parking}>
          Predict Parking
        </button>
        <button type="button" onClick={onPersonalizedTip} disabled={loading.tip}>
          Get Personalized Tip
        </button>
      </div>
    </section>
  );
}

window.InputForm = InputForm;
