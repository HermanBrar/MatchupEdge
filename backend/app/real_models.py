from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class RealPlayer(Base):
    __tablename__ = "real_players"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    team: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    position: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RealPlayerGameStat(Base):
    __tablename__ = "real_player_game_stats"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    player_id: Mapped[str] = mapped_column(String(128), index=True)
    game_id: Mapped[str] = mapped_column(String(128), index=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    game_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    values: Mapped[dict[str, Any]] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RealProjection(Base):
    __tablename__ = "real_projections"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    game_id: Mapped[str] = mapped_column(String(128), index=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    player_id: Mapped[str] = mapped_column(String(128), index=True)
    player: Mapped[str] = mapped_column(String(120), index=True)
    team: Mapped[str] = mapped_column(String(16))
    market: Mapped[str] = mapped_column(String(64))
    projected: Mapped[float] = mapped_column(Float)
    predictive_lower: Mapped[float] = mapped_column(Float)
    predictive_upper: Mapped[float] = mapped_column(Float)
    line: Mapped[float | None] = mapped_column(Float, nullable=True)
    over_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    under_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int] = mapped_column(Integer)
    model_version: Mapped[str] = mapped_column(String(64))
    feature_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(64))
    data_quality: Mapped[str] = mapped_column(String(32))


class ProviderRun(Base):
    __tablename__ = "provider_runs"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24))
    records: Mapped[int] = mapped_column(Integer, default=0)
    coverage_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
