"use client";
import type {
  Counterparty,
  CounterpartyInput,
  ContactInput,
} from "../lib/counterparty-contracts";
const newContact = (): ContactInput => ({
  name: "",
  job_title: null,
  email: null,
  phone: null,
});
export function CounterpartyEditor({
  selected,
  form,
  setForm,
  locked,
  reloadDisabled,
  onReload,
  onSubmit,
}: {
  selected: Counterparty | null;
  form: CounterpartyInput;
  setForm: (form: CounterpartyInput) => void;
  locked: boolean;
  reloadDisabled: boolean;
  onReload: () => void;
  onSubmit: (event: React.FormEvent) => void;
}) {
  const fields = [
    ["display_name", "Display name", 200],
    ["legal_name", "Legal name", 300],
    ["tax_id", "Tax identifier", 64],
    ["registration_number", "Registration number", 64],
    ["email", "Email", 254],
    ["phone", "Phone", 32],
  ] as const;
  return (
    <section aria-label="Counterparty card" className="mgmt-card">
      <h2>{selected ? selected.display_name : "New counterparty"}</h2>
      {selected && (
        <>
          <p>
            Version {selected.revision} · {selected.state}
          </p>
          <button
            disabled={reloadDisabled}
            className="secondary"
            onClick={onReload}
          >
            Reload card
          </button>
        </>
      )}
      {selected?.state === "merged" && (
        <p>
          This card is merged. Its saved details remain readable. Record a
          separation before editing it.
        </p>
      )}
      <form onSubmit={(e) => void onSubmit(e)}>
        <fieldset disabled={locked}>
          <legend>Card details</legend>
          <label>
            Record type
            <select
              value={form.kind}
              disabled={selected !== null}
              onChange={(e) =>
                setForm({
                  ...form,
                  kind: e.target.value as CounterpartyInput["kind"],
                })
              }
            >
              <option value="person">Person</option>
              <option value="organization">Organization</option>
            </select>
          </label>
          <div className="cp-fields">
            {fields.map(([key, label, max]) => (
              <label key={key}>
                {label}
                <input
                  type={
                    key === "email" ? "email" : key === "phone" ? "tel" : "text"
                  }
                  value={form[key] ?? ""}
                  required={key === "display_name"}
                  maxLength={max}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      [key]:
                        e.target.value || (key === "display_name" ? "" : null),
                    })
                  }
                />
              </label>
            ))}
          </div>
          <fieldset>
            <legend>Roles</legend>
            {(["customer", "supplier", "contractor", "partner"] as const).map(
              (r) => (
                <label key={r}>
                  <input
                    type="checkbox"
                    checked={form.roles.includes(r)}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        roles: e.target.checked
                          ? [...form.roles, r]
                          : form.roles.filter((v) => v !== r),
                      })
                    }
                  />{" "}
                  {r}
                </label>
              ),
            )}
          </fieldset>
          <label>
            <input
              type="checkbox"
              checked={form.archived}
              onChange={(e) => setForm({ ...form, archived: e.target.checked })}
            />{" "}
            Archived
          </label>
          <h3>Contact people</h3>
          {form.contacts.map((contact, i) => (
            <fieldset key={i}>
              <legend>Contact {i + 1}</legend>
              <div className="cp-fields">
                {(["name", "job_title", "email", "phone"] as const).map(
                  (key) => (
                    <label key={key}>
                      {
                        {
                          name: "Contact name",
                          job_title: "Job title",
                          email: "Contact email",
                          phone: "Contact phone",
                        }[key]
                      }
                      <input
                        required={key === "name"}
                        type={
                          key === "email"
                            ? "email"
                            : key === "phone"
                              ? "tel"
                              : "text"
                        }
                        maxLength={
                          key === "email" ? 254 : key === "phone" ? 32 : 200
                        }
                        value={contact[key] ?? ""}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            contacts: form.contacts.map((c, n) =>
                              n === i
                                ? {
                                    ...c,
                                    [key]:
                                      e.target.value ||
                                      (key === "name" ? "" : null),
                                  }
                                : c,
                            ),
                          })
                        }
                      />
                    </label>
                  ),
                )}
              </div>
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  setForm({
                    ...form,
                    contacts: form.contacts.filter((_, n) => n !== i),
                  })
                }
              >
                Remove contact {i + 1}
              </button>
            </fieldset>
          ))}
          <button
            type="button"
            className="secondary"
            disabled={form.contacts.length >= 20}
            onClick={() =>
              setForm({ ...form, contacts: [...form.contacts, newContact()] })
            }
          >
            Add contact
          </button>
          <button type="submit">Review and save card</button>
        </fieldset>
      </form>
    </section>
  );
}
