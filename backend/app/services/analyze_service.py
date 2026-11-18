"""Analyze a business scenario deterministically: engine numbers, ranking, caveats, step log.

No Claude, no database, no network. Market evidence comes only from the loaded dataset. When the
dataset has no coverage for the place or business, the analysis is feasibility-only: the original
option's numbers and caveats, a neutral market signal, no alternatives compared, no invented
evidence.
"""

from datetime import timedelta, timezone

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
    ValidateConstraintsStep,
    ValidatedConstraints,
)
from app.services.clock import Clock
from app.services.compare_strategies import (
    StrategyComparisonError,
    compare_strategies,
    feasibility_for,
)
from app.services.market_data import MarketDataset
from app.services.scoring import rupees
from app.services.strategy_models import Opportunity, RankedStrategies

# India has no daylight saving, so a fixed offset is exact and needs no tz database.
IST = timezone(timedelta(hours=5, minutes=30))

_MESSAGES = {
    "unknown_opportunity": "An option links to market evidence that is not in the dataset.",
    "alternative_needs_evidence": "Each alternative must link to a market evidence entry from the dataset.",  # noqa: E501
    "inconsistent_scenario": "The options are inconsistent with each other.",
}


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

        if covered:
            self._check_alternatives_have_evidence(options)
            analysed: list[AnalyzeOption] = options
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
        analyses = [
            OptionAnalysis(
                option_id=o.id,
                title=o.title,
                is_original=o.is_original,
                opportunity_id=o.opportunity_id,
                feasibility=feasibility_for(profile, o),
                score=scores[o.id],
            )
            for o in analysed
        ]
        linked = self._linked_evidence(analysed)
        coverage: Coverage = "covered" if covered else "none"
        return AnalyzeResponse(
            analyzed_on=today,
            market_coverage=coverage,
            market_message=self._message(request, covered, linked, len(analysed) < len(options)),
            profile=profile,
            category=request.category,
            options=analyses,
            skipped_option_ids=skipped,
            ranking=ranking,
            evidence=linked,
            steps=self._steps(request, coverage, linked, analyses, ranking),
        )

    # -- validation against the dataset --

    def _check_links_exist(self, options: list[AnalyzeOption]) -> None:
        for index, option in enumerate(options):
            link = option.opportunity_id
            if link is not None and self._dataset.get(link) is None:
                raise ScenarioError("unknown_opportunity", f"options.{index}.opportunity_id")

    @staticmethod
    def _check_alternatives_have_evidence(options: list[AnalyzeOption]) -> None:
        for index, option in enumerate(options):
            if not option.is_original and option.opportunity_id is None:
                raise ScenarioError("alternative_needs_evidence", f"options.{index}.opportunity_id")

    def _linked_evidence(self, analysed: list[AnalyzeOption]) -> list[Opportunity]:
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
