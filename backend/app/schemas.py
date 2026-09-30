from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class StatusResponse(BaseModel):
    mode: Literal["demo", "historical", "live"]
    label: str
    live_configured: bool
    note: str


class GameResponse(BaseModel):
    id: str
    sport: str
    home_team: str
    away_team: str
    starts_at: datetime
    data_mode: str

    model_config = {"from_attributes": True}


class ProjectionResponse(BaseModel):
    id: str
    game_id: str
    sport: str
    player: str
    team: str
    market: str
    line: float
    projected: float
    over_probability: float = Field(ge=0, le=1)
    under_probability: float = Field(ge=0, le=1)
    data_mode: str
    generated_at: datetime

    model_config = {"from_attributes": True}


class RealProjectionResponse(BaseModel):
    id: str
    game_id: str
    sport: str
    player_id: str
    player: str
    team: str
    market: str
    projected: float
    predictive_lower: float
    predictive_upper: float
    line: float | None
    over_probability: float | None
    under_probability: float | None
    sample_size: int
    model_version: str
    feature_cutoff: datetime
    source: str
    data_quality: str

    model_config = {"from_attributes": True}


class CoverageResponse(BaseModel):
    provider: str
    sport: str
    status: str
    records: int
    coverage: dict
    message: str | None


class CapabilityResponse(BaseModel):
    provider: str
    sport: str
    capability: str
    status: str
    detail: str
    requires_key: bool


class OddsInput(BaseModel):
    american_odds: int | None = None
    decimal_odds: float | None = Field(default=None, gt=1)
    stake: float = Field(default=10, gt=0)


class OddsResponse(BaseModel):
    decimal_odds: float
    implied_probability: float
    break_even_probability: float
    potential_profit: float
    stake: float


class ParlayLeg(BaseModel):
    id: str
    game_id: str
    label: str
    probability: float = Field(ge=0, le=1)
    decimal_odds: float = Field(gt=1)


class ParlayRequest(BaseModel):
    legs: list[ParlayLeg] = Field(min_length=2, max_length=4)
    quoted_decimal_odds: float | None = Field(default=None, gt=1)
    stake: float = Field(default=10, gt=0)


class ParlayResponse(BaseModel):
    valid: bool
    message: str
    joint_probability: float | None = None
    decimal_odds: float | None = None
    potential_profit: float | None = None
    expected_return: float | None = None
    correlation_status: str
