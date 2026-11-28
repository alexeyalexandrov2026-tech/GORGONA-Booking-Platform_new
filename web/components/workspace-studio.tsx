"use client";

import { useEffect, useId, useState } from "react";
import {
  createBoardCard,
  createCustomField,
  createWorkspaceBoard,
  deleteBoardCard,
  deleteCustomField,
  deleteWorkspaceBoard,
  fetchBoardCards,
  fetchBrandTheme,
  fetchCustomFields,
  fetchWorkspaceBoards,
  moveBoardCard,
  saveBrandTheme,
  type BoardEntityKind,
  type BrandTheme,
  type CardPriority,
  type CustomFieldDefinition,
  type CustomFieldType,
  type EntityKind,
  type SurfacePreset,
  type WorkspaceBoard,
  type WorkspaceBoardCard,
} from "../lib/workspace-studio-api";
import "../app/us-release-v2.css";

const ENTITY_LABELS: Record<EntityKind, string> = {
  counterparty: "Counterparties (CRM / Vendors)",
  commercial_quote: "Commercial Quotes (CPQ)",
  purchase_order: "Purchase Orders (PO)",
  booking: "Bookings / Dispatch Jobs",
  asset: "Managed Assets / Fleet",
  project_matter: "Projects & Legal Matters",
};

const FIELD_TYPE_LABELS: Record<CustomFieldType, string> = {
  text: "Text",
  number: "Number",
  currency_usd: "Currency (USD)",
  date: "Date (YYYY-MM-DD)",
  select: "Dropdown (Select)",
  boolean: "Checkbox (Yes/No)",
};

const WCAG_SAFE_ACCENTS = [
  { label: "MONOLITH Ink", hex: "#111111" },
  { label: "Enterprise Cobalt", hex: "#1D4ED8" },
  { label: "Forest Emerald", hex: "#15803D" },
  { label: "Deep Crimson", hex: "#B91C1C" },
  { label: "Royal Indigo", hex: "#4338CA" },
  { label: "Slate Graphite", hex: "#334155" },
];

const WIDGET_LABELS: Record<string, string> = {
  kpis: "Today's KPI Summary Cards",
  launchpad: "Go-Live Readiness Launchpad",
  unit_economics: "Live Unit Economics & 0% Savings",
  copilot: "AMARKAL AI Command Copilot",
  smart_autonomy: "AI Smart Autonomy & Predictive CFO Brief",
  schedule: "Today's Schedule & Audit Trail",
};

function errText(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

export function WorkspaceStudio({ businessId }: { businessId: string }) {
  const [activeTab, setActiveTab] = useState<"kanban" | "fields" | "theme">(
    "kanban",
  );
  const [boards, setBoards] = useState<WorkspaceBoard[]>([]);
  const [selectedBoardId, setSelectedBoardId] = useState<string | null>(null);
  const [cards, setCards] = useState<WorkspaceBoardCard[]>([]);
  const [fields, setFields] = useState<CustomFieldDefinition[]>([]);
  const [theme, setTheme] = useState<BrandTheme | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Drag state
  const [dragCardId, setDragCardId] = useState<string | null>(null);

  // New board form
  const [boardTitle, setBoardTitle] = useState("");
  const [boardSlug, setBoardSlug] = useState("");
  const [boardEntity, setBoardEntity] = useState<BoardEntityKind>("general");
  const [creatingBoard, setCreatingBoard] = useState(false);

  // New card form
  const [cardTitle, setCardTitle] = useState("");
  const [cardDesc, setCardDesc] = useState("");
  const [cardPriority, setCardPriority] = useState<CardPriority>("medium");
  const [cardAmountUsd, setCardAmountUsd] = useState("");
  const [cardLaneId, setCardLaneId] = useState("backlog");
  const [creatingCard, setCreatingCard] = useState(false);

  // New custom field form
  const [fieldEntity, setFieldEntity] = useState<EntityKind>("counterparty");
  const [fieldLabel, setFieldLabel] = useState("");
  const [fieldKey, setFieldKey] = useState("");
  const [fieldType, setFieldType] = useState<CustomFieldType>("text");
  const [fieldOptionsRaw, setFieldOptionsRaw] = useState("");
  const [fieldRequired, setFieldRequired] = useState(false);
  const [creatingField, setCreatingField] = useState(false);

  // Brand theme form
  const [brandName, setBrandName] = useState("");
  const [logoUrl, setLogoUrl] = useState("");
  const [accentHex, setAccentHex] = useState("#111111");
  const [surfacePreset, setSurfacePreset] =
    useState<SurfacePreset>("monolith_light");
  const [widgets, setWidgets] = useState<string[]>(Object.keys(WIDGET_LABELS));
  const [savingTheme, setSavingTheme] = useState(false);

  const bTitleId = useId();
  const bSlugId = useId();
  const bEntityId = useId();
  const cTitleId = useId();
  const cDescId = useId();
  const cPrioId = useId();
  const cAmtId = useId();
  const cLaneId = useId();
  const fEntityId = useId();
  const fLabelId = useId();
  const fKeyId = useId();
  const fTypeId = useId();
  const fOptsId = useId();
  const tNameId = useId();
  const tLogoId = useId();
  const tHexId = useId();
  const tSurfId = useId();

  useEffect(() => {
    let active = true;
    void Promise.all([
      fetchWorkspaceBoards(businessId),
      fetchCustomFields(businessId),
      fetchBrandTheme(businessId),
    ])
      .then(([bList, fList, th]) => {
        if (!active) return;
        setBoards(bList);
        const firstBoard = bList[0];
        if (firstBoard) {
          setSelectedBoardId(firstBoard.id);
          const firstLane = firstBoard.lanes[0];
          if (firstLane) setCardLaneId(firstLane.id);
        }
        setFields(fList);
        setTheme(th);
        setBrandName(th.brand_display_name ?? "");
        setLogoUrl(th.logo_url ?? "");
        setAccentHex(th.accent_hex);
        setSurfacePreset(th.surface_preset);
        setWidgets(th.dashboard_widgets);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active) setError(errText(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId]);

  useEffect(() => {
    if (!selectedBoardId) return;
    let active = true;
    fetchBoardCards(businessId, selectedBoardId)
      .then((list) => {
        if (active) setCards(list);
      })
      .catch((err: unknown) => {
        if (active) setError(errText(err));
      });
    return () => {
      active = false;
    };
  }, [businessId, selectedBoardId]);

  const activeBoard = boards.find((b) => b.id === selectedBoardId) ?? null;
  const boardCards = activeBoard
    ? cards.filter((c) => c.board_id === activeBoard.id)
    : [];

  async function onCreateBoard(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setCreatingBoard(true);
    try {
      const created = await createWorkspaceBoard(businessId, {
        title: boardTitle.trim(),
        slug:
          boardSlug.trim().toLowerCase() ||
          boardTitle
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "_")
            .slice(0, 48),
        entity_kind: boardEntity,
      });
      setBoards((prev) => [...prev, created]);
      setSelectedBoardId(created.id);
      const firstLane = created.lanes[0];
      if (firstLane) setCardLaneId(firstLane.id);
      setBoardTitle("");
      setBoardSlug("");
      setNotice(
        `Kanban board "${created.title}" created with 4 workflow lanes.`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setCreatingBoard(false);
    }
  }

  async function onDeleteBoard(boardId: string) {
    setError(null);
    setNotice(null);
    try {
      await deleteWorkspaceBoard(businessId, boardId);
      setBoards((prev) => {
        const next = prev.filter((b) => b.id !== boardId);
        setSelectedBoardId(next[0]?.id ?? null);
        return next;
      });
      setNotice("Kanban board removed.");
    } catch (err) {
      setError(errText(err));
    }
  }

  async function onCreateCard(e: React.FormEvent) {
    e.preventDefault();
    if (!activeBoard) return;
    setError(null);
    setNotice(null);
    setCreatingCard(true);
    try {
      const parsedUsd = cardAmountUsd.trim()
        ? Math.round(Number(cardAmountUsd) * 100)
        : null;
      const created = await createBoardCard(businessId, activeBoard.id, {
        lane_id: cardLaneId,
        title: cardTitle.trim(),
        description: cardDesc.trim(),
        priority: cardPriority,
        amount_cents:
          parsedUsd !== null && Number.isFinite(parsedUsd) && parsedUsd >= 0
            ? parsedUsd
            : null,
      });
      setCards((prev) => [...prev, created]);
      setCardTitle("");
      setCardDesc("");
      setCardAmountUsd("");
      setNotice(`Card "${created.title}" added.`);
    } catch (err) {
      setError(errText(err));
    } finally {
      setCreatingCard(false);
    }
  }

  async function onMoveCard(card: WorkspaceBoardCard, targetLaneId: string) {
    if (!activeBoard || card.lane_id === targetLaneId) return;
    setError(null);
    try {
      const moved = await moveBoardCard(
        businessId,
        activeBoard.id,
        card.id,
        targetLaneId,
        0,
      );
      setCards((prev) => prev.map((c) => (c.id === moved.id ? moved : c)));
      setNotice(
        `Moved "${moved.title}" to ${targetLaneId.replace(/_/g, " ")}.`,
      );
    } catch (err) {
      setError(errText(err));
    }
  }

  async function onDeleteCard(card: WorkspaceBoardCard) {
    if (!activeBoard) return;
    setError(null);
    try {
      await deleteBoardCard(businessId, activeBoard.id, card.id);
      setCards((prev) => prev.filter((c) => c.id !== card.id));
    } catch (err) {
      setError(errText(err));
    }
  }

  async function onCreateField(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setCreatingField(true);
    try {
      const opts = fieldOptionsRaw
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const created = await createCustomField(businessId, {
        entity_kind: fieldEntity,
        label: fieldLabel.trim(),
        field_key:
          fieldKey.trim().toLowerCase() ||
          fieldLabel
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "_")
            .replace(/^[^a-z]+/, "f_")
            .slice(0, 40),
        field_type: fieldType,
        options: opts,
        is_required: fieldRequired,
      });
      setFields((prev) => [...prev, created]);
      setFieldLabel("");
      setFieldKey("");
      setFieldOptionsRaw("");
      setFieldRequired(false);
      setNotice(
        `Custom field "${created.label}" (${created.field_key}) added to ${ENTITY_LABELS[created.entity_kind]}.`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setCreatingField(false);
    }
  }

  async function onDeleteField(defId: string) {
    setError(null);
    try {
      await deleteCustomField(businessId, defId);
      setFields((prev) => prev.filter((f) => f.id !== defId));
      setNotice("Custom field definition removed.");
    } catch (err) {
      setError(errText(err));
    }
  }

  async function onSaveTheme(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setSavingTheme(true);
    try {
      const saved = await saveBrandTheme(businessId, {
        brand_display_name: brandName.trim() || null,
        logo_url: logoUrl.trim() || null,
        accent_hex: accentHex.trim(),
        surface_preset: surfacePreset,
        dashboard_widgets: widgets,
      });
      setTheme(saved);
      setNotice(
        `Brand theme saved (${saved.accent_hex}, WCAG contrast ${saved.accent_contrast_on_white}:1 on white).`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setSavingTheme(false);
    }
  }

  return (
    <div className="usr-stack">
      <div className="mgmt-section-header">
        <div>
          <h2>No-Code Workspace Studio</h2>
          <p className="usr-muted" style={{ margin: "4px 0 0" }}>
            Customize AMARKAL for your industry without touching code:
            Drag-and-Drop Kanban workflows, typed Custom Fields across NAICS
            entities, and WCAG-verified Brand Themes.
          </p>
        </div>
      </div>

      <div
        role="tablist"
        aria-label="Workspace Studio sections"
        className="usr-inline"
      >
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "kanban"}
          className={
            activeTab === "kanban" ? "usr-small-btn" : "secondary usr-small-btn"
          }
          onClick={() => setActiveTab("kanban")}
        >
          Kanban Boards ({boards.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "fields"}
          className={
            activeTab === "fields" ? "usr-small-btn" : "secondary usr-small-btn"
          }
          onClick={() => setActiveTab("fields")}
        >
          Custom Fields ({fields.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "theme"}
          className={
            activeTab === "theme" ? "usr-small-btn" : "secondary usr-small-btn"
          }
          onClick={() => setActiveTab("theme")}
        >
          Brand Theme &amp; Dashboard
        </button>
      </div>

      {error && (
        <p className="usr-field-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="hold-note" style={{ margin: 0 }}>
          {notice}
        </p>
      )}
      {loading && (
        <p className="mgmt-loading" aria-live="polite">
          Loading Workspace Studio…
        </p>
      )}

      {!loading && activeTab === "kanban" && (
        <div className="usr-stack">
          <section className="usr-card" aria-labelledby="kanban-create-heading">
            <h3 id="kanban-create-heading" style={{ marginTop: 0 }}>
              Workflow Kanban Boards (Drag &amp; Drop)
            </h3>
            <form
              onSubmit={(e) => void onCreateBoard(e)}
              aria-label="Create Kanban board"
            >
              <div className="usr-grid">
                <label htmlFor={bTitleId}>
                  Board title
                  <input
                    id={bTitleId}
                    type="text"
                    required
                    minLength={2}
                    maxLength={120}
                    value={boardTitle}
                    placeholder="Example: Freight Dispatch Pipeline or Deal Flow"
                    onChange={(e) => setBoardTitle(e.target.value)}
                  />
                </label>
                <label htmlFor={bSlugId}>
                  Slug (optional)
                  <input
                    id={bSlugId}
                    type="text"
                    maxLength={63}
                    value={boardSlug}
                    placeholder="freight_dispatch"
                    onChange={(e) => setBoardSlug(e.target.value)}
                  />
                </label>
                <label htmlFor={bEntityId}>
                  Linked entity
                  <select
                    id={bEntityId}
                    value={boardEntity}
                    onChange={(e) =>
                      setBoardEntity(e.target.value as BoardEntityKind)
                    }
                  >
                    <option value="general">General Operations</option>
                    {Object.entries(ENTITY_LABELS).map(([k, lbl]) => (
                      <option key={k} value={k}>
                        {lbl}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <button
                type="submit"
                disabled={creatingBoard}
                style={{ marginTop: 12 }}
              >
                {creatingBoard ? "Creating board…" : "+ Create Kanban Board"}
              </button>
            </form>

            {boards.length > 0 && (
              <div className="usr-inline" style={{ marginTop: 16 }}>
                {boards.map((b) => (
                  <button
                    key={b.id}
                    type="button"
                    className={
                      b.id === selectedBoardId
                        ? "usr-small-btn"
                        : "secondary usr-small-btn"
                    }
                    onClick={() => {
                      setSelectedBoardId(b.id);
                      const first = b.lanes[0];
                      if (first) setCardLaneId(first.id);
                    }}
                  >
                    {b.title}
                  </button>
                ))}
                {activeBoard && (
                  <button
                    type="button"
                    className="usr-danger usr-small-btn"
                    onClick={() => void onDeleteBoard(activeBoard.id)}
                  >
                    Delete selected board
                  </button>
                )}
              </div>
            )}
          </section>

          {activeBoard && (
            <section
              className="usr-card"
              aria-labelledby="kanban-board-heading"
            >
              <h3 id="kanban-board-heading" style={{ marginTop: 0 }}>
                {activeBoard.title} — Drag cards across lanes or use Move
                buttons
              </h3>
              <form
                onSubmit={(e) => void onCreateCard(e)}
                aria-label="Add card to board"
                style={{ marginBottom: 16 }}
              >
                <div className="usr-grid">
                  <label htmlFor={cTitleId}>
                    Card title
                    <input
                      id={cTitleId}
                      type="text"
                      required
                      minLength={2}
                      maxLength={180}
                      value={cardTitle}
                      placeholder="Example: Load #408 Chicago -> Dallas"
                      onChange={(e) => setCardTitle(e.target.value)}
                    />
                  </label>
                  <label htmlFor={cLaneId}>
                    Lane
                    <select
                      id={cLaneId}
                      value={cardLaneId}
                      onChange={(e) => setCardLaneId(e.target.value)}
                    >
                      {activeBoard.lanes.map((l) => (
                        <option key={l.id} value={l.id}>
                          {l.title}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label htmlFor={cPrioId}>
                    Priority
                    <select
                      id={cPrioId}
                      value={cardPriority}
                      onChange={(e) =>
                        setCardPriority(e.target.value as CardPriority)
                      }
                    >
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">High</option>
                      <option value="urgent">Urgent</option>
                    </select>
                  </label>
                  <label htmlFor={cAmtId}>
                    USD Value (optional)
                    <input
                      id={cAmtId}
                      type="number"
                      min="0"
                      step="0.01"
                      value={cardAmountUsd}
                      placeholder="2500.00"
                      onChange={(e) => setCardAmountUsd(e.target.value)}
                    />
                  </label>
                </div>
                <label htmlFor={cDescId}>
                  Notes (optional)
                  <input
                    id={cDescId}
                    type="text"
                    maxLength={1000}
                    value={cardDesc}
                    placeholder="Key operational details or SLA"
                    onChange={(e) => setCardDesc(e.target.value)}
                  />
                </label>
                <button
                  type="submit"
                  disabled={creatingCard}
                  style={{ marginTop: 10 }}
                >
                  {creatingCard ? "Adding card…" : "+ Add Card"}
                </button>
              </form>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "repeat(auto-fit, minmax(min(100%, 240px), 1fr))",
                  gap: 12,
                }}
              >
                {activeBoard.lanes.map((lane, laneIdx) => {
                  const laneCards = boardCards.filter(
                    (c) => c.lane_id === lane.id,
                  );
                  const prevLane = activeBoard.lanes[laneIdx - 1];
                  const nextLane = activeBoard.lanes[laneIdx + 1];
                  return (
                    <div
                      key={lane.id}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => {
                        if (!dragCardId) return;
                        const found = cards.find((c) => c.id === dragCardId);
                        setDragCardId(null);
                        if (found) void onMoveCard(found, lane.id);
                      }}
                      style={{
                        border: "1px solid var(--line)",
                        borderRadius: 10,
                        padding: 12,
                        background: "#fafafa",
                        minHeight: 180,
                      }}
                    >
                      <div
                        className="usr-inline"
                        style={{
                          justifyContent: "space-between",
                          marginBottom: 10,
                          borderBottom: `3px solid ${lane.color_hex}`,
                          paddingBottom: 6,
                        }}
                      >
                        <strong>{lane.title}</strong>
                        <span className="usr-badge usr-badge-off">
                          {laneCards.length}
                        </span>
                      </div>
                      <div className="usr-stack" style={{ gap: 8 }}>
                        {laneCards.map((card) => (
                          <article
                            key={card.id}
                            draggable
                            onDragStart={() => setDragCardId(card.id)}
                            onDragEnd={() => setDragCardId(null)}
                            style={{
                              background: "#ffffff",
                              border: "1px solid var(--line)",
                              borderRadius: 8,
                              padding: 10,
                              cursor: "grab",
                            }}
                          >
                            <div
                              className="usr-inline"
                              style={{ justifyContent: "space-between" }}
                            >
                              <strong>{card.title}</strong>
                              <span
                                className={`usr-badge ${
                                  card.priority === "urgent" ||
                                  card.priority === "high"
                                    ? "usr-badge-fallback"
                                    : "usr-badge-off"
                                }`}
                              >
                                {card.priority}
                              </span>
                            </div>
                            {card.description && (
                              <p
                                className="usr-muted"
                                style={{ margin: "6px 0" }}
                              >
                                {card.description}
                              </p>
                            )}
                            {card.amount_cents != null && (
                              <p style={{ margin: "4px 0", fontWeight: 600 }}>
                                $
                                {(card.amount_cents / 100).toLocaleString(
                                  "en-US",
                                  { minimumFractionDigits: 2 },
                                )}{" "}
                                USD
                              </p>
                            )}
                            <div
                              className="usr-inline"
                              style={{ marginTop: 8 }}
                            >
                              {prevLane && (
                                <button
                                  type="button"
                                  className="secondary usr-small-btn"
                                  aria-label={`Move ${card.title} to ${prevLane.title}`}
                                  onClick={() =>
                                    void onMoveCard(card, prevLane.id)
                                  }
                                >
                                  ← {prevLane.title}
                                </button>
                              )}
                              {nextLane && (
                                <button
                                  type="button"
                                  className="secondary usr-small-btn"
                                  aria-label={`Move ${card.title} to ${nextLane.title}`}
                                  onClick={() =>
                                    void onMoveCard(card, nextLane.id)
                                  }
                                >
                                  {nextLane.title} →
                                </button>
                              )}
                              <button
                                type="button"
                                className="usr-danger usr-small-btn"
                                aria-label={`Delete card ${card.title}`}
                                onClick={() => void onDeleteCard(card)}
                              >
                                ×
                              </button>
                            </div>
                          </article>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
        </div>
      )}

      {!loading && activeTab === "fields" && (
        <section className="usr-card" aria-labelledby="custom-fields-heading">
          <h3 id="custom-fields-heading" style={{ marginTop: 0 }}>
            Typed Custom Fields Builder
          </h3>
          <p className="usr-muted">
            Extend any AMARKAL NAICS record with company-specific metadata
            (e.g., DOT Number, Lien Waiver Status, OSHA Permit Expiry, Contract
            Tier) while preserving strict PostgreSQL FORCE RLS isolation.
          </p>
          <form
            onSubmit={(e) => void onCreateField(e)}
            aria-label="Create custom field"
          >
            <div className="usr-grid">
              <label htmlFor={fEntityId}>
                Target entity
                <select
                  id={fEntityId}
                  value={fieldEntity}
                  onChange={(e) => setFieldEntity(e.target.value as EntityKind)}
                >
                  {Object.entries(ENTITY_LABELS).map(([k, lbl]) => (
                    <option key={k} value={k}>
                      {lbl}
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor={fLabelId}>
                Field label
                <input
                  id={fLabelId}
                  type="text"
                  required
                  minLength={2}
                  maxLength={80}
                  value={fieldLabel}
                  placeholder="Example: USDOT Carrier Number"
                  onChange={(e) => setFieldLabel(e.target.value)}
                />
              </label>
              <label htmlFor={fKeyId}>
                Machine key (optional)
                <input
                  id={fKeyId}
                  type="text"
                  maxLength={48}
                  value={fieldKey}
                  placeholder="usdot_number"
                  onChange={(e) => setFieldKey(e.target.value)}
                />
              </label>
              <label htmlFor={fTypeId}>
                Field type
                <select
                  id={fTypeId}
                  value={fieldType}
                  onChange={(e) =>
                    setFieldType(e.target.value as CustomFieldType)
                  }
                >
                  {Object.entries(FIELD_TYPE_LABELS).map(([k, lbl]) => (
                    <option key={k} value={k}>
                      {lbl}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {fieldType === "select" && (
              <label htmlFor={fOptsId}>
                Dropdown options (comma-separated)
                <input
                  id={fOptsId}
                  type="text"
                  required
                  value={fieldOptionsRaw}
                  placeholder="Tier 1 Preferred, Approved, On Hold"
                  onChange={(e) => setFieldOptionsRaw(e.target.value)}
                />
              </label>
            )}
            <label className="usr-check" style={{ margin: "10px 0" }}>
              <input
                type="checkbox"
                checked={fieldRequired}
                onChange={(e) => setFieldRequired(e.target.checked)}
              />
              <span>Mark field as required for staff forms</span>
            </label>
            <button type="submit" disabled={creatingField}>
              {creatingField ? "Adding field…" : "+ Add Custom Field"}
            </button>
          </form>

          {fields.length > 0 && (
            <div
              className="usr-table-wrap"
              tabIndex={0}
              aria-label="Defined custom fields"
              style={{ marginTop: 16 }}
            >
              <table className="usr-table">
                <thead>
                  <tr>
                    <th scope="col">Entity</th>
                    <th scope="col">Label</th>
                    <th scope="col">Key</th>
                    <th scope="col">Type</th>
                    <th scope="col">Required</th>
                    <th scope="col">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {fields.map((f) => (
                    <tr key={f.id}>
                      <td>{ENTITY_LABELS[f.entity_kind]}</td>
                      <td>
                        <strong>{f.label}</strong>
                      </td>
                      <td>
                        <code>{f.field_key}</code>
                      </td>
                      <td>
                        {FIELD_TYPE_LABELS[f.field_type]}
                        {f.options.length > 0
                          ? ` (${f.options.join(", ")})`
                          : ""}
                      </td>
                      <td>{f.is_required ? "Yes" : "Optional"}</td>
                      <td>
                        <button
                          type="button"
                          className="usr-danger usr-small-btn"
                          onClick={() => void onDeleteField(f.id)}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {!loading && activeTab === "theme" && (
        <section className="usr-card" aria-labelledby="brand-theme-heading">
          <div
            className="usr-inline"
            style={{ justifyContent: "space-between" }}
          >
            <h3 id="brand-theme-heading" style={{ margin: 0 }}>
              Brand Theme &amp; Dashboard Layout (WCAG 2.1 AA Guarded)
            </h3>
            {theme && (
              <span className="usr-badge usr-badge-ai">
                Contrast {theme.accent_contrast_on_white}:1 (WCAG AA Pass)
              </span>
            )}
          </div>
          <p className="usr-muted">
            Tailor your workspace header, brand accent color, and Overview
            dashboard widgets. AMARKAL automatically verifies at least 4.5:1
            contrast against white so custom branding never hurts readability.
          </p>
          <form
            onSubmit={(e) => void onSaveTheme(e)}
            aria-label="Configure tenant brand theme"
          >
            <div className="usr-grid">
              <label htmlFor={tNameId}>
                Brand display name override (optional)
                <input
                  id={tNameId}
                  type="text"
                  maxLength={120}
                  value={brandName}
                  placeholder="Acme US Logistics OS"
                  onChange={(e) => setBrandName(e.target.value)}
                />
              </label>
              <label htmlFor={tLogoId}>
                HTTPS Logo URL (optional — e.g. Cloudflare R2)
                <input
                  id={tLogoId}
                  type="url"
                  maxLength={500}
                  value={logoUrl}
                  placeholder="https://..."
                  onChange={(e) => setLogoUrl(e.target.value)}
                />
              </label>
            </div>

            <div className="usr-grid" style={{ marginTop: 12 }}>
              <label htmlFor={tHexId}>
                Primary Accent Hex (min 4.5:1 contrast on white)
                <input
                  id={tHexId}
                  type="text"
                  pattern="^#[0-9A-Fa-f]{6}$"
                  maxLength={7}
                  value={accentHex}
                  onChange={(e) => setAccentHex(e.target.value)}
                />
              </label>
              <label htmlFor={tSurfId}>
                Surface preset
                <select
                  id={tSurfId}
                  value={surfacePreset}
                  onChange={(e) =>
                    setSurfacePreset(e.target.value as SurfacePreset)
                  }
                >
                  <option value="monolith_light">MONOLITH Light</option>
                  <option value="warm_stone">Warm Stone</option>
                  <option value="slate_enterprise">Slate Enterprise</option>
                </select>
              </label>
            </div>

            <div className="usr-inline" style={{ margin: "10px 0 14px" }}>
              <span className="usr-muted">WCAG-verified presets:</span>
              {WCAG_SAFE_ACCENTS.map((sw) => (
                <button
                  key={sw.hex}
                  type="button"
                  className="secondary usr-small-btn"
                  onClick={() => setAccentHex(sw.hex)}
                >
                  <span
                    aria-hidden="true"
                    style={{
                      display: "inline-block",
                      width: 10,
                      height: 10,
                      borderRadius: "50%",
                      background: sw.hex,
                      marginRight: 6,
                    }}
                  />
                  {sw.label}
                </button>
              ))}
            </div>

            <fieldset className="usr-checks">
              <legend>Visible Overview Dashboard Widgets</legend>
              {Object.entries(WIDGET_LABELS).map(([key, label]) => (
                <label key={key} className="usr-check">
                  <input
                    type="checkbox"
                    checked={widgets.includes(key)}
                    onChange={() =>
                      setWidgets((prev) =>
                        prev.includes(key)
                          ? prev.filter((x) => x !== key)
                          : [...prev, key],
                      )
                    }
                  />
                  <span>{label}</span>
                </label>
              ))}
            </fieldset>

            <button
              type="submit"
              disabled={savingTheme}
              style={{ marginTop: 14 }}
            >
              {savingTheme ? "Validating & saving…" : "Save Brand Theme"}
            </button>
          </form>
        </section>
      )}
    </div>
  );
}
