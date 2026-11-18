from typing import cast

from fastapi import APIRouter, Request

from app.services.market_data import EvidenceChoiceList, MarketDataset

router = APIRouter()


@router.get("/market-evidence", response_model=EvidenceChoiceList)
def market_evidence(request: Request) -> EvidenceChoiceList:
    """The dataset entries an alternative can be based on. Read-only and cheap."""
    return cast(MarketDataset, request.app.state.market_dataset).choices()
