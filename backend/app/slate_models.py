"""Additive tables: existing installations need no destructive schema migration."""
from datetime import datetime
from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class ScheduledGame(Base):
    __tablename__ = 'scheduled_games'
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    season_type: Mapped[str] = mapped_column(String(16))
    week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_team: Mapped[str] = mapped_column(String(64))
    away_team: Mapped[str] = mapped_column(String(64))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24))
    source: Mapped[str] = mapped_column(String(32))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    context: Mapped[dict] = mapped_column(JSON, default=dict)


class RosterMembership(Base):
    __tablename__ = 'roster_memberships'
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    player_id: Mapped[str] = mapped_column(String(128), index=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    week: Mapped[int] = mapped_column(Integer)
    team: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QuoteBatch(Base):
    __tablename__ = 'quote_batches'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    game_id: Mapped[str] = mapped_column(String(128), index=True)
    event_id: Mapped[str] = mapped_column(String(128))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)


class ForecastSnapshot(Base):
    __tablename__ = 'forecast_snapshots'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    game_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)
