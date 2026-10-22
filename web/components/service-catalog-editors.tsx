"use client";

// L7a (package L): the stages and the materials of one service, edited in one dialog.
// Words stay neutral (specialist, service, materials): every direction uses this screen.
import React, { useEffect, useId, useState } from "react";
import { fetchAllItems } from "../lib/inventory-api";
import type { Item } from "../lib/inventory-contracts";
import {
  fetchServiceMaterials,
  ManagementApiError,
  type RecipeLine,
  replaceServiceMaterials,
  replaceServiceStages,
  type ServiceView,
  type StageInput,
  type StageKind,
  type StageResource,
} from "../lib/management-api";

const KINDS: { value: StageKind; label: string }[] = [
  { value: "active", label: "Active work" },
  { value: "processing", label: "Processing (specialist free)" },
  { value: "finish", label: "Finish" },
];
const RESOURCES: { value: StageResource; label: string }[] = [
  { value: "specialist", label: "Specialist" },
  { value: "chair", label: "Chair" },
  { value: "room", label: "Room" },
  { value: "equipment", label: "Equipment" },
];

function refusal(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

export function ServiceCatalogDialog({
  salonId,
  service,
  onClose,
  onChanged,
}: {
  salonId: string;
  // Always the latest row of the catalog: saving moves its revision.
  service: ServiceView;
  onClose: () => void;
  onChanged: () => void;
}) {
  const titleId = useId();
  return (
    <div
      className="mgmt-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div className="mgmt-modal-card service-catalog-dialog">
        <h2 id={titleId}>Stages and materials: {service.name}</h2>
        <StagesEditor
          salonId={salonId}
          service={service}
          onChanged={onChanged}
        />
        <MaterialsEditor
          salonId={salonId}
          service={service}
          onChanged={onChanged}
        />
        <div className="mgmt-form-actions">
          <button type="button" className="secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function StagesEditor({
  salonId,
  service,
  onChanged,
}: {
  salonId: string;
  service: ServiceView;
  onChanged: () => void;
}) {
  const [rows, setRows] = useState<StageInput[]>(() =>
    service.stages.map(({ kind, minutes, resources }) => ({
      kind,
      minutes,
      resources: [...resources],
    })),
  );
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const total = rows.reduce((sum, row) => sum + (row.minutes || 0), 0);

  const change = (index: number, patch: Partial<StageInput>) =>
    setRows((current) =>
      current.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  const toggle = (index: number, resource: StageResource) =>
    setRows((current) =>
      current.map((row, i) =>
        i !== index
          ? row
          : {
              ...row,
              resources: row.resources.includes(resource)
                ? row.resources.filter((r) => r !== resource)
                : RESOURCES.map((r) => r.value).filter(
                    (r) => r === resource || row.resources.includes(r),
                  ),
            },
      ),
    );

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await replaceServiceStages(
        salonId,
        service.id,
        service.revision,
        rows,
      );
      setNotice(
        saved.stages.length
          ? `Stages saved. The service now takes ${saved.booking_duration_minutes} minutes.`
          : "Stages cleared. The service keeps one stage of its duration.",
      );
      onChanged();
    } catch (failure) {
      if (
        failure instanceof ManagementApiError &&
        failure.code === "SERVICE_REVISION_CONFLICT"
      ) {
        setNotice(
          "This service changed since it was opened. It was reloaded; check the stages and save again.",
        );
        onChanged();
      } else setError(`The stages were not saved: ${refusal(failure)}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      className="service-stages"
      onSubmit={save}
      aria-labelledby="stages-heading"
    >
      <h3 id="stages-heading">Stages</h3>
      <p className="muted">
        A specialist works in active and finish stages and is free while a stage
        is processing; the other resources stay held.
      </p>
      {rows.length === 0 && (
        <p className="muted">No stages: the service is one stage.</p>
      )}
      {rows.map((row, index) => (
        <fieldset key={index} className="service-stage-row">
          <legend>Stage {index + 1}</legend>
          <label>
            Kind
            <select
              value={row.kind}
              onChange={(e) =>
                change(index, { kind: e.target.value as StageKind })
              }
            >
              {KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Minutes
            <input
              type="number"
              min={1}
              max={720}
              inputMode="numeric"
              value={row.minutes || ""}
              onChange={(e) =>
                change(index, { minutes: Number(e.target.value) })
              }
              required
            />
          </label>
          <fieldset className="service-stage-resources">
            <legend>Uses</legend>
            {RESOURCES.map((r) => (
              <label key={r.value} className="inline">
                <input
                  type="checkbox"
                  checked={row.resources.includes(r.value)}
                  onChange={() => toggle(index, r.value)}
                />
                {r.label}
              </label>
            ))}
          </fieldset>
          <button
            type="button"
            className="secondary mgmt-btn-small"
            onClick={() =>
              setRows((current) => current.filter((_, i) => i !== index))
            }
          >
            Remove stage {index + 1}
          </button>
        </fieldset>
      ))}
      <p>
        <strong>Total:</strong> {total} min
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="hold-note" role="status">
          {notice}
        </p>
      )}
      <div className="mgmt-form-actions">
        <button
          type="button"
          className="secondary"
          onClick={() =>
            setRows((current) => [
              ...current,
              {
                kind: current.length ? "finish" : "active",
                minutes: 15,
                resources: ["specialist"],
              },
            ])
          }
          disabled={rows.length >= 10}
        >
          Add stage
        </button>
        <button type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save stages"}
        </button>
      </div>
    </form>
  );
}

function MaterialsEditor({
  salonId,
  service,
  onChanged,
}: {
  salonId: string;
  service: ServiceView;
  onChanged: () => void;
}) {
  const [items, setItems] = useState<Item[] | null>(null);
  const [rows, setRows] = useState<RecipeLine[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let live = true;
    Promise.all([
      fetchServiceMaterials(salonId, service.id),
      fetchAllItems(salonId),
    ])
      .then(([recipe, list]) => {
        if (!live) return;
        setRows(recipe.lines.map((line) => ({ ...line })));
        setLoaded(true);
        setItems(list.items.filter((item) => !item.archived));
        setUnavailable(null);
      })
      .catch((failure: unknown) => {
        if (live)
          setUnavailable(
            `Materials are not available here: ${refusal(failure)}`,
          );
      });
    return () => {
      live = false;
    };
  }, [salonId, service.id, reload]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!loaded) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      // The recipe's revision is the service's: saving the stages moves it too, so the
      // latest catalog row decides, never the revision seen when the dialog opened.
      const saved = await replaceServiceMaterials(
        salonId,
        service.id,
        service.revision,
        rows,
      );
      setRows(saved.lines.map((line) => ({ ...line })));
      setNotice("Materials saved.");
      onChanged();
    } catch (failure) {
      if (
        failure instanceof ManagementApiError &&
        failure.code === "SERVICE_REVISION_CONFLICT"
      ) {
        setNotice(
          "This service changed since it was opened. Its materials were reloaded.",
        );
        setReload((n) => n + 1);
        onChanged();
      } else setError(`The materials were not saved: ${refusal(failure)}`);
    } finally {
      setSaving(false);
    }
  }

  const unitOf = (id: string) => items?.find((i) => i.item_id === id)?.unit;

  return (
    <form
      className="service-materials"
      onSubmit={save}
      aria-labelledby="materials-heading"
    >
      <h3 id="materials-heading">Materials</h3>
      {unavailable ? (
        <p className="muted" role="status">
          {unavailable}
        </p>
      ) : items === null ? (
        <p className="muted" role="status">
          Loading materials…
        </p>
      ) : (
        <>
          {rows.length === 0 && (
            <p className="muted">No materials are used by this service.</p>
          )}
          {rows.map((row, index) => (
            <fieldset key={index} className="service-material-row">
              <legend>Material {index + 1}</legend>
              <label>
                Material
                <select
                  value={row.item_id}
                  onChange={(e) =>
                    setRows((current) =>
                      current.map((r, i) =>
                        i === index ? { ...r, item_id: e.target.value } : r,
                      ),
                    )
                  }
                >
                  {items.map((item) => (
                    <option key={item.item_id} value={item.item_id}>
                      {item.name} ({item.unit})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Quantity{unitOf(row.item_id) ? ` (${unitOf(row.item_id)})` : ""}
                <input
                  type="text"
                  inputMode="decimal"
                  value={row.quantity}
                  onChange={(e) =>
                    setRows((current) =>
                      current.map((r, i) =>
                        i === index ? { ...r, quantity: e.target.value } : r,
                      ),
                    )
                  }
                  required
                />
              </label>
              <button
                type="button"
                className="secondary mgmt-btn-small"
                onClick={() =>
                  setRows((current) => current.filter((_, i) => i !== index))
                }
              >
                Remove material {index + 1}
              </button>
            </fieldset>
          ))}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="hold-note" role="status">
              {notice}
            </p>
          )}
          <div className="mgmt-form-actions">
            <button
              type="button"
              className="secondary"
              disabled={items.length === 0 || rows.length >= 20}
              onClick={() => {
                const first = items[0];
                if (first)
                  setRows((current) => [
                    ...current,
                    { item_id: first.item_id, quantity: "1" },
                  ]);
              }}
            >
              Add material
            </button>
            <button type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save materials"}
            </button>
          </div>
        </>
      )}
    </form>
  );
}
