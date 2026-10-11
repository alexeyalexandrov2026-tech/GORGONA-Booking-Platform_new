import { z } from "zod";
import { managementFetch, ManagementApiError } from "./management-api";
import {
  changeHistorySchema,
  changeListSchema,
  changeSchema,
  colleagueListSchema,
  commandStatusSchema,
  deskSchema,
  directoryListSchema,
  locationSettingSchema,
  profileSchema,
  shiftListSchema,
  shiftSchema,
  skillHistorySchema,
  skillListSchema,
  skillSchema,
  staffSkillSchema,
  timeHistorySchema,
  timeListSchema,
  timeSchema,
  workforceCommandSchema,
  type Change,
  type CommandReference,
  type LocationSetting,
  type Profile,
  type Shift,
  type Skill,
  type StaffSkill,
  type TimeEntry,
  type WorkforceCommand,
} from "./workforce-contracts";

const base = (business: string) => `/v1/businesses/${business}/workforce`;
const invalid = () =>
  new ManagementApiError(
    "INVALID_RESPONSE",
    "Unable to load these workforce records safely.",
  );
async function read<T>(
  schema: z.ZodType<T>,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const parsed = schema.safeParse(await managementFetch(path, init));
  if (!parsed.success) throw invalid();
  return parsed.data;
}
/** Every record answers for the requested business, or nothing is shown. */
function owned<T extends { business_id: string }>(
  business: string,
  items: T[],
): T[] {
  if (items.some((item) => item.business_id !== business)) throw invalid();
  return items;
}
function exact(actual: string | number, expected: string | number) {
  if (actual !== expected) throw invalid();
}
const PAGES = 10;
/** Follow cursors to a bounded depth; `more` says the list was cut. */
async function every<T>(
  load: (after?: string) => Promise<{ items: T[]; next_cursor: string | null }>,
): Promise<{ items: T[]; more: boolean }> {
  const items: T[] = [];
  let after: string | undefined;
  for (let index = 0; index < PAGES; index++) {
    const part = await load(after);
    items.push(...part.items);
    if (!part.next_cursor) return { items, more: false };
    after = part.next_cursor;
  }
  return { items, more: true };
}
const cursor = (after?: string, more: Record<string, string> = {}) => {
  const query = new URLSearchParams(more);
  if (after) query.set("after", after);
  const text = query.toString();
  return text ? `?${text}` : "";
};

export async function fetchDesk(business: string) {
  const desk = await read(deskSchema, `${base(business)}/desk`);
  exact(desk.business_id, business);
  return desk;
}
export const fetchDirectory = (business: string) =>
  every((after) =>
    read(directoryListSchema, `${base(business)}/directory${cursor(after)}`),
  );
export async function fetchSkills(business: string) {
  const result = await every((after) =>
    read(skillListSchema, `${base(business)}/skills${cursor(after)}`),
  );
  owned(business, result.items);
  return result;
}
export async function fetchSkillHistory(
  business: string,
  profile: string,
  skill: string,
): Promise<StaffSkill[]> {
  const items: StaffSkill[] = [];
  let after = 0;
  for (let index = 0; index < PAGES; index++) {
    const part = await read(
      skillHistorySchema,
      `${base(business)}/staff/${profile}/skills/${skill}/history?after_revision=${after}`,
    );
    items.push(...owned(business, part.items));
    if (part.next_revision === null) break;
    after = part.next_revision;
  }
  for (const item of items) {
    exact(item.profile_id, profile);
    exact(item.skill_id, skill);
  }
  return items;
}
export type ShiftScope = "shifts" | "my-shifts" | "open-shifts";
export async function fetchShifts(
  business: string,
  scope: ShiftScope,
  starts: string,
  ends: string,
) {
  const result = await every((after) =>
    read(
      shiftListSchema,
      `${base(business)}/${scope}${cursor(after, { starts, ends })}`,
    ),
  );
  owned(business, result.items);
  return result;
}
export async function fetchColleagueShifts(
  business: string,
  profile: string,
  starts: string,
  ends: string,
) {
  const result = await every((after) =>
    read(
      shiftListSchema,
      `${base(business)}/colleagues/${profile}/shifts${cursor(after, { starts, ends })}`,
    ),
  );
  for (const item of owned(business, result.items))
    exact(item.staff_profile_id ?? "", profile);
  return result;
}
export async function fetchShift(
  business: string,
  shift: string,
  revision?: number,
): Promise<Shift> {
  const result = await read(
    shiftSchema,
    `${base(business)}/shifts/${shift}${revision ? `?revision=${revision}` : ""}`,
  );
  exact(result.business_id, business);
  exact(result.shift_id, shift);
  if (revision) exact(result.revision, revision);
  return result;
}
export const fetchColleagues = (business: string) =>
  every((after) =>
    read(colleagueListSchema, `${base(business)}/colleagues${cursor(after)}`),
  );
/** `own` reads through the caller's participation; otherwise the manager's scope. */
export async function fetchChanges(business: string, own: boolean) {
  const result = await every((after) =>
    read(
      changeListSchema,
      `${base(business)}/${own ? "my-changes" : "changes"}${cursor(after)}`,
    ),
  );
  owned(business, result.items);
  return result;
}
export async function fetchChangeHistory(
  business: string,
  request: string,
  own: boolean,
): Promise<Change[]> {
  const part = await read(
    changeHistorySchema,
    `${base(business)}/${own ? "my-changes" : "changes"}/${request}/history`,
  );
  for (const item of owned(business, part.items))
    exact(item.request_id, request);
  return part.items;
}
/** The shift versions a request names, read as one of its participants. */
export async function fetchRequestShifts(
  business: string,
  request: Change,
): Promise<Shift[]> {
  const part = await read(
    shiftListSchema,
    `${base(business)}/my-changes/${request.request_id}/shifts`,
  );
  const named = new Map<string, number | null>([
    [request.shift_id, request.expected_shift_revision],
  ]);
  if (request.other_shift_id)
    named.set(request.other_shift_id, request.expected_other_shift_revision);
  for (const item of owned(business, part.items))
    exact(item.revision, named.get(item.shift_id) ?? -1);
  return part.items;
}
export async function fetchLocationSetting(
  business: string,
  location: string,
): Promise<LocationSetting> {
  const result = await read(
    locationSettingSchema,
    `${base(business)}/locations/${location}/settings`,
  );
  exact(result.business_id, business);
  exact(result.location_id, location);
  return result;
}
export async function fetchTimeEntries(business: string, own: boolean) {
  const result = await every((after) =>
    read(
      timeListSchema,
      `${base(business)}/${own ? "my-time-entries" : "time-entries"}${cursor(after)}`,
    ),
  );
  owned(business, result.items);
  return result;
}
export async function fetchTimeHistory(
  business: string,
  entry: string,
  own: boolean,
): Promise<TimeEntry[]> {
  const items: TimeEntry[] = [];
  let after = 0;
  for (let index = 0; index < PAGES; index++) {
    const part = await read(
      timeHistorySchema,
      `${base(business)}/${own ? "my-time-entries" : "time-entries"}/${entry}/history?after_revision=${after}`,
    );
    items.push(...owned(business, part.items));
    if (part.next_revision === null) break;
    after = part.next_revision;
  }
  for (const item of items) exact(item.entry_id, entry);
  return items;
}

export type WorkforceResult =
  Profile | Skill | StaffSkill | Shift | Change | TimeEntry | LocationSetting;
/** Send one command under its key and accept only the exact expected version. */
export async function executeWorkforceCommand(
  business: string,
  input: WorkforceCommand,
): Promise<WorkforceResult> {
  const command = workforceCommandSchema.parse(input);
  const root = base(business);
  const send = (method: "PUT" | "POST"): RequestInit => ({
    method,
    headers: { "Idempotency-Key": command.key },
    body: JSON.stringify(command.body),
  });
  switch (command.operation) {
    case "profile": {
      const result = await read(
        profileSchema,
        `${root}/staff/${command.subject}`,
        send("PUT"),
      );
      exact(result.business_id, business);
      exact(result.profile_id, command.subject);
      exact(result.membership_id, command.body.membership_id);
      return result;
    }
    case "skill": {
      const result = await read(
        skillSchema,
        `${root}/skills/${command.subject}`,
        send("PUT"),
      );
      exact(result.business_id, business);
      exact(result.skill_id, command.subject);
      exact(result.revision, command.body.expected_revision + 1);
      return result;
    }
    case "staff_skill": {
      const result = await read(
        staffSkillSchema,
        `${root}/staff/${command.subject}/skills/${command.skill}`,
        send("PUT"),
      );
      exact(result.business_id, business);
      exact(result.profile_id, command.subject);
      exact(result.skill_id, command.skill);
      exact(result.revision, command.body.expected_revision + 1);
      return result;
    }
    case "shift": {
      const result = await read(
        shiftSchema,
        `${root}/shifts/${command.subject}`,
        send("PUT"),
      );
      exact(result.business_id, business);
      exact(result.shift_id, command.subject);
      exact(result.revision, command.body.expected_revision + 1);
      return result;
    }
    case "change.propose":
    case "change.event": {
      const result = await read(
        changeSchema,
        command.operation === "change.propose"
          ? `${root}/changes/${command.subject}`
          : `${root}/changes/${command.subject}/events`,
        send(command.operation === "change.propose" ? "PUT" : "POST"),
      );
      exact(result.business_id, business);
      exact(result.request_id, command.subject);
      exact(
        result.revision,
        command.operation === "change.propose"
          ? 1
          : command.body.expected_revision + 1,
      );
      return result;
    }
    case "location_setting": {
      const result = await read(
        locationSettingSchema,
        `${root}/locations/${command.subject}/settings`,
        send("PUT"),
      );
      exact(result.business_id, business);
      exact(result.location_id, command.subject);
      exact(result.revision, command.body.expected_revision + 1);
      if (
        result.colleague_shifts_visible !==
        command.body.colleague_shifts_visible
      )
        throw invalid();
      return result;
    }
    case "time.clock_in":
    case "time.event": {
      const result = await read(
        timeSchema,
        command.operation === "time.clock_in"
          ? `${root}/time-entries/${command.subject}`
          : `${root}/time-entries/${command.subject}/events`,
        send(command.operation === "time.clock_in" ? "PUT" : "POST"),
      );
      exact(result.business_id, business);
      exact(result.entry_id, command.subject);
      exact(
        result.revision,
        command.operation === "time.clock_in"
          ? 1
          : command.body.expected_revision + 1,
      );
      return result;
    }
  }
}
/** Ask what happened to a sent command by its key; `cancel` retires an unsent one. */
export async function resolveWorkforceCommand(
  business: string,
  key: string,
  reference: CommandReference,
  cancel = false,
) {
  const result = await read(
    commandStatusSchema,
    `${base(business)}/commands/${encodeURIComponent(key)}/${cancel ? "cancel" : "resolve"}`,
    { method: "POST", body: JSON.stringify(reference) },
  );
  exact(result.business_id, business);
  exact(result.key, key);
  exact(result.operation, reference.operation);
  return result;
}
