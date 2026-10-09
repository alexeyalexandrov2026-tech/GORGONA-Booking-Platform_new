"""Strict version-one workforce contracts; no payroll or booking-derived fields."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

type Label = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=200, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]

_MIN_DATE = datetime(2, 1, 1, tzinfo=UTC)
_MAX_DATE = datetime(9999, 1, 1, tzinfo=UTC)


def _supported_date(value: datetime) -> None:
    if not _MIN_DATE <= value < _MAX_DATE:
        raise ValueError("Workforce dates must be within the supported timestamp range")


class WorkforceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1


class RevisionInput(WorkforceModel):
    expected_revision: int = Field(ge=0, le=2147483646)


class ProfileInput(WorkforceModel):
    membership_id: UUID
    location_id: UUID


class ProfileView(WorkforceModel):
    business_id: UUID
    profile_id: UUID
    membership_id: UUID
    resource_id: UUID
    location_id: UUID
    user_id: UUID


class SkillInput(RevisionInput):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    name: Label
    archived: bool = False


class SkillView(WorkforceModel):
    business_id: UUID
    skill_id: UUID
    code: str
    revision: int
    name: str
    archived: bool


class StaffSkillInput(RevisionInput):
    effective_at: AwareDatetime
    granted: bool

    @model_validator(mode="after")
    def valid_date(self) -> Self:
        _supported_date(self.effective_at)
        return self


class StaffSkillView(WorkforceModel):
    business_id: UUID
    profile_id: UUID
    skill_id: UUID
    revision: int
    effective_at: AwareDatetime
    granted: bool


class ShiftInput(RevisionInput):
    location_id: UUID
    position: Label
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    required_skill_ids: tuple[UUID, ...] = Field(default=(), max_length=20)
    status: Literal["draft", "published", "cancelled"] = "draft"
    staff_profile_id: UUID | None = None

    @model_validator(mode="after")
    def valid_shift(self) -> Self:
        _supported_date(self.starts_at)
        _supported_date(self.ends_at)
        if not timedelta(0) < self.ends_at - self.starts_at <= timedelta(days=31):
            raise ValueError("A shift must end after its start, within 31 days")
        if len(set(self.required_skill_ids)) != len(self.required_skill_ids):
            raise ValueError("Required skills must be unique")
        if self.staff_profile_id is not None and self.status != "published":
            raise ValueError("Only a published shift may have an assignment")
        return self


class AssignmentInput(RevisionInput):
    staff_profile_id: UUID


class ShiftView(WorkforceModel):
    business_id: UUID
    shift_id: UUID
    location_id: UUID
    revision: int
    position: str
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    required_skill_ids: tuple[UUID, ...]
    status: Literal["draft", "published", "cancelled"]
    staff_profile_id: UUID | None
    assignment_id: UUID | None


class WorkforceReceipt(WorkforceModel):
    subject_id: UUID
    revision: int = 0
    # Used only for a staff-skill command's second tenant-owned reference.
    skill_id: UUID | None = None


class ProfileList(WorkforceModel):
    items: tuple[ProfileView, ...]
    next_cursor: UUID | None = None


class SkillList(WorkforceModel):
    items: tuple[SkillView, ...]
    next_cursor: UUID | None = None


class ShiftList(WorkforceModel):
    items: tuple[ShiftView, ...]
    next_cursor: UUID | None = None


class SkillHistory(WorkforceModel):
    items: tuple[StaffSkillView, ...]
    next_revision: int | None = None
