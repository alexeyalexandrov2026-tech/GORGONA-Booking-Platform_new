"""Version-one actual-time contracts; UTC durations, explicit human decisions."""

from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from gorgona_booking.business.workforce_contracts import WorkforceModel, _supported_date

type Reason = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=1000, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]
type TimeAction = Literal[
    "clock_in", "break_start", "break_end", "clock_out", "correct", "approve", "decline"
]
type TimeStatus = Literal["open", "proposed", "approved", "declined"]


def microseconds(start: datetime, end: datetime) -> int:
    duration = end.astimezone(UTC) - start.astimezone(UTC)
    return (duration.days * 86400 + duration.seconds) * 1_000_000 + duration.microseconds


class BreakPeriod(WorkforceModel):
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        _supported_date(self.starts_at)
        _supported_date(self.ends_at)
        if microseconds(self.starts_at, self.ends_at) <= 0:
            raise ValueError("A break must have positive elapsed time")
        return self


class ClockInInput(WorkforceModel):
    expected_revision: int = Field(default=0, strict=True, ge=0, le=0)
    staff_profile_id: UUID
    starts_at: AwareDatetime
    shift_id: UUID | None = None
    expected_shift_revision: int | None = Field(default=None, strict=True, ge=1, le=2147483646)

    @model_validator(mode="after")
    def valid_start(self) -> Self:
        _supported_date(self.starts_at)
        if (self.shift_id is None) != (self.expected_shift_revision is None):
            raise ValueError("A shift link requires both identifiers")
        return self


class TimeRevisionInput(WorkforceModel):
    expected_revision: int = Field(strict=True, ge=1, le=2147483646)


class ClockCommand(TimeRevisionInput):
    action: Literal["break_start", "break_end", "clock_out"]
    at: AwareDatetime

    @model_validator(mode="after")
    def valid_date(self) -> Self:
        _supported_date(self.at)
        return self


class CorrectionCommand(TimeRevisionInput):
    action: Literal["correct"]
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    breaks: tuple[BreakPeriod, ...] = Field(default=(), max_length=100)
    reason: Reason

    @model_validator(mode="after")
    def valid_work(self) -> Self:
        _supported_date(self.starts_at)
        _supported_date(self.ends_at)
        if microseconds(self.starts_at, self.ends_at) <= 0:
            raise ValueError("Worked time must have a positive elapsed interval")
        prior = self.starts_at.astimezone(UTC)
        for period in self.breaks:
            if period.starts_at.astimezone(UTC) < prior or period.ends_at.astimezone(
                UTC
            ) > self.ends_at.astimezone(UTC):
                raise ValueError("Breaks must be ordered inside worked time without overlap")
            prior = period.ends_at.astimezone(UTC)
        return self


class DecisionCommand(TimeRevisionInput):
    action: Literal["approve", "decline"]
    reason: Reason | None = None

    @model_validator(mode="after")
    def valid_reason(self) -> Self:
        if (self.action == "decline") != (self.reason is not None):
            raise ValueError("A decline needs a reason; approval keeps the proposed reason")
        return self


type TimeCommand = Annotated[
    ClockCommand | CorrectionCommand | DecisionCommand, Field(discriminator="action")
]


class EffectiveTime(WorkforceModel):
    revision: int
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    breaks: tuple[BreakPeriod, ...]
    worked_microseconds: int
    approved_by: UUID
    approved_at: AwareDatetime
    self_approved: bool
    # The mark of the time that counts; the entry's own mark describes its latest version.
    out_of_schedule: bool


class TimeView(WorkforceModel):
    business_id: UUID
    entry_id: UUID
    staff_profile_id: UUID
    user_id: UUID
    location_id: UUID
    shift_id: UUID | None
    expected_shift_revision: int | None
    revision: int
    action: TimeAction
    status: TimeStatus
    starts_at: AwareDatetime
    ends_at: AwareDatetime | None
    breaks: tuple[BreakPeriod, ...]
    break_started_at: AwareDatetime | None
    reason: str
    reason_source: Literal["system", "human"]
    created_by: UUID
    created_at: AwareDatetime
    self_approved: bool
    out_of_schedule: bool
    worked_microseconds: int | None
    effective: EffectiveTime | None


class TimeList(WorkforceModel):
    items: tuple[TimeView, ...]
    next_cursor: UUID | None = None


class TimeHistory(WorkforceModel):
    items: tuple[TimeView, ...]
    next_revision: int | None = None
