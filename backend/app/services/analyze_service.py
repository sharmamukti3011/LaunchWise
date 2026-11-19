"""Analyze a business scenario deterministically: engine numbers, ranking, caveats, step log.

No Claude, no database, no network. Market evidence comes only from the loaded dataset. When the
dataset has no coverage for the place or business, the analysis is feasibility-only: the original
option's numbers and caveats, a neutral market signal, no alternatives compared, no invented
evidence.
"""

from datetime import timedelta, timezone
from typing import Literal

from app.engine.feasibility import FeasibilityResult
from app.services.analyze_models import (
    AnalyzeOption,
    AnalyzeRequest,
    AnalyzeResponse,
    CompareStrategiesStep,
    ComparisonSummary,
    Coverage,
    FeasibilityQuery,
    MarketQuery,
    MarketQueryResult,
    OptionAnalysis,
    QueryMarketStep,
    RunFeasibilityStep,
    Step,
    SuggestAlternativesStep,
    SuggestedFigure,
    SuggestionInfo,
    SuggestionResult,
    ValidateConstraintsStep,
    ValidatedConstraints,
)
from app.services.business_kind import is_food_business
from app.services.clock import Clock
from app.services.compare_strategies import (
    StrategyComparisonError,
    compare_strategies,
    feasibility_for,
)
from app.services.market_data import MarketDataset
from app.services.scoring import rupees
from app.services.strategy_models import (
    Caveat,
    ConstraintProfile,
    MinutesPerUnit,
    Opportunity,
    OptionScore,
    RankedStrategies,
    StrategyOption,
    SuggestedMinutes,
    SuggestedMoney,
    SuggestionTemplate,
)

# India has no daylight saving, so a fixed offset is exact and needs no tz database.
IST = timezone(timedelta(hours=5, minutes=30))

_MESSAGES = {
    "unknown_opportunity": "An option links to market evidence that is not in the dataset.",
    "inconsistent_scenario": "The options are inconsistent with each other.",
}


# Fewer than this many alternatives from the owner leaves room for suggestions.
MAX_USER_ALTERNATIVES_FOR_HELP = 2
MAX_SUGGESTIONS = 2

_FIGURE_LABELS = {
    "price": "price",
    "variable_cost": "variable cost",
    "startup_cost": "startup cost",
    "minutes_per_unit": "time per item",
}


def _tag(basis: str) -> Literal["from_source", "assumption"]:
    return "from_source" if basis == "from_source" else "assumption"


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _suggestion_info(entry: Opportunity, template: SuggestionTemplate) -> SuggestionInfo:
    figures: list[tuple[str, SuggestedMoney | SuggestedMinutes]] = [
        ("price", template.price),
        ("variable_cost", template.variable_cost),
        ("startup_cost", template.startup_cost),
        ("minutes_per_unit", template.minutes_per_unit),
    ]
    return SuggestionInfo(
        evidence_id=entry.id,
        source_name=entry.source_name,
        figures=[
            SuggestedFigure(
                field=name,
                label=_FIGURE_LABELS[name],
                value=str(figure.value),
                basis=figure.basis,
                quote=figure.quote,
            )
            for name, figure in figures
        ],
    )


def _retag_inputs(result: FeasibilityResult, template: SuggestionTemplate) -> FeasibilityResult:
    """The engine tags the figures it is given as the owner's. A suggestion's inputs are the
    template's, so each is tagged by where it really came from. The owner's own figures (budget,
    units, days) stay as they were, and derived figures stay derived from the inputs."""
    price, cost = _tag(template.price.basis), _tag(template.variable_cost.basis)
    startup = _tag(template.startup_cost.basis)
    data = result.model_dump()
    data["inputs"]["price"]["source"] = price
    data["inputs"]["variable_cost_per_unit"]["source"] = cost
    data["inputs"]["fixed_startup_costs"]["source"] = startup
    data["unit_variable_cost"]["source"] = cost
    data["startup_cost"]["source"] = startup
    data["budget_check"]["startup_cost"]["source"] = startup
    return FeasibilityResult.model_validate(data)


class ScenarioError(Exception):
    """The scenario can't be analysed. Fixed text only: it never echoes what was submitted."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        self.message = _MESSAGES[code]
        super().__init__(self.message)


class AnalyzeService:
    def __init__(self, dataset: MarketDataset, clock: Clock) -> None:
        self._dataset = dataset
        self._clock = clock

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        profile = request.profile
        options = list(request.options)
        self._check_links_exist(options)
        covered = self._dataset.covers(profile.location, request.category)

        templates: dict[str, Opportunity] = {}  # suggested option id -> the entry it came from
        if covered:
            suggested = self._suggestions(request)
            for option in suggested:
                entry = self._dataset.get(option.opportunity_id or "")
                if entry is not None:
                    templates[option.id] = entry
            analysed: list[StrategyOption] = [*options, *suggested]
            skipped: list[str] = []
            pool = list(self._dataset.opportunities)
        else:
            # No evidence for this place or business: judge the original on its own numbers. Any
            # market link on it is dropped, and alternatives are not compared.
            original = next(o for o in options if o.is_original)
            analysed = [original.model_copy(update={"opportunity_id": None})]
            skipped = [o.id for o in options if not o.is_original]
            pool = []

        today = self._clock.now().astimezone(IST).date()
        try:
            ranking = compare_strategies(profile, list(analysed), pool, today)
        except StrategyComparisonError:
            raise ScenarioError("inconsistent_scenario", "options") from None

        scores = {s.option_id: s for s in ranking.ranked}
        analyses = [self._analysis(profile, o, scores[o.id], templates.get(o.id)) for o in analysed]
        # One caveat line per suggestion, whether or not it is the recommendation: the owner sees
        # every suggestion in the table, so each says its figures are partly assumed.
        notes = [self._suggestion_caveat(a) for a in analyses if a.suggestion is not None]
        if notes:
            ranking = ranking.model_copy(update={"caveats": [*ranking.caveats, *notes]})
        linked = self._linked_evidence(analysed)
        coverage: Coverage = "covered" if covered else "none"
        return AnalyzeResponse(
            analyzed_on=today,
            market_coverage=coverage,
            market_message=self._message(request, covered, linked, len(analysed) < len(options)),
            profile=profile,
            category=request.category,
            food_business=is_food_business(
                " ".join([request.category, *(o.title for o in request.options)])
            ),
            options=analyses,
            skipped_option_ids=skipped,
            ranking=ranking,
            evidence=linked,
            steps=self._steps(request, coverage, linked, analyses, ranking),
        )

    # -- suggested alternatives --

    @staticmethod
    def _title_key(title: str) -> str:
        return " ".join(title.casefold().split())

    def _suggestions(self, request: AnalyzeRequest) -> list[StrategyOption]:
        """Up to two alternatives from matching templates, when the owner gave fewer than two.

        A template whose title matches one of the owner's own options is skipped. Each suggestion
        links to its dataset entry, so it gets that entry's market signal, and the same engine
        scores it by the same rules as any other option.
        """
        if not request.suggest_alternatives:
            return []
        if sum(1 for o in request.options if not o.is_original) >= MAX_USER_ALTERNATIVES_FOR_HELP:
            return []
        taken = {self._title_key(o.title) for o in request.options}
        found: list[StrategyOption] = []
        for entry in self._dataset.suggestion_candidates(
            request.profile.location, request.category
        ):
            template = entry.suggestion
            if template is None or self._title_key(template.title) in taken:
                continue
            taken.add(self._title_key(template.title))
            found.append(self._option_from(entry, template))
            if len(found) == MAX_SUGGESTIONS:
                break
        return found

    @staticmethod
    def _option_from(entry: Opportunity, template: SuggestionTemplate) -> StrategyOption:
        minutes = template.minutes_per_unit
        return StrategyOption(
            id=f"suggested-{entry.id.lower()}",
            title=template.title,
            is_original=False,
            is_suggested=True,
            price=template.price.value,
            variable_cost_per_unit=template.variable_cost.value,
            fixed_startup_costs=template.startup_cost.value,
            minutes_per_unit=MinutesPerUnit(value=minutes.value, source=_tag(minutes.basis)),
            opportunity_id=entry.id,
        )

    def _analysis(
        self,
        profile: ConstraintProfile,
        option: StrategyOption,
        score: OptionScore,
        entry: Opportunity | None,
    ) -> OptionAnalysis:
        feasibility = feasibility_for(profile, option)
        suggestion = None
        if option.is_suggested and entry is not None and entry.suggestion is not None:
            feasibility = _retag_inputs(feasibility, entry.suggestion)
            suggestion = _suggestion_info(entry, entry.suggestion)
        return OptionAnalysis(
            option_id=option.id,
            title=option.title,
            is_original=option.is_original,
            opportunity_id=option.opportunity_id,
            feasibility=feasibility,
            score=score,
            is_suggested=option.is_suggested,
            suggestion=suggestion,
        )

    @staticmethod
    def _suggestion_caveat(analysis: OptionAnalysis) -> Caveat:
        info = analysis.suggestion
        assert info is not None  # noqa: S101 - only called for suggested options
        given = [f.label for f in info.figures if f.basis == "from_source"]
        assumed = [f.label for f in info.figures if f.basis == "assumption"]
        message = f"{analysis.title} is a suggestion from LaunchWise, not your idea."
        if given and assumed:
            message += (
                f" Its {_join(given)} {'comes' if len(given) == 1 else 'come'} from "
                f"{info.source_name}; its {_join(assumed)} {'is' if len(assumed) == 1 else 'are'} "
                "assumed."
            )
        elif assumed:
            message += f" Its {_join(assumed)} {'is' if len(assumed) == 1 else 'are'} all assumed."
        return Caveat(kind="suggestion", message=message, items=[analysis.option_id])

    # -- validation against the dataset --

    def _check_links_exist(self, options: list[AnalyzeOption]) -> None:
        for index, option in enumerate(options):
            link = option.opportunity_id
            if link is not None and self._dataset.get(link) is None:
                raise ScenarioError("unknown_opportunity", f"options.{index}.opportunity_id")

    def _linked_evidence(self, analysed: list[StrategyOption]) -> list[Opportunity]:
        wanted = {o.opportunity_id for o in analysed if o.opportunity_id is not None}
        return [o for o in self._dataset.opportunities if o.id in wanted]

    # -- plain-language message and step log --

    @staticmethod
    def _message(
        request: AnalyzeRequest, covered: bool, linked: list[Opportunity], dropped: bool
    ) -> str:
        where = f"{request.profile.location} / {request.category}"
        if not covered:
            return (
                f"LaunchWise has no market evidence for {where}, so this is a feasibility-only "
                "analysis: the numbers come from your inputs and the engine's stated assumptions, "
                "no other options were compared, and nothing here says anything about demand "
                "in your market."
                + (" Market links in your options were ignored." if dropped else "")
            )
        message = f"Market evidence comes from the LaunchWise dataset for {where}."
        if not linked:
            return (
                message
                + " None of your options link to a dataset entry, so market signals are neutral."
            )  # noqa: E501
        unverified = sum(1 for o in linked if o.verification_status != "verified")
        if unverified:
            message += (
                f" {unverified} of {len(linked)} linked entries are unverified, "
                "so treat their market signal with caution."
            )
        return message

    def _steps(
        self,
        request: AnalyzeRequest,
        coverage: Coverage,
        linked: list[Opportunity],
        analyses: list[OptionAnalysis],
        ranking: RankedStrategies,
    ) -> list[Step]:
        profile = request.profile
        where = f"{profile.location} / {request.category}"
        titles = {a.option_id: a.title for a in analyses}
        steps: list[Step] = []

        def add(step: Step) -> None:
            steps.append(step)

        add(
            ValidateConstraintsStep(
                index=1,
                title=(
                    f"Checked constraints: budget {rupees(profile.budget)}, "
                    f"{profile.units_per_day} units/day x {profile.days_per_week} days/week, "
                    f"{len(request.options)} option(s)"
                ),
                result=ValidatedConstraints(
                    profile=profile, category=request.category, option_count=len(request.options)
                ),
            )
        )
        market_title = (
            f"Market evidence for {where}: {len(linked)} linked dataset entr"
            f"{'y' if len(linked) == 1 else 'ies'}"
            if coverage == "covered"
            else f"No market evidence for {where}: feasibility only"
        )
        add(
            QueryMarketStep(
                index=2,
                title=market_title,
                input=MarketQuery(location=profile.location, category=request.category),
                result=MarketQueryResult(
                    coverage=coverage,
                    dataset_entries=len(self._dataset.opportunities),
                    linked_ids=[o.id for o in linked],
                ),
            )
        )
        added = [a for a in analyses if a.is_suggested]
        if added:
            add(
                SuggestAlternativesStep(
                    index=len(steps) + 1,
                    title=(
                        f"Suggested {len(added)} alternative{'' if len(added) == 1 else 's'} from "
                        f"LaunchWise market data: {', '.join(a.title for a in added)}"
                    ),
                    result=SuggestionResult(suggested_ids=[a.option_id for a in added]),
                )
            )
        for analysis in analyses:
            feas = analysis.feasibility
            fits = "within budget" if feas.budget_check.within_budget else "over budget"
            add(
                RunFeasibilityStep(
                    index=len(steps) + 1,
                    title=(
                        f"Feasibility for {analysis.title}: margin "
                        f"{rupees(feas.contribution_margin.value)} per unit, {fits}"
                    ),
                    input=FeasibilityQuery(option_id=analysis.option_id),
                    result=feas,
                )
            )
        recommended_id = ranking.recommended_id
        verdict = (
            f"recommended: {titles[recommended_id]}" if recommended_id else "no option is viable"
        )
        add(
            CompareStrategiesStep(
                index=len(steps) + 1,
                title=f"Ranked {len(ranking.ranked)} option(s); {verdict}",
                result=ComparisonSummary(
                    ranked_ids=[s.option_id for s in ranking.ranked],
                    viable_ids=[s.option_id for s in ranking.ranked if s.viable],
                    recommended_id=recommended_id,
                    keep_original=ranking.keep_original,
                ),
            )
        )
        return steps
