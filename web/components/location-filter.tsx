import type { LocationItem } from "../lib/management-api";

export function LocationFilter({
  locations,
  value,
  onChange,
}: {
  locations: LocationItem[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="mgmt-filter-group">
      <label htmlFor="location-filter">Location:</label>
      <select
        id="location-filter"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={!locations.length}
      >
        {!locations.length && <option value="">Loading locations…</option>}
        {locations.map((location) => (
          <option key={location.id} value={location.id}>
            {location.name} · {location.timezone}
          </option>
        ))}
      </select>
    </div>
  );
}
