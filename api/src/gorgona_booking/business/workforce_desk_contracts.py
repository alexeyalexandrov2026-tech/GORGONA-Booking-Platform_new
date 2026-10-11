"""I4 screen-support contracts: identifiers and names only, never a command body."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from gorgona_booking.business.workforce_contracts import ProfileView, WorkforceModel

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
]
type CommandState = Literal["committed", "unresolved", "cancelled"]


class DeskView(WorkforceModel):
    business_id: UUID
    writes: WriteState
    profile: ProfileView | None


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
