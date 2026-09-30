import pandas as pd

from app.coverage import CoverageSummary
from app.providers.nflverse import NFLVerseProvider


def test_nflverse_capabilities_are_explicit():
    capabilities = {item.capability: item.status for item in NFLVerseProvider().capabilities()}
    assert capabilities["schedules"] == "supported"
    assert capabilities["odds"] == "unavailable"


def test_coverage_summary_never_claims_market_coverage_without_quotes():
    summary = CoverageSummary(10, 7, 4, 0, ("missing line",))
    assert summary.as_dict()["players_with_market"] == 0
    assert summary.as_dict()["failures"] == ["missing line"]
