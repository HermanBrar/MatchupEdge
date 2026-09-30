from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .models import Game, Projection


GAMES = [
    {"id": "demo-nfl-001", "sport": "NFL", "home_team": "Colts", "away_team": "Broncos", "starts_at": datetime(2026, 10, 4, 17, tzinfo=timezone.utc)},
    {"id": "demo-nba-001", "sport": "NBA", "home_team": "Pacers", "away_team": "Bulls", "starts_at": datetime(2026, 10, 5, 23, tzinfo=timezone.utc)},
]

PROJECTIONS = [
    {"id": "demo-proj-001", "game_id": "demo-nfl-001", "sport": "NFL", "player": "Jonathan Taylor", "team": "Colts", "market": "Rushing yards", "line": 78.5, "projected": 86.0, "over_probability": 0.57, "under_probability": 0.43},
    {"id": "demo-proj-002", "game_id": "demo-nfl-001", "sport": "NFL", "player": "Bo Nix", "team": "Broncos", "market": "Passing yards", "line": 231.5, "projected": 226.0, "over_probability": 0.46, "under_probability": 0.54},
    {"id": "demo-proj-003", "game_id": "demo-nba-001", "sport": "NBA", "player": "Tyrese Haliburton", "team": "Pacers", "market": "Assists", "line": 9.5, "projected": 10.4, "over_probability": 0.59, "under_probability": 0.41},
    {"id": "demo-proj-004", "game_id": "demo-nba-001", "sport": "NBA", "player": "Zach LaVine", "team": "Bulls", "market": "Points", "line": 24.5, "projected": 23.1, "over_probability": 0.44, "under_probability": 0.56},
]


def seed_demo(session: Session) -> None:
    if session.query(Game).count() > 0:
        return
    session.add_all([Game(**game, data_mode="demo") for game in GAMES])
    session.add_all([Projection(**projection, data_mode="demo", generated_at=datetime.now(timezone.utc)) for projection in PROJECTIONS])
    session.commit()
