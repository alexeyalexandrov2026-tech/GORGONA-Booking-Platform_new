import { WEEKDAYS } from "../lib/business-time";
import type { WorkingHourDraft } from "../lib/working-hours";

export function WorkingHoursEditor({
  value,
  onChange,
  disabled,
}: {
  value: WorkingHourDraft[];
  onChange: (value: WorkingHourDraft[]) => void;
  disabled: boolean;
}) {
  function edit(index: number, change: Partial<WorkingHourDraft>) {
    onChange(
      value.map((item, position) =>
        position === index ? { ...item, ...change } : item,
      ),
    );
  }
  return (
    <fieldset disabled={disabled}>
      <legend>Weekly working hours</legend>
      <p className="muted">
        Add each working interval. Days without intervals are unavailable.
      </p>
      {WEEKDAYS.map((day) => (
        <div key={day.index} className="working-hours-day">
          <strong>{day.label}</strong>
          {value.map(
            (item, index) =>
              item.weekday === day.index && (
                <div key={index} className="working-hours-interval">
                  <label>
                    From
                    <input
                      type="time"
                      required
                      value={item.open}
                      aria-label={`${day.label} interval ${index + 1} opens`}
                      onChange={(event) =>
                        edit(index, { open: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    To
                    <input
                      type="time"
                      required={item.close !== "24:00"}
                      disabled={item.close === "24:00" || disabled}
                      value={item.close === "24:00" ? "00:00" : item.close}
                      aria-label={`${day.label} interval ${index + 1} closes`}
                      onChange={(event) =>
                        edit(index, { close: event.target.value })
                      }
                    />
                  </label>
                  <label className="working-hours-midnight">
                    <input
                      type="checkbox"
                      checked={item.close === "24:00"}
                      onChange={(event) =>
                        edit(index, {
                          close: event.target.checked ? "24:00" : "",
                        })
                      }
                    />
                    End at midnight
                  </label>
                  <button
                    type="button"
                    className="secondary"
                    aria-label={`Remove ${day.label} interval ${index + 1}`}
                    onClick={() =>
                      onChange(
                        value.filter((_, position) => position !== index),
                      )
                    }
                  >
                    Remove
                  </button>
                </div>
              ),
          )}
          <button
            type="button"
            className="secondary mgmt-btn-small"
            disabled={value.length >= 50}
            onClick={() =>
              onChange([...value, { weekday: day.index, open: "", close: "" }])
            }
          >
            Add {day.label} hours
          </button>
        </div>
      ))}
    </fieldset>
  );
}
