"""Request and response models for the analyze endpoint, plus the typed step log.

The request models subclass the domain models (`ConstraintProfile`, `StrategyOption`) and only
tighten them: bounded money, bounded text, bounded lists. The services take them unchanged, so
there is no mapping layer. They live beside `strategy_models` because they build on it.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from app.engine.feasibility import FeasibilityResult, Money, Sourced
from app.schemas.text import reject_control_characters
from app.services.strategy_models import (
    ConstraintProfile,
    HoursPerWeek,
    Opportunity,
    OptionScore,
    RankedStrategies,
    StrategyOption,
)

MAX_OPTIONS = 6
MAX_MONEY = Decimal("10000000")  # Rs 1 crore: far above any first-time business, and bounded
MAX_UNITS_PER_DAY = 10_000
MAX_MINUTES_PER_UNIT = 1_440  # a whole day
MAX_LIST_ITEMS = 20

# ASSUMPTIONS (our choice, not measured): used only when the owner leaves a figure blank. They are
# always tagged "assumption", so the engine's existing caveats say they were not provided.
DEFAULT_HOURS_PER_WEEK = 20  # a part-time business
DEFAULT_MINUTES_PER_UNIT = 60

_CLEAN = AfterValidator(reject_control_characters)


def _text(max_length: int) -> StringConstraints:
    return StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)


ShortText = Annotated[str, _text(60), _CLEAN]
Title = Annotated[str, _text(80), _CLEAN]
Place = Annotated[str, _text(80), _CLEAN]
Category = Annotated[str, _text(60), _CLEAN]
# Option ids are chosen by the caller: lowercase slugs. Opportunity ids come from the dataset,
# which uses upper case (PUNE-001), so they get their own pattern.
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")]
OpportunityId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")]
BoundedMoney = Annotated[Money, Field(le=MAX_MONEY, decimal_places=2)]
NameList = Annotated[list[ShortText], Field(max_length=MAX_LIST_ITEMS)]


# The same parametrised types as the fields, so the defaults serialise without warnings.
MinutesPerUnit = Sourced[Annotated[int, Field(ge=0, le=MAX_MINUTES_PER_UNIT)]]


class AnalyzeProfile(ConstraintProfile):
    model_config = ConfigDict(frozen=True, extra="forbid")

    budget: BoundedMoney
    # Left out, this is an assumption. An explicit null is still rejected.
    hours_per_week: HoursPerWeek = HoursPerWeek(value=DEFAULT_HOURS_PER_WEEK, source="assumption")
    units_per_day: Annotated[int, Field(ge=0, le=MAX_UNITS_PER_DAY)]
    skills: NameList
    equipment: NameList
    location: Place


class AnalyzeOption(StrategyOption):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Slug
    title: Title
    price: BoundedMoney
    variable_cost_per_unit: BoundedMoney
    fixed_startup_costs: BoundedMoney
    minutes_per_unit: MinutesPerUnit = MinutesPerUnit(
        value=DEFAULT_MINUTES_PER_UNIT, source="assumption"
    )
    required_skills: NameList = Field(default_factory=list)
    required_equipment: NameList = Field(default_factory=list)
    opportunity_id: OpportunityId | None = None


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: AnalyzeProfile
    category: Category
    options: Annotated[list[AnalyzeOption], Field(min_length=1, max_length=MAX_OPTIONS)]

    @field_validator("options")
    @classmethod
    def _one_original_and_unique_ids(cls, options: list[AnalyzeOption]) -> list[AnalyzeOption]:
        if sum(1 for o in options if o.is_original) != 1:
            raise ValueError("exactly one option must be the original idea")
        ids = [o.id for o in options]
        if len(set(ids)) != len(ids):
            raise ValueError("option ids must be unique")
        return options


# ---- response ---------------------------------------------------------------------------------

Coverage = Literal["covered", "none"]


class OptionAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    option_id: str
    title: str
    is_original: bool
    opportunity_id: str | None
    feasibility: FeasibilityResult
    score: OptionScore


class ValidatedConstraints(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile: ConstraintProfile
    category: str
    option_count: int


class MarketQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    location: str
    category: str


class MarketQueryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    coverage: Coverage
    dataset_entries: int
    linked_ids: list[str]


class FeasibilityQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    option_id: str


class ComparisonSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    ranked_ids: list[str]
    viable_ids: list[str]
    recommended_id: str | None
    keep_original: bool


class _StepBase(BaseModel):
    """One tool-style step. No timestamps or durations, so the same input gives the same bytes."""

    model_config = ConfigDict(frozen=True)

    index: int
    title: str
    status: Literal["ok"] = "ok"


class ValidateConstraintsStep(_StepBase):
    tool: Literal["validate_constraints"] = "validate_constraints"
    result: ValidatedConstraints


class QueryMarketStep(_StepBase):
    tool: Literal["query_market_opportunities"] = "query_market_opportunities"
    input: MarketQuery
    result: MarketQueryResult


class RunFeasibilityStep(_StepBase):
    tool: Literal["run_feasibility"] = "run_feasibility"
    input: FeasibilityQuery
    result: FeasibilityResult


class CompareStrategiesStep(_StepBase):
    tool: Literal["compare_strategies"] = "compare_strategies"
    result: ComparisonSummary


Step = Annotated[
    ValidateConstraintsStep | QueryMarketStep | RunFeasibilityStep | CompareStrategiesStep,
    Field(discriminator="tool"),
]


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    analyzed_on: date
    market_coverage: Coverage
    market_message: str
    profile: ConstraintProfile
    category: str
    # True when the category or an option title names food: the screen then shows the FSSAI note.
    food_business: bool
    options: list[OptionAnalysis]
    skipped_option_ids: list[str]
    ranking: RankedStrategies
    evidence: list[Opportunity]
    steps: list[Step]
