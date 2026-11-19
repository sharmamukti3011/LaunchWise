"""The seeded example page: what a starter page looks like, made from the pivot scenario.

It is built from the guided demo's recommendation (never typed in by hand), under a made-up
business name that says so. It never expires and has no unpublish token. It keeps the banner and
noindex like every other page.
"""

import logging

from app.engine.approval_payload import hash_model
from app.schemas.starter import StarterPageRequest, to_config
from app.schemas.storefront import StorefrontConfig
from app.services.analyze_models import AnalyzeResponse
from app.services.analyze_service import AnalyzeService
from app.services.demo_catalog import DemoCatalog
from app.services.page_store import EXAMPLE_SLUG, PageStore

logger = logging.getLogger("launchwise.storefront")

PIVOT_SCENARIO = "pune-pivot"
EXAMPLE_BRAND = "Example Cake Studio (not a real business)"
EXAMPLE_DESCRIPTION = (
    "A made-up example business, shown to illustrate what a LaunchWise starter page looks like. "
    "The offer and price come from the guided demo."
)


class ExampleSeedError(Exception):
    """The example page cannot be built. Stops startup, like a bad dataset does."""


def build_example_config(analysis: AnalyzeResponse) -> StorefrontConfig:
    recommended = next(
        (o for o in analysis.options if o.option_id == analysis.ranking.recommended_id), None
    )
    if recommended is None:
        raise ExampleSeedError("the pivot scenario has no recommendation")
    request = StarterPageRequest(
        business_name=EXAMPLE_BRAND,
        description=EXAMPLE_DESCRIPTION,
        offer_title=recommended.title,
        offer_price=recommended.feasibility.inputs.price.value,
        food_business=True,
    )
    return to_config(request)


def seed_example_page(store: PageStore, catalog: DemoCatalog, analyzer: AnalyzeService) -> None:
    """Create the example page at startup if it is missing. Safe to run on every start."""
    scenario = catalog.request(PIVOT_SCENARIO)
    if scenario is None:
        raise ExampleSeedError("the pivot scenario is missing from the demo catalog")
    config = build_example_config(analyzer.analyze(scenario))
    created = store.seed_example(config, hash_model(config))
    logger.info("storefront outcome=%s", "example_seeded" if created else "example_present")


__all__ = ["EXAMPLE_SLUG", "seed_example_page", "build_example_config", "ExampleSeedError"]
