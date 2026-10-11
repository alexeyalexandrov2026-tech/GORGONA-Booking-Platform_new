import { z } from "zod";

const v1 = z.literal(1);
const id = z.uuid();
const instant = z.iso.datetime({ offset: true });
const revision = z.int().min(1).max(2147483647);
// The server limits text in Unicode code points, not UTF-16 units.
const text = (min: number, max: number) =>
  z
    .string()
    .regex(/^[^\x00-\x1f\x7f]+$/)
    .refine((value) => {
      const length = Array.from(value).length;
      return length >= min && length <= max;
    });
const ordered = (start: string, end: string) =>
  Date.parse(start) < Date.parse(end);
function page<T extends z.ZodType, K extends string>(item: T, key: K) {
  return z
    .strictObject({
      schema_version: v1,
      items: z.array(item).max(100),
      next_cursor: id.nullable(),
    })
    .refine(
      (value) =>
        new Set(value.items.map((entry) => (entry as Record<K, string>)[key]))
          .size === value.items.length,
    );
}
function history<T extends z.ZodType>(item: T) {
  return z
    .strictObject({
      schema_version: v1,
      items: z.array(item).max(100),
      next_revision: revision.nullable(),
    })
    .refine((value) =>
      value.items.every(
        (entry, index) =>
          index === 0 ||
          (entry as { revision: number }).revision >
            (value.items[index - 1] as { revision: number }).revision,
      ),
    );
}

export const profileSchema = z.strictObject({
  schema_version: v1,
  business_id: id,
  profile_id: id,
  membership_id: id,
  resource_id: id,
  location_id: id,
  user_id: id,
});
export const profileListSchema = page(profileSchema, "profile_id");

export const skillSchema = z.strictObject({
  schema_version: v1,
  business_id: id,
  skill_id: id,
  code: z.string().regex(/^[A-Z][A-Z0-9_]{0,63}$/),
  revision,
  name: text(1, 200),
  archived: z.boolean(),
});
export const skillListSchema = page(skillSchema, "skill_id");

export const staffSkillSchema = z.strictObject({
  schema_version: v1,
  business_id: id,
  profile_id: id,
  skill_id: id,
  revision,
  effective_at: instant,
  granted: z.boolean(),
});
export const skillHistorySchema = history(staffSkillSchema);

export const shiftStatusSchema = z.enum(["draft", "published", "cancelled"]);
export const shiftSchema = z
  .strictObject({
    schema_version: v1,
    business_id: id,
    shift_id: id,
    location_id: id,
    revision,
    position: text(1, 200),
    starts_at: instant,
    ends_at: instant,
    required_skill_ids: z.array(id).max(20),
    status: shiftStatusSchema,
    staff_profile_id: id.nullable(),
    assignment_id: id.nullable(),
  })
  .refine(
    (value) =>
      ordered(value.starts_at, value.ends_at) &&
      new Set(value.required_skill_ids).size ===
        value.required_skill_ids.length &&
      (value.staff_profile_id === null || value.status === "published"),
  );
export const shiftListSchema = page(shiftSchema, "shift_id");

export const changeKindSchema = z.enum(["handover", "swap", "pickup"]);
export const changeStatusSchema = z.enum([
  "proposed",
  "accepted",
  "approved",
  "declined",
  "withdrawn",
]);
const appliedShiftSchema = z.strictObject({
  schema_version: v1,
  shift_id: id,
  revision,
});
export const changeSchema = z
  .strictObject({
    schema_version: v1,
    business_id: id,
    request_id: id,
    kind: changeKindSchema,
    location_id: id,
    other_location_id: id.nullable(),
    shift_id: id,
    expected_shift_revision: revision,
    other_shift_id: id.nullable(),
    expected_other_shift_revision: revision.nullable(),
    from_profile_id: id.nullable(),
    target_profile_id: id,
    proposed_by: id,
    recipient_user_id: id,
    revision,
    status: changeStatusSchema,
    event_created_by: id,
    event_created_at: instant,
    applied_shifts: z.array(appliedShiftSchema).max(2),
  })
  .refine(
    (value) =>
      (value.kind === "swap") === (value.other_shift_id !== null) &&
      (value.other_shift_id === null) ===
        (value.expected_other_shift_revision === null) &&
      (value.kind === "pickup") === (value.from_profile_id === null) &&
      (value.status === "approved") === value.applied_shifts.length > 0,
  );
export const changeListSchema = page(changeSchema, "request_id");
export const changeHistorySchema = history(changeSchema);

export const colleagueSchema = z.strictObject({
  schema_version: v1,
  profile_id: id,
  display_name: z.string().max(400),
});
export const colleagueListSchema = page(colleagueSchema, "profile_id");

const breakSchema = z
  .strictObject({ schema_version: v1, starts_at: instant, ends_at: instant })
  .refine((value) => ordered(value.starts_at, value.ends_at));
const worked = z.int().min(0);
const effectiveSchema = z
  .strictObject({
    schema_version: v1,
    revision,
    starts_at: instant,
    ends_at: instant,
    breaks: z.array(breakSchema).max(100),
    worked_microseconds: worked,
    approved_by: id,
    approved_at: instant,
    self_approved: z.boolean(),
  })
  .refine((value) => ordered(value.starts_at, value.ends_at));
export const timeActionSchema = z.enum([
  "clock_in",
  "break_start",
  "break_end",
  "clock_out",
  "correct",
  "approve",
  "decline",
]);
export const timeStatusSchema = z.enum([
  "open",
  "proposed",
  "approved",
  "declined",
]);
export const timeSchema = z
  .strictObject({
    schema_version: v1,
    business_id: id,
    entry_id: id,
    staff_profile_id: id,
    user_id: id,
    location_id: id,
    shift_id: id.nullable(),
    expected_shift_revision: revision.nullable(),
    revision,
    action: timeActionSchema,
    status: timeStatusSchema,
    starts_at: instant,
    ends_at: instant.nullable(),
    breaks: z.array(breakSchema).max(100),
    break_started_at: instant.nullable(),
    reason: z.string().max(4000),
    created_by: id,
    created_at: instant,
    self_approved: z.boolean(),
    out_of_schedule: z.boolean(),
    worked_microseconds: worked.nullable(),
    effective: effectiveSchema.nullable(),
  })
  .refine(
    (value) =>
      (value.shift_id === null) === (value.expected_shift_revision === null) &&
      (value.status === "open") === (value.ends_at === null) &&
      (value.ends_at === null || ordered(value.starts_at, value.ends_at)) &&
      (value.break_started_at === null || value.status === "open") &&
      (value.ends_at === null) === (value.worked_microseconds === null),
  );
export const timeListSchema = page(timeSchema, "entry_id");
export const timeHistorySchema = history(timeSchema);

export const writeStateSchema = z.enum([
  "open",
  "module_disabled",
  "not_accepted",
]);
export const deskSchema = z
  .strictObject({
    schema_version: v1,
    business_id: id,
    writes: writeStateSchema,
    profile: profileSchema.nullable(),
    // Whether the caller's home location shows colleagues' published shifts.
    colleague_shifts: z.enum(["visible", "hidden"]),
  })
  .refine(
    (value) =>
      value.profile === null || value.profile.business_id === value.business_id,
  );
export const directoryEntrySchema = z
  .strictObject({
    schema_version: v1,
    membership_id: id,
    user_id: id,
    display_name: z.string().max(400).nullable(),
    role: z.enum(["owner", "manager", "front_desk", "artist"]),
    location_id: id.nullable(),
    profile_id: id.nullable(),
    home_location_id: id.nullable(),
  })
  .refine(
    (value) =>
      (value.profile_id === null) === (value.home_location_id === null),
  );
export const directoryListSchema = page(directoryEntrySchema, "membership_id");
/** A location setting; revision 0 is the default nobody has changed. */
export const locationSettingSchema = z
  .strictObject({
    schema_version: v1,
    business_id: id,
    location_id: id,
    revision: z.int().min(0).max(2147483647),
    colleague_shifts_visible: z.boolean(),
    changed_by: id.nullable(),
    changed_at: instant.nullable(),
  })
  .refine(
    (value) =>
      (value.revision === 0) === (value.changed_by === null) &&
      (value.changed_by === null) === (value.changed_at === null) &&
      (value.revision > 0 || value.colleague_shifts_visible),
  );

export const commandOperationSchema = z.enum([
  "profile",
  "skill",
  "staff_skill",
  "shift",
  "change.propose",
  "change.event",
  "time.clock_in",
  "time.event",
  "location_setting",
]);
/** Identifiers only: what a sent command was expected to produce. */
export const commandReferenceSchema = z.strictObject({
  schema_version: v1,
  operation: commandOperationSchema,
  subject_id: id,
  revision: z.int().min(0).max(2147483647),
  skill_id: id.nullable(),
});
export const commandKeySchema = z.string().regex(/^[A-Za-z0-9._:-]{8,255}$/);
export const commandStatusSchema = z.strictObject({
  schema_version: v1,
  business_id: id,
  key: commandKeySchema,
  operation: commandOperationSchema,
  state: z.enum(["committed", "unresolved", "cancelled"]),
});

const expected = z.int().min(0).max(2147483646);
const shiftBody = z
  .strictObject({
    schema_version: v1,
    expected_revision: expected,
    location_id: id,
    position: text(1, 200),
    starts_at: instant,
    ends_at: instant,
    required_skill_ids: z.array(id).max(20),
    status: shiftStatusSchema,
    staff_profile_id: id.nullable(),
  })
  .refine(
    (value) =>
      ordered(value.starts_at, value.ends_at) &&
      Date.parse(value.ends_at) - Date.parse(value.starts_at) <=
        31 * 86_400_000 &&
      new Set(value.required_skill_ids).size ===
        value.required_skill_ids.length &&
      (value.staff_profile_id === null || value.status === "published"),
  );
const changeBody = z
  .strictObject({
    schema_version: v1,
    kind: changeKindSchema,
    shift_id: id,
    expected_shift_revision: revision,
    target_profile_id: id,
    other_shift_id: id.nullable(),
    expected_other_shift_revision: revision.nullable(),
  })
  .refine(
    (value) =>
      (value.kind === "swap") === (value.other_shift_id !== null) &&
      (value.other_shift_id === null) ===
        (value.expected_other_shift_revision === null) &&
      value.other_shift_id !== value.shift_id,
  );
const clockBody = z.strictObject({
  schema_version: v1,
  expected_revision: revision,
  action: z.enum(["break_start", "break_end", "clock_out"]),
  at: instant,
});
const correctionBody = z
  .strictObject({
    schema_version: v1,
    expected_revision: revision,
    action: z.literal("correct"),
    starts_at: instant,
    ends_at: instant,
    breaks: z.array(breakSchema).max(100),
    reason: text(1, 1000),
  })
  .refine((value) => {
    if (!ordered(value.starts_at, value.ends_at)) return false;
    let prior = Date.parse(value.starts_at);
    for (const period of value.breaks) {
      if (
        Date.parse(period.starts_at) < prior ||
        Date.parse(period.ends_at) > Date.parse(value.ends_at)
      )
        return false;
      prior = Date.parse(period.ends_at);
    }
    return true;
  });
const decisionBody = z
  .strictObject({
    schema_version: v1,
    expected_revision: revision,
    action: z.enum(["approve", "decline"]),
    reason: text(1, 1000).nullable(),
  })
  .refine((value) => (value.action === "decline") === (value.reason !== null));
const sent = { key: commandKeySchema, subject: id };
export const workforceCommandSchema = z.discriminatedUnion("operation", [
  z.strictObject({
    operation: z.literal("profile"),
    ...sent,
    body: z.strictObject({
      schema_version: v1,
      membership_id: id,
      location_id: id,
    }),
  }),
  z.strictObject({
    operation: z.literal("skill"),
    ...sent,
    body: z.strictObject({
      schema_version: v1,
      expected_revision: expected,
      code: z.string().regex(/^[A-Z][A-Z0-9_]{0,63}$/),
      name: text(1, 200),
      archived: z.boolean(),
    }),
  }),
  z.strictObject({
    operation: z.literal("staff_skill"),
    ...sent,
    skill: id,
    body: z.strictObject({
      schema_version: v1,
      expected_revision: expected,
      effective_at: instant,
      granted: z.boolean(),
    }),
  }),
  z.strictObject({ operation: z.literal("shift"), ...sent, body: shiftBody }),
  z.strictObject({
    operation: z.literal("change.propose"),
    ...sent,
    body: changeBody,
  }),
  z.strictObject({
    operation: z.literal("change.event"),
    ...sent,
    body: z.strictObject({
      schema_version: v1,
      expected_revision: revision,
      action: z.enum(["accept", "approve", "decline", "withdraw"]),
    }),
  }),
  z.strictObject({
    operation: z.literal("time.clock_in"),
    ...sent,
    body: z
      .strictObject({
        schema_version: v1,
        expected_revision: z.literal(0),
        staff_profile_id: id,
        starts_at: instant,
        shift_id: id.nullable(),
        expected_shift_revision: revision.nullable(),
      })
      .refine(
        (value) =>
          (value.shift_id === null) ===
          (value.expected_shift_revision === null),
      ),
  }),
  z.strictObject({
    operation: z.literal("time.event"),
    ...sent,
    body: z.union([clockBody, correctionBody, decisionBody]),
  }),
  z.strictObject({
    operation: z.literal("location_setting"),
    ...sent,
    body: z.strictObject({
      schema_version: v1,
      expected_revision: expected,
      colleague_shifts_visible: z.boolean(),
    }),
  }),
]);

/** The version a command creates; the server stores the same pair in its receipt. */
export function commandReference(command: WorkforceCommand): CommandReference {
  let produced = 1;
  if (command.operation === "profile") produced = 0;
  else if (
    command.operation !== "change.propose" &&
    command.operation !== "time.clock_in"
  )
    produced = command.body.expected_revision + 1;
  return commandReferenceSchema.parse({
    schema_version: 1,
    operation: command.operation,
    subject_id: command.subject,
    revision: produced,
    skill_id: command.operation === "staff_skill" ? command.skill : null,
  });
}

const uuid = "[0-9a-f-]{36}";
const routes: [RegExp, string[], z.ZodType][] = [
  [/^\/desk$/, ["GET"], deskSchema],
  [/^\/directory$/, ["GET"], directoryListSchema],
  [/^\/staff$/, ["GET"], profileListSchema],
  [new RegExp(`^/staff/${uuid}$`, "i"), ["PUT"], profileSchema],
  [/^\/skills$/, ["GET"], skillListSchema],
  [new RegExp(`^/skills/${uuid}$`, "i"), ["GET", "PUT"], skillSchema],
  [
    new RegExp(`^/staff/${uuid}/skills/${uuid}$`, "i"),
    ["PUT"],
    staffSkillSchema,
  ],
  [
    new RegExp(`^/staff/${uuid}/skills/${uuid}/history$`, "i"),
    ["GET"],
    skillHistorySchema,
  ],
  [/^\/(shifts|my-shifts|open-shifts)$/, ["GET"], shiftListSchema],
  [new RegExp(`^/colleagues/${uuid}/shifts$`, "i"), ["GET"], shiftListSchema],
  [new RegExp(`^/shifts/${uuid}$`, "i"), ["GET", "PUT"], shiftSchema],
  [/^\/colleagues$/, ["GET"], colleagueListSchema],
  [/^\/(changes|my-changes)$/, ["GET"], changeListSchema],
  [new RegExp(`^/changes/${uuid}$`, "i"), ["GET", "PUT"], changeSchema],
  [new RegExp(`^/my-changes/${uuid}$`, "i"), ["GET"], changeSchema],
  [new RegExp(`^/my-changes/${uuid}/shifts$`, "i"), ["GET"], shiftListSchema],
  [
    new RegExp(`^/locations/${uuid}/settings$`, "i"),
    ["GET", "PUT"],
    locationSettingSchema,
  ],
  [new RegExp(`^/changes/${uuid}/events$`, "i"), ["POST"], changeSchema],
  [
    new RegExp(`^/(changes|my-changes)/${uuid}/history$`, "i"),
    ["GET"],
    changeHistorySchema,
  ],
  [/^\/(time-entries|my-time-entries)$/, ["GET"], timeListSchema],
  [new RegExp(`^/time-entries/${uuid}$`, "i"), ["GET", "PUT"], timeSchema],
  [new RegExp(`^/my-time-entries/${uuid}$`, "i"), ["GET"], timeSchema],
  [new RegExp(`^/time-entries/${uuid}/events$`, "i"), ["POST"], timeSchema],
  [
    new RegExp(`^/(time-entries|my-time-entries)/${uuid}/history$`, "i"),
    ["GET"],
    timeHistorySchema,
  ],
  [
    /^\/commands\/[A-Za-z0-9._:-]{8,255}\/(resolve|cancel)$/,
    ["POST"],
    commandStatusSchema,
  ],
];
export function workforceResponseSchema(
  path: string,
  method: string,
): z.ZodType | null {
  if (!path.startsWith("/workforce/")) return null;
  const rest = path.slice("/workforce".length);
  for (const [pattern, methods, schema] of routes)
    if (pattern.test(rest)) return methods.includes(method) ? schema : null;
  return null;
}

export type Profile = z.infer<typeof profileSchema>;
export type Skill = z.infer<typeof skillSchema>;
export type StaffSkill = z.infer<typeof staffSkillSchema>;
export type Shift = z.infer<typeof shiftSchema>;
export type ShiftStatus = z.infer<typeof shiftStatusSchema>;
export type Change = z.infer<typeof changeSchema>;
export type ChangeKind = z.infer<typeof changeKindSchema>;
export type Colleague = z.infer<typeof colleagueSchema>;
export type TimeEntry = z.infer<typeof timeSchema>;
export type Desk = z.infer<typeof deskSchema>;
export type LocationSetting = z.infer<typeof locationSettingSchema>;
export type WriteState = z.infer<typeof writeStateSchema>;
export type DirectoryEntry = z.infer<typeof directoryEntrySchema>;
export type CommandReference = z.infer<typeof commandReferenceSchema>;
export type CommandStatus = z.infer<typeof commandStatusSchema>;
export type WorkforceCommand = z.infer<typeof workforceCommandSchema>;
