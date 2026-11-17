"""Boundary models for strategy comparison: the user's constraints, the options, the market data.

`hours_per_week` and `minutes_per_unit` are `Sourced` so callers must say whether the figure was
given by the user or is our assumption. The comparison reasons repeat that tag.
"""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.engine.feasibility import Money, Sourced

HOURS_IN_WEEK = 168

VerificationStatus = Literal["verified", "single_source", "unverified_sample"]
SignalStrength = Literal["low", "medium", "high"]


class ConstraintProfile(BaseModel):
    """Everything we know about the entrepreneur's real constraints."""

    model_config = ConfigDict(frozen=True)

    budget: Money
    units_per_day: Annotated[int, Field(ge=0)]
    days_per_week: Annotated[int, Field(ge=0, le=7)]
    hours_per_week: Sourced[Annotated[int, Field(ge=0, le=HOURS_IN_WEEK)]]
    skills: list[str]
    equipment: list[str]
    location: str


class StrategyOption(BaseModel):
    """One business option. The original idea is the option with `is_original=True`."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    is_original: bool = False
    price: Money
    variable_cost_per_unit: Money
    fixed_startup_costs: Money
    minutes_per_unit: Sourced[Annotated[int, Field(ge=0)]]
    required_skills: list[str] = Field(default_factory=list)
    required_equipment: list[str] = Field(default_factory=list)
    opportunity_id: str | None = None


class Opportunity(BaseModel):
    """A hand-curated market opportunity (see docs/SPEC.md, market dataset)."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    title: str
    location: str
    category: str
    signal_summary: str
    evidence: str
    source_name: str
    source_url: HttpUrl
    event_date: date | None = None
    is_evergreen: bool = False
    retrieved_date: date
    verification_status: VerificationStatus
    verified_by: str | None = None
    verified_on: date | None = None
    signal_strength: SignalStrength
    required_skills: list[str]
    required_equipment: list[str]
    lead_time_days: Annotated[int, Field(ge=0)]
    label: str

    @model_validator(mode="after")
    def _check_dates_and_verifier(self) -> Self:
        # Never fabricate a date: a dated entry must carry one; evergreen entries never expire.
        if self.event_date is None and not self.is_evergreen:
            raise ValueError("event_date is required unless is_evergreen is True")
        if self.verification_status == "verified" and (
            self.verified_by is None or self.verified_on is None
        ):
            raise ValueError("verified_by and verified_on are required when status is verified")
        return self

    def has_passed(self, today: date) -> bool:
        """True for a dated entry whose event is before `today`. Evergreen never passes."""
        return not self.is_evergreen and self.event_date is not None and self.event_date < today
