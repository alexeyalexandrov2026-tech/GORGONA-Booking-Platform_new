"""I2 version-one consent contracts; receipts reference immutable events."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from gorgona_booking.business.workforce_contracts import RevisionInput, WorkforceModel

type ChangeKind = Literal["handover", "swap", "pickup"]
type ChangeAction = Literal["accept", "approve", "decline", "withdraw"]
type ChangeStatus = Literal["proposed", "accepted", "approved", "declined", "withdrawn"]


class ChangeInput(WorkforceModel):
    kind: ChangeKind
    shift_id: UUID
    expected_shift_revision: int = Field(strict=True, ge=1, le=2147483646)
    target_profile_id: UUID
    other_shift_id: UUID | None = None
    expected_other_shift_revision: int | None = Field(
        default=None, strict=True, ge=1, le=2147483646
    )

    @model_validator(mode="after")
    def valid_shape(self) -> Self:
        if self.kind == "swap":
            if self.other_shift_id is None or self.expected_other_shift_revision is None:
                raise ValueError("A swap needs both expected shift versions")
            if self.other_shift_id == self.shift_id:
                raise ValueError("A swap needs two different shifts")
        elif self.other_shift_id is not None or self.expected_other_shift_revision is not None:
            raise ValueError("Only a swap references a second shift")
        return self


class ChangeEventInput(RevisionInput):
    expected_revision: int = Field(strict=True, ge=1, le=2147483646)
    action: ChangeAction


class AppliedShift(WorkforceModel):
    shift_id: UUID
    revision: int


class ChangeView(WorkforceModel):
    business_id: UUID
    request_id: UUID
    kind: ChangeKind
    location_id: UUID
    other_location_id: UUID | None
    shift_id: UUID
    expected_shift_revision: int
    other_shift_id: UUID | None
    expected_other_shift_revision: int | None
    from_profile_id: UUID | None
    target_profile_id: UUID
    proposed_by: UUID
    recipient_user_id: UUID
    revision: int
    status: ChangeStatus
    event_created_by: UUID
    event_created_at: AwareDatetime
    applied_shifts: tuple[AppliedShift, ...] = ()


class ChangeList(WorkforceModel):
    items: tuple[ChangeView, ...]
    next_cursor: UUID | None = None


class ChangeHistory(WorkforceModel):
    items: tuple[ChangeView, ...]
    next_revision: int | None = None


class ColleagueView(WorkforceModel):
    profile_id: UUID
    display_name: str


class ColleagueList(WorkforceModel):
    items: tuple[ColleagueView, ...]
    next_cursor: UUID | None = None
