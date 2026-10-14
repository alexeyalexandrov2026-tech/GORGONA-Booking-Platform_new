"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { fetchWorkspace, type LocationItem } from "../lib/management-api";
import { fetchAccounts, fetchLedger } from "../lib/ledger-api";
import {
  fetchBalances,
  fetchCosts,
  fetchItems,
  fetchPlaces,
  fetchPostingRules,
} from "../lib/inventory-api";
import {
  RULE_ACCOUNTS,
  type Balance,
  type Cost,
  type Item,
  type Place,
  type PostingRules,
  type RuleAccount,
} from "../lib/inventory-contracts";
import {
  InventoryNotices,
  explain,
  useInventoryCommands,
  type CommandCenter,
} from "./inventory-commands";

const CODE = /^[A-Z0-9][A-Z0-9_-]{0,63}$/;
const TEXT = /^[^\u0000-\u001f\u007f-\u009f]+$/;
type Owner = { id: string; label: string; book: string | null };

export function Materials({
  actorId,
  businessId,
  companyWide,
  finance,
}: {
  actorId: string;
  businessId: string;
  /** A company-wide owner or manager: the list of materials is theirs to change. */
  companyWide: boolean;
  /** Reads cost and chooses the accounts of materials. */
  finance: boolean;
}) {
  const [items, setItems] = useState<Item[]>([]);
  const [places, setPlaces] = useState<Place[]>([]);
  const [balances, setBalances] = useState<Balance[]>([]);
  const [costs, setCosts] = useState<Cost[]>([]);
  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [owners, setOwners] = useState<Owner[]>([]);
  const [filter, setFilter] = useState("");
  const [failed, setFailed] = useState<string | null>(null);
  const read = useCallback(async () => {
    const [itemList, placeList, balanceList, workspace, costList, ledger] =
      await Promise.all([
        fetchItems(businessId),
        fetchPlaces(businessId),
        fetchBalances(businessId, filter || undefined),
        fetchWorkspace(businessId),
        finance ? fetchCosts(businessId) : null,
        finance ? fetchLedger(businessId) : null,
      ]);
    return { itemList, placeList, balanceList, workspace, costList, ledger };
  }, [businessId, filter, finance]);
  const show = useCallback((data: Awaited<ReturnType<typeof read>>) => {
    const { workspace } = data;
    setItems(data.itemList.items);
    setPlaces(data.placeList.items);
    setBalances(data.balanceList.items);
    // A branch manager places stock only in their own branch.
    setLocations(
      workspace.location_id
        ? workspace.locations.filter((l) => l.id === workspace.location_id)
        : workspace.locations,
    );
    setCosts(data.costList?.items ?? []);
    setOwners(
      (data.ledger?.items ?? []).map((x) => ({
        id: x.legal_entity_id,
        label: `${x.code} · ${x.legal_name}`,
        book: x.book?.book_id ?? null,
      })),
    );
  }, []);
  const load = useCallback(async () => show(await read()), [read, show]);
  useEffect(() => {
    let active = true;
    read().then(
      (data) => {
        if (!active) return;
        show(data);
        setFailed(null);
      },
      (error: unknown) => {
        if (active) setFailed(explain(error));
      },
    );
    return () => {
      active = false;
    };
  }, [read, show]);
  const center = useInventoryCommands(businessId, actorId, load);
  const itemName = (id: string) => {
    const item = items.find((x) => x.item_id === id);
    return item ? `${item.code} · ${item.name}` : id;
  };
  const placeName = (id: string) => {
    const place = places.find((x) => x.place_id === id);
    return place ? `${place.code} · ${place.name}` : id;
  };
  const ownerName = (id: string) =>
    owners.find((x) => x.id === id)?.label ?? id;

  return (
    <div className="inventory-screen materials">
      <h1>Materials</h1>
      {failed && (
        <p role="alert" className="error">
          {failed}
        </p>
      )}
      <InventoryNotices center={center} label="Materials change recovery" />
      <section aria-label="Material list">
        <h2>Materials</h2>
        {items.length === 0 ? (
          <p>No materials yet.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Code</th>
                  <th scope="col">Name</th>
                  <th scope="col">Unit</th>
                  <th scope="col">Decimals</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.item_id}>
                    <td>{item.code}</td>
                    <td>{item.name}</td>
                    <td>{item.unit}</td>
                    <td>{item.quantity_scale}</td>
                    <td>{item.archived ? "Archived" : "In use"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {companyWide && <ItemEditor items={items} center={center} />}
      <section aria-label="Storage places">
        <h2>Storage places</h2>
        {places.length === 0 ? (
          <p>No storage places yet.</p>
        ) : (
          <ul>
            {places.map((place) => (
              <li key={place.place_id}>
                {place.code} · {place.name} ·{" "}
                {locations.find((l) => l.id === place.location_id)?.name ??
                  "Branch"}
                {place.archived ? " · Archived" : ""}
              </li>
            ))}
          </ul>
        )}
      </section>
      <PlaceEditor places={places} locations={locations} center={center} />
      <section aria-label="Balances">
        <h2>Balances</h2>
        <label>
          Place
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All places</option>
            {places.map((place) => (
              <option key={place.place_id} value={place.place_id}>
                {place.code} · {place.name}
              </option>
            ))}
          </select>
        </label>
        {balances.length === 0 ? (
          <p>Nothing is held here.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Material</th>
                  <th scope="col">Place</th>
                  <th scope="col">Owner</th>
                  <th scope="col">Quantity</th>
                </tr>
              </thead>
              <tbody>
                {balances.map((row) => (
                  <tr
                    key={`${row.item_id}:${row.place_id}:${row.legal_entity_id}`}
                  >
                    <td>{itemName(row.item_id)}</td>
                    <td>{placeName(row.place_id)}</td>
                    <td>
                      {finance ? ownerName(row.legal_entity_id) : "Company"}
                    </td>
                    <td>{row.quantity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {finance && (
        <section aria-label="Cost of materials">
          <h2>Cost at the moving average</h2>
          {costs.length === 0 ? (
            <p>No cost recorded yet.</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Owner</th>
                    <th scope="col">Material</th>
                    <th scope="col">Quantity</th>
                    <th scope="col">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {costs.map((row) => (
                    <tr key={`${row.legal_entity_id}:${row.item_id}`}>
                      <td>{ownerName(row.legal_entity_id)}</td>
                      <td>{itemName(row.item_id)}</td>
                      <td>{row.quantity}</td>
                      <td>
                        {row.value} {row.currency}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
      {finance && companyWide && (
        <RulesEditor businessId={businessId} owners={owners} center={center} />
      )}
    </div>
  );
}

function ItemEditor({
  items,
  center,
}: {
  items: Item[];
  center: CommandCenter;
}) {
  const [editing, setEditing] = useState("");
  const current = items.find((x) => x.item_id === editing) ?? null;
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("");
  const [scale, setScale] = useState(0);
  const [archived, setArchived] = useState(false);
  function choose(id: string) {
    setEditing(id);
    const item = items.find((x) => x.item_id === id);
    setCode(item?.code ?? "");
    setName(item?.name ?? "");
    setUnit(item?.unit ?? "");
    setScale(item?.quantity_scale ?? 0);
    setArchived(item?.archived ?? false);
  }
  const valid =
    CODE.test(code) &&
    TEXT.test(name.trim()) &&
    name.trim().length <= 200 &&
    TEXT.test(unit.trim()) &&
    unit.trim().length <= 16;
  return (
    <form
      aria-label="Material editor"
      onSubmit={(event) => {
        event.preventDefault();
        if (!valid) return;
        void center
          .run(
            {
              type: "item",
              id: current?.item_id ?? crypto.randomUUID(),
              key: crypto.randomUUID(),
              body: {
                schema_version: 1,
                expected_revision: current?.revision ?? 0,
                code,
                name: name.trim(),
                unit: unit.trim(),
                quantity_scale: scale,
                archived,
              },
            },
            "Material saved.",
          )
          .then((saved) => saved && choose(""));
      }}
    >
      <h2>{current ? "Change material" : "New material"}</h2>
      <label>
        Material to change
        <select value={editing} onChange={(e) => choose(e.target.value)}>
          <option value="">A new material</option>
          {items.map((item) => (
            <option key={item.item_id} value={item.item_id}>
              {item.code} · {item.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Material code
        <input
          value={code}
          disabled={current !== null}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
        />
      </label>
      <label>
        Material name
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        Unit
        <input
          value={unit}
          disabled={current !== null}
          onChange={(e) => setUnit(e.target.value)}
        />
      </label>
      <label>
        Decimal places
        <select
          value={scale}
          disabled={current !== null}
          onChange={(e) => setScale(Number(e.target.value))}
        >
          {[0, 1, 2, 3].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
      <label>
        <input
          type="checkbox"
          checked={archived}
          onChange={(e) => setArchived(e.target.checked)}
        />
        Archived
      </label>
      <button type="submit" disabled={!valid || center.blocked}>
        Save material
      </button>
    </form>
  );
}

function PlaceEditor({
  places,
  locations,
  center,
}: {
  places: Place[];
  locations: LocationItem[];
  center: CommandCenter;
}) {
  const [editing, setEditing] = useState("");
  const current = places.find((x) => x.place_id === editing) ?? null;
  const [location, setLocation] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [archived, setArchived] = useState(false);
  const branch = location || locations[0]?.id || "";
  function choose(id: string) {
    setEditing(id);
    const place = places.find((x) => x.place_id === id);
    setLocation(place?.location_id ?? "");
    setCode(place?.code ?? "");
    setName(place?.name ?? "");
    setArchived(place?.archived ?? false);
  }
  const valid =
    branch !== "" &&
    CODE.test(code) &&
    TEXT.test(name.trim()) &&
    name.trim().length <= 200;
  return (
    <form
      aria-label="Storage place editor"
      onSubmit={(event) => {
        event.preventDefault();
        if (!valid) return;
        void center
          .run(
            {
              type: "place",
              id: current?.place_id ?? crypto.randomUUID(),
              key: crypto.randomUUID(),
              body: {
                schema_version: 1,
                expected_revision: current?.revision ?? 0,
                location_id: current?.location_id ?? branch,
                code,
                name: name.trim(),
                archived,
              },
            },
            "Storage place saved.",
          )
          .then((saved) => saved && choose(""));
      }}
    >
      <h2>{current ? "Change storage place" : "New storage place"}</h2>
      <label>
        Place to change
        <select value={editing} onChange={(e) => choose(e.target.value)}>
          <option value="">A new place</option>
          {places.map((place) => (
            <option key={place.place_id} value={place.place_id}>
              {place.code} · {place.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Branch
        <select
          value={current?.location_id ?? branch}
          disabled={current !== null}
          onChange={(e) => setLocation(e.target.value)}
        >
          {locations.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Place code
        <input
          value={code}
          disabled={current !== null}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
        />
      </label>
      <label>
        Place name
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        <input
          type="checkbox"
          checked={archived}
          onChange={(e) => setArchived(e.target.checked)}
        />
        Archived
      </label>
      <button type="submit" disabled={!valid || center.blocked}>
        Save storage place
      </button>
    </form>
  );
}

type Account = {
  account_id: string;
  code: string;
  name: string;
  archived: boolean;
};

function RulesEditor({
  businessId,
  owners,
  center,
}: {
  businessId: string;
  owners: Owner[];
  center: CommandCenter;
}) {
  const booked = owners.filter((x) => x.book !== null);
  const [owner, setOwner] = useState("");
  const chosenOwner = booked.find((x) => x.id === owner) ?? booked[0];
  const book = chosenOwner?.book ?? null;
  const [loaded, setLoaded] = useState<{
    book: string;
    accounts: Account[];
    rules: PostingRules | null;
  } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  // Read again after every saved or settled change; the form keeps what a person is
  // choosing until the book or its saved version changes.
  useEffect(() => {
    if (!book) return;
    let active = true;
    Promise.all([
      fetchAccounts(businessId, book),
      fetchPostingRules(businessId, book),
    ]).then(
      ([list, rules]) => {
        if (!active) return;
        setLoaded({
          book,
          accounts: list.items.filter((a) => !a.archived),
          rules,
        });
        setFailed(null);
      },
      (error: unknown) => {
        if (active) setFailed(explain(error));
      },
    );
    return () => {
      active = false;
    };
  }, [businessId, book, center.message]);
  if (!chosenOwner || !book)
    return (
      <section aria-label="Accounts of materials">
        <h2>Accounts of materials</h2>
        <p>
          Materials post to the ledger book of the company that owns them.
          Create a book first, then choose its accounts here.{" "}
          <Link href="/ledger/">Open the ledger</Link>
        </p>
      </section>
    );
  return (
    <section aria-label="Accounts of materials">
      <h2>Accounts of materials</h2>
      {failed && (
        <p role="alert" className="error">
          {failed}
        </p>
      )}
      <label>
        Owner
        <select
          value={chosenOwner.id}
          onChange={(e) => setOwner(e.target.value)}
        >
          {booked.map((x) => (
            <option key={x.id} value={x.id}>
              {x.label}
            </option>
          ))}
        </select>
      </label>
      {loaded?.book === book ? (
        <RulesForm
          key={`${book}:${loaded.rules?.revision ?? 0}`}
          book={book}
          accounts={loaded.accounts}
          rules={loaded.rules}
          center={center}
        />
      ) : (
        <p>Reading the accounts of this book.</p>
      )}
    </section>
  );
}

function RulesForm({
  book,
  accounts,
  rules,
  center,
}: {
  book: string;
  accounts: Account[];
  rules: PostingRules | null;
  center: CommandCenter;
}) {
  const [chosen, setChosen] = useState<Partial<Record<RuleAccount, string>>>(
    () =>
      rules
        ? Object.fromEntries(
            RULE_ACCOUNTS.map(([field]) => [field, rules[field]]),
          )
        : {},
  );
  const complete = RULE_ACCOUNTS.every(([field]) => chosen[field]);
  const apart = RULE_ACCOUNTS.slice(1).every(
    ([field]) => chosen[field] !== chosen.inventory_account_id,
  );
  return (
    <form
      aria-label="Accounts of this book"
      onSubmit={(event) => {
        event.preventDefault();
        if (!complete || !apart) return;
        void center.run(
          {
            type: "posting_rules",
            book,
            key: crypto.randomUUID(),
            body: {
              schema_version: 1,
              expected_revision: rules?.revision ?? 0,
              ...(Object.fromEntries(
                RULE_ACCOUNTS.map(([field]) => [field, chosen[field] ?? ""]),
              ) as Record<RuleAccount, string>),
            },
          },
          "Accounts of materials saved.",
        );
      }}
    >
      {!rules && (
        <p>
          No accounts are chosen for this book yet: documents with amounts
          cannot be posted until they are.
        </p>
      )}
      {RULE_ACCOUNTS.map(([field, label]) => (
        <label key={field}>
          {label}
          <select
            value={chosen[field] ?? ""}
            onChange={(e) => setChosen({ ...chosen, [field]: e.target.value })}
          >
            <option value="">Choose an account</option>
            {accounts.map((a) => (
              <option key={a.account_id} value={a.account_id}>
                {a.code} · {a.name}
              </option>
            ))}
          </select>
        </label>
      ))}
      {complete && !apart && (
        <p role="alert" className="error">
          The inventory account must differ from the other six accounts.
        </p>
      )}
      <button type="submit" disabled={!complete || !apart || center.blocked}>
        Save accounts
      </button>
    </form>
  );
}
