import { expect, test } from "@playwright/test";
import {
  changeSchema,
  commandReference,
  commandStatusSchema,
  deskSchema,
  directoryListSchema,
  locationSettingSchema,
  shiftListSchema,
  shiftSchema,
  timeHistorySchema,
  timeSchema,
  workforceCommandSchema,
  workforceResponseSchema,
  type WorkforceCommand,
} from "../lib/workforce-contracts";
import { managementResponseSchema } from "../lib/management-contracts";
import {
  clearWorkforceRecovery,
  preserveWorkforceRecovery,
  readWorkforceRecovery,
  workforceRecoverySchema,
} from "../lib/workforce-recovery";

const uuid = (n: number) =>
  `00000000-0000-4000-8000-${n.toString().padStart(12, "0")}`;
const business = uuid(1);
const location = uuid(2);
const profile = uuid(3);
const other = uuid(4);
const user = uuid(5);
const subject = uuid(6);
const skill = uuid(7);
const shift = {
  schema_version: 1,
  business_id: business,
  shift_id: subject,
  location_id: location,
  revision: 2,
  position: "FAKE host",
  starts_at: "2031-06-02T10:00:00Z",
  ends_at: "2031-06-02T18:00:00Z",
  required_skill_ids: [skill],
  status: "published",
  staff_profile_id: profile,
  assignment_id: uuid(8),
};
const change = {
  schema_version: 1,
  business_id: business,
  request_id: uuid(9),
  kind: "handover",
  location_id: location,
  other_location_id: null,
  shift_id: subject,
  expected_shift_revision: 2,
  other_shift_id: null,
  expected_other_shift_revision: null,
  from_profile_id: profile,
  target_profile_id: other,
  proposed_by: user,
  recipient_user_id: uuid(10),
  revision: 1,
  status: "proposed",
  event_created_by: user,
  event_created_at: "2031-06-01T09:00:00.123456Z",
  applied_shifts: [],
};
const approved = {
  schema_version: 1,
  revision: 3,
  starts_at: "2031-06-02T10:00:00Z",
  ends_at: "2031-06-02T18:00:00Z",
  breaks: [
    {
      schema_version: 1,
      starts_at: "2031-06-02T13:00:00Z",
      ends_at: "2031-06-02T13:30:00Z",
    },
  ],
  worked_microseconds: 27_000_000_000,
  approved_by: uuid(11),
  approved_at: "2031-06-02T19:00:00Z",
  self_approved: false,
};
const entry = {
  schema_version: 1,
  business_id: business,
  entry_id: uuid(12),
  staff_profile_id: profile,
  user_id: user,
  location_id: location,
  shift_id: subject,
  expected_shift_revision: 2,
  revision: 4,
  action: "correct",
  status: "proposed",
  starts_at: "2031-06-02T09:45:00Z",
  ends_at: "2031-06-02T18:00:00Z",
  breaks: [],
  break_started_at: null,
  reason: "FAKE forgot the early start",
  created_by: user,
  created_at: "2031-06-03T08:00:00Z",
  self_approved: false,
  out_of_schedule: true,
  worked_microseconds: 29_700_000_000,
  effective: approved,
};
const rejects = (schema: { safeParse(v: unknown): { success: boolean } }) => {
  return (base: object, changes: object[]) => {
    for (const changed of changes)
      expect(
        schema.safeParse({ ...base, ...changed }).success,
        JSON.stringify(changed),
      ).toBe(false);
  };
};

test("a shift is one seat with a positive interval and unique skills", () => {
  expect(shiftSchema.safeParse(shift).success).toBe(true);
  expect(
    shiftSchema.safeParse({
      ...shift,
      status: "draft",
      staff_profile_id: null,
      assignment_id: null,
    }).success,
  ).toBe(true);
  rejects(shiftSchema)(shift, [
    { ends_at: shift.starts_at },
    { status: "draft" },
    { status: "open" },
    { required_skill_ids: [skill, skill] },
    { position: "" },
    { position: "FAKE\nline" },
    { revision: 0 },
    { pay_rate: "10.00" },
  ]);
  const list = { schema_version: 1, items: [shift], next_cursor: null };
  expect(shiftListSchema.safeParse(list).success).toBe(true);
  expect(
    shiftListSchema.safeParse({ ...list, items: [shift, shift] }).success,
  ).toBe(false);
});

test("a change keeps its kind, both shift versions and the applied result", () => {
  expect(changeSchema.safeParse(change).success).toBe(true);
  const swap = {
    ...change,
    kind: "swap",
    other_shift_id: uuid(13),
    expected_other_shift_revision: 1,
    other_location_id: location,
  };
  expect(changeSchema.safeParse(swap).success).toBe(true);
  expect(
    changeSchema.safeParse({
      ...swap,
      status: "approved",
      revision: 3,
      applied_shifts: [
        { schema_version: 1, shift_id: subject, revision: 3 },
        { schema_version: 1, shift_id: uuid(13), revision: 2 },
      ],
    }).success,
  ).toBe(true);
  expect(
    changeSchema.safeParse({ ...change, kind: "pickup", from_profile_id: null })
      .success,
  ).toBe(true);
  rejects(changeSchema)(change, [
    { kind: "swap" },
    { other_shift_id: uuid(13) },
    { kind: "pickup" },
    { status: "approved" },
    { status: "applied" },
    {
      applied_shifts: [{ schema_version: 1, shift_id: subject, revision: 3 }],
    },
    { note: "FAKE" },
  ]);
});

test("a time entry separates the pending version from the one in effect", () => {
  const parsed = timeSchema.parse(entry);
  expect(parsed.status).toBe("proposed");
  expect(parsed.effective?.revision).toBe(3);
  expect(parsed.effective?.starts_at).not.toBe(parsed.starts_at);
  const open = {
    ...entry,
    revision: 2,
    action: "break_start",
    status: "open",
    ends_at: null,
    worked_microseconds: null,
    break_started_at: "2031-06-02T13:00:00Z",
    reason: "",
    effective: null,
  };
  expect(timeSchema.safeParse(open).success).toBe(true);
  expect(
    timeSchema.safeParse({
      ...entry,
      action: "approve",
      status: "approved",
      self_approved: true,
      effective: { ...approved, revision: 4, self_approved: true },
    }).success,
  ).toBe(true);
  rejects(timeSchema)(entry, [
    { status: "open" },
    { ends_at: null },
    { worked_microseconds: null },
    { ends_at: entry.starts_at },
    { break_started_at: "2031-06-02T13:00:00Z" },
    { shift_id: null },
    { status: "paid" },
    { effective: { ...approved, ends_at: approved.starts_at } },
    { wage: 100 },
  ]);
  const history = {
    schema_version: 1,
    items: [
      { ...open, revision: 1, action: "clock_in", break_started_at: null },
      open,
    ],
    next_revision: null,
  };
  expect(timeHistorySchema.safeParse(history).success).toBe(true);
  expect(
    timeHistorySchema.safeParse({
      ...history,
      items: [...history.items].reverse(),
    }).success,
  ).toBe(false);
});

test("desk, directory and command status are closed and scoped", () => {
  const desk = {
    schema_version: 1,
    business_id: business,
    writes: "module_disabled",
    profile: {
      schema_version: 1,
      business_id: business,
      profile_id: profile,
      membership_id: uuid(14),
      resource_id: uuid(15),
      location_id: location,
      user_id: user,
    },
    colleague_shifts: "hidden",
  };
  expect(deskSchema.safeParse(desk).success).toBe(true);
  expect(deskSchema.safeParse({ ...desk, profile: null }).success).toBe(true);
  rejects(deskSchema)(desk, [
    { writes: "closed" },
    { colleague_shifts: "private" },
    { colleague_shifts: undefined },
    { profile: { ...desk.profile, business_id: uuid(16) } },
    { payroll: true },
  ]);
  const person = {
    schema_version: 1,
    membership_id: uuid(14),
    user_id: user,
    display_name: "FAKE Person",
    role: "artist",
    location_id: location,
    profile_id: profile,
    home_location_id: location,
  };
  const directory = { schema_version: 1, items: [person], next_cursor: null };
  expect(directoryListSchema.safeParse(directory).success).toBe(true);
  for (const changed of [
    { home_location_id: null },
    { role: "support" },
    { email: "fake@example.test" },
  ])
    expect(
      directoryListSchema.safeParse({
        ...directory,
        items: [{ ...person, ...changed }],
      }).success,
    ).toBe(false);
  const status = {
    schema_version: 1,
    business_id: business,
    key: "FAKE-command-1",
    operation: "time.event",
    state: "committed",
  };
  expect(commandStatusSchema.safeParse(status).success).toBe(true);
  rejects(commandStatusSchema)(status, [
    { state: "pending" },
    { operation: "payroll" },
    { key: "short" },
    { reason: "FAKE" },
  ]);
});

test("a location setting is versioned and its default is nobody's change", () => {
  const untouched = {
    schema_version: 1,
    business_id: business,
    location_id: location,
    revision: 0,
    colleague_shifts_visible: true,
    changed_by: null,
    changed_at: null,
  };
  const hidden = {
    ...untouched,
    revision: 2,
    colleague_shifts_visible: false,
    changed_by: user,
    changed_at: "2031-06-02T10:00:00.123456Z",
  };
  expect(locationSettingSchema.safeParse(untouched).success).toBe(true);
  expect(locationSettingSchema.safeParse(hidden).success).toBe(true);
  rejects(locationSettingSchema)(hidden, [
    { revision: 0 },
    { revision: -1 },
    { changed_by: null },
    { changed_at: null },
    { colleague_shifts_visible: "no" },
    { reason: "FAKE" },
  ]);
  // The default is visible; a hidden default would be a change nobody made.
  rejects(locationSettingSchema)(untouched, [
    { colleague_shifts_visible: false },
  ]);
  const command = {
    operation: "location_setting",
    key: "FAKE-command-7",
    subject: location,
    body: {
      schema_version: 1,
      expected_revision: 2,
      colleague_shifts_visible: true,
    },
  };
  expect(commandReference(workforceCommandSchema.parse(command))).toEqual({
    schema_version: 1,
    operation: "location_setting",
    subject_id: location,
    revision: 3,
    skill_id: null,
  });
  for (const body of [
    { ...command.body, colleague_shifts_visible: "yes" },
    { ...command.body, expected_revision: -1 },
    { ...command.body, reason: "FAKE private" },
    { schema_version: 1, expected_revision: 2 },
  ])
    expect(workforceCommandSchema.safeParse({ ...command, body }).success).toBe(
      false,
    );
});

test("every workforce route has exactly one response contract", () => {
  const root = `/v1/businesses/${business}/workforce`;
  const known: [string, string][] = [
    ["GET", "/desk"],
    ["GET", "/directory"],
    ["GET", "/staff"],
    ["PUT", `/staff/${profile}`],
    ["GET", "/skills"],
    ["PUT", `/skills/${skill}`],
    ["PUT", `/staff/${profile}/skills/${skill}`],
    ["GET", `/staff/${profile}/skills/${skill}/history`],
    ["GET", "/shifts"],
    ["GET", "/my-shifts"],
    ["GET", "/open-shifts"],
    ["GET", `/colleagues/${profile}/shifts`],
    ["GET", `/shifts/${subject}`],
    ["PUT", `/shifts/${subject}`],
    ["GET", "/colleagues"],
    ["GET", "/changes"],
    ["GET", "/my-changes"],
    ["PUT", `/changes/${subject}`],
    ["POST", `/changes/${subject}/events`],
    ["GET", `/my-changes/${subject}/history`],
    ["GET", `/my-changes/${subject}/shifts`],
    ["GET", `/locations/${location}/settings`],
    ["PUT", `/locations/${location}/settings`],
    ["GET", "/time-entries"],
    ["GET", "/my-time-entries"],
    ["PUT", `/time-entries/${subject}`],
    ["POST", `/time-entries/${subject}/events`],
    ["GET", `/time-entries/${subject}/history`],
    ["POST", "/commands/FAKE-command-1/resolve"],
    ["POST", "/commands/FAKE-command-1/cancel"],
  ];
  for (const [method, path] of known)
    expect(
      workforceResponseSchema(`/workforce${path}`, method),
      `${method} ${path}`,
    ).not.toBeNull();
  for (const [method, path] of [
    ["DELETE", `/shifts/${subject}`],
    ["PUT", `/my-changes/${subject}`],
    ["PUT", `/my-time-entries/${subject}`],
    ["POST", "/desk"],
    ["POST", `/locations/${location}/settings`],
    ["GET", "/locations"],
    ["PUT", `/my-changes/${subject}/shifts`],
    ["GET", "/payroll"],
    ["POST", "/commands/short/resolve"],
    ["POST", "/commands/FAKE-command-1/replay"],
  ] as const)
    expect(
      workforceResponseSchema(`/workforce${path}`, method),
      `${method} ${path}`,
    ).toBeNull();
  expect(workforceResponseSchema("/ledger/books", "GET")).toBeNull();
  expect(
    managementResponseSchema(
      `${root}/shifts/${subject}?revision=1`,
      "GET",
    ).safeParse(shift).success,
  ).toBe(true);
  expect(
    managementResponseSchema(`${root}/shifts/${subject}`, "GET").safeParse(
      entry,
    ).success,
  ).toBe(false);
  // An unknown workforce route has no contract and is never read.
  expect(() => managementResponseSchema(`${root}/payroll`, "GET")).toThrow(
    /Unrecognized/,
  );
});

const correction: WorkforceCommand = {
  operation: "time.event",
  key: "FAKE-command-1",
  subject: entry.entry_id,
  body: {
    schema_version: 1,
    expected_revision: 3,
    action: "correct",
    starts_at: "2031-06-02T09:45:00Z",
    ends_at: "2031-06-02T18:00:00Z",
    breaks: [],
    reason: "FAKE private reason",
  },
};

test("commands are strict and name the version they produce", () => {
  expect(commandReference(workforceCommandSchema.parse(correction))).toEqual({
    schema_version: 1,
    operation: "time.event",
    subject_id: entry.entry_id,
    revision: 4,
    skill_id: null,
  });
  const samples: [WorkforceCommand, number, string | null][] = [
    [
      {
        operation: "profile",
        key: "FAKE-command-2",
        subject: profile,
        body: {
          schema_version: 1,
          membership_id: uuid(14),
          location_id: location,
        },
      },
      0,
      null,
    ],
    [
      {
        operation: "staff_skill",
        key: "FAKE-command-3",
        subject: profile,
        skill,
        body: {
          schema_version: 1,
          expected_revision: 0,
          effective_at: "2031-06-01T00:00:00Z",
          granted: true,
        },
      },
      1,
      skill,
    ],
    [
      {
        operation: "change.propose",
        key: "FAKE-command-4",
        subject: uuid(9),
        body: {
          schema_version: 1,
          kind: "pickup",
          shift_id: subject,
          expected_shift_revision: 2,
          target_profile_id: profile,
          other_shift_id: null,
          expected_other_shift_revision: null,
        },
      },
      1,
      null,
    ],
    [
      {
        operation: "time.clock_in",
        key: "FAKE-command-5",
        subject: uuid(12),
        body: {
          schema_version: 1,
          expected_revision: 0,
          staff_profile_id: profile,
          starts_at: "2031-06-02T10:00:00Z",
          shift_id: null,
          expected_shift_revision: null,
        },
      },
      1,
      null,
    ],
    [
      {
        operation: "shift",
        key: "FAKE-command-6",
        subject,
        body: {
          schema_version: 1,
          expected_revision: 2,
          location_id: location,
          position: "FAKE host",
          starts_at: shift.starts_at,
          ends_at: shift.ends_at,
          required_skill_ids: [],
          status: "cancelled",
          staff_profile_id: null,
        },
      },
      3,
      null,
    ],
  ];
  for (const [command, revision, second] of samples) {
    const reference = commandReference(workforceCommandSchema.parse(command));
    expect(reference.revision, command.operation).toBe(revision);
    expect(reference.skill_id, command.operation).toBe(second);
  }
  const refused: unknown[] = [
    { ...correction, key: "short" },
    { ...correction, body: { ...correction.body, reason: "" } },
    {
      ...correction,
      body: {
        ...correction.body,
        breaks: [
          {
            schema_version: 1,
            starts_at: "2031-06-02T09:00:00Z",
            ends_at: "2031-06-02T10:00:00Z",
          },
        ],
      },
    },
    {
      ...correction,
      body: {
        schema_version: 1,
        expected_revision: 3,
        action: "decline",
        reason: null,
      },
    },
    {
      ...correction,
      body: {
        schema_version: 1,
        expected_revision: 3,
        action: "approve",
        reason: "FAKE",
      },
    },
    {
      ...samples[2]![0],
      body: { ...samples[2]![0].body, kind: "swap" },
    },
    {
      ...samples[3]![0],
      body: { ...samples[3]![0].body, shift_id: subject },
    },
    {
      ...samples[4]![0],
      body: { ...samples[4]![0].body, staff_profile_id: profile },
    },
    { ...correction, operation: "payroll" },
  ];
  for (const command of refused)
    expect(
      workforceCommandSchema.safeParse(command).success,
      JSON.stringify(command),
    ).toBe(false);
});

test("recovery keeps identifiers only, for one person and business", () => {
  const values = new Map<string, string>();
  const store = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
  const descriptor = Object.getOwnPropertyDescriptor(
    globalThis,
    "sessionStorage",
  );
  Object.defineProperty(globalThis, "sessionStorage", {
    value: store,
    configurable: true,
  });
  try {
    expect(readWorkforceRecovery(user, business)).toBeNull();
    const saved = preserveWorkforceRecovery(user, business, correction);
    expect(workforceRecoverySchema.safeParse(saved).success).toBe(true);
    const serialized = Array.from(values.values())[0]!;
    for (const secret of ["FAKE private reason", "reason", "starts_at", "body"])
      expect(serialized).not.toContain(secret);
    expect(readWorkforceRecovery(user, business)?.reference.revision).toBe(4);
    // Another person, or the same person in another business, sees nothing.
    expect(readWorkforceRecovery(other, business)).toBeNull();
    expect(readWorkforceRecovery(user, uuid(16))).toBeNull();
    // The same command may be preserved again; another must wait.
    expect(preserveWorkforceRecovery(user, business, correction).saved_at).toBe(
      saved.saved_at,
    );
    expect(() =>
      preserveWorkforceRecovery(user, business, {
        ...correction,
        key: "FAKE-command-9",
      }),
    ).toThrow(/earlier/);
    clearWorkforceRecovery(user, business, "FAKE-command-9");
    expect(values.size).toBe(1);
    const storageKey = Array.from(values.keys())[0]!;
    store.setItem(
      storageKey,
      JSON.stringify({ ...JSON.parse(serialized), actor_id: other }),
    );
    expect(() => readWorkforceRecovery(user, business)).toThrow(/another/);
    store.setItem(
      storageKey,
      JSON.stringify({ ...JSON.parse(serialized), reason: "FAKE" }),
    );
    expect(() => readWorkforceRecovery(user, business)).toThrow();
    store.setItem(storageKey, "x".repeat(5000));
    expect(() => readWorkforceRecovery(user, business)).toThrow(/safely/);
    store.setItem(storageKey, serialized);
    clearWorkforceRecovery(user, business, correction.key);
    expect(values.size).toBe(0);
  } finally {
    if (descriptor)
      Object.defineProperty(globalThis, "sessionStorage", descriptor);
    else Reflect.deleteProperty(globalThis, "sessionStorage");
  }
});
