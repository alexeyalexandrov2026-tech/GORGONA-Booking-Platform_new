"""I4 screen-support contracts: identifiers and names only, never a command body."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool

from gorgona_booking.business.workforce_contracts import (
    ProfileView,
    RevisionInput,
    WorkforceModel,
)

type WriteState = Literal["open", "module_disabled", "not_accepted"]
type CommandOperation = Literal[
    "profile",
    "skill",
    "staff_skill",
    "shift",
    "change.propose",
    "change.event",
    "time.clock_in",
    "time.event",
    "location_setting",
]
type CommandState = Literal["committed", "unresolved", "cancelled"]
type ShiftVisibility = Literal["visible", "hidden"]


class DeskView(WorkforceModel):
    business_id: UUID
    writes: WriteState
    profile: ProfileView | None
    # Whether the caller's home branch shows colleagues' published shifts.
    colleague_shifts: ShiftVisibility


class LocationSettingInput(RevisionInput):
    colleague_shifts_visible: StrictBool


class LocationSettingView(WorkforceModel):
    """A branch setting; revision 0 is the default nobody has changed."""

    business_id: UUID
    location_id: UUID
    revision: int
    colleague_shifts_visible: bool
    changed_by: UUID | None
    changed_at: datetime | None


class DirectoryEntry(WorkforceModel):
    membership_id: UUID
    user_id: UUID
    display_name: str | None
    role: str
    location_id: UUID | None
    profile_id: UUID | None
    home_location_id: UUID | None


class DirectoryList(WorkforceModel):
    items: tuple[DirectoryEntry, ...]
    next_cursor: UUID | None = None


class CommandReference(WorkforceModel):
    """What the sender expected a command to produce; no reason, name or time."""

    operation: CommandOperation
    subject_id: UUID
    revision: int = Field(strict=True, ge=0, le=2147483647)
    skill_id: UUID | None = None


class CancelledCommand(CommandReference):
    cancelled: Literal[True] = True


class CommandStatus(WorkforceModel):
    business_id: UUID
    key: str
    operation: CommandOperation
    state: CommandState
