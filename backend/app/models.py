from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Game(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    home_team: Mapped[str] = mapped_column(String(64))
    away_team: Mapped[str] = mapped_column(String(64))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_mode: Mapped[str] = mapped_column(String(16), default="demo")


class Projection(Base):
    __tablename__ = "projections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    game_id: Mapped[str] = mapped_column(String(64), index=True)
    sport: Mapped[str] = mapped_column(String(8), index=True)
    player: Mapped[str] = mapped_column(String(100))
    team: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(64))
    line: Mapped[float] = mapped_column(Float)
    projected: Mapped[float] = mapped_column(Float)
    over_probability: Mapped[float] = mapped_column(Float)
    under_probability: Mapped[float] = mapped_column(Float)
    data_mode: Mapped[str] = mapped_column(String(16), default="demo")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
