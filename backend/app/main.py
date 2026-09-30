from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal
import uuid

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .slate_models import ScheduledGame, ForecastSnapshot
from .slates import weekly_board, select_games, refresh_quotes
from .providers.base import ProviderError
from .db import Base, engine, get_db
from .demo import seed_demo
from .models import Game, Projection
from .providers import NBAApiProvider, NFLVerseProvider, OddsApiProvider
from .real_models import ProviderRun, RealProjection
from .schemas import CapabilityResponse, CoverageResponse, GameResponse, OddsInput, OddsResponse, ParlayRequest, ParlayResponse, ProjectionResponse, RealProjectionResponse, StatusResponse
from .services.odds import american_to_decimal, decimal_to_implied_probability, evaluate_parlay


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    if get_settings().app_mode == "demo":
        with next(get_db()) as session:
            seed_demo(session)
    yield


app = FastAPI(title="MatchupEdge API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in settings.api_cors_origins.split(",")], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "matchupedge-api"}


@app.get("/api/v1/status", response_model=StatusResponse)
def status() -> StatusResponse:
    mode = settings.app_mode if settings.app_mode in {"demo", "historical", "live"} else "demo"
    live_configured = bool(settings.odds_api_key)
    note = "Demo records are deterministic synthetic fixtures; no live feed is configured." if mode == "demo" else "Real provider data only. Missing feeds remain unavailable and never fall back to Demo."
    return StatusResponse(mode=mode, label=f"{mode.title()} Data", live_configured=live_configured, note=note)


@app.get("/api/v1/demo")
def demo_data(sport: str = 'NFL'):
    from .demo import GAMES, PROJECTIONS
    return {'status': {'mode': 'demo', 'label': 'Demo Data', 'live_configured': False,
                       'note': 'Deterministic synthetic fixtures, including demo lines and probabilities.'},
            'games': [{**g, 'data_mode': 'demo'} for g in GAMES if g['sport'] == sport],
            'projections': [{**p, 'data_mode': 'demo'} for p in PROJECTIONS if p['sport'] == sport]}


@app.get("/api/v1/games", response_model=list[GameResponse])
def games(sport: str | None = Query(default=None), season: int | None = None, season_type: str | None = None,
          week: int | None = None, date: str | None = None, view: str = 'upcoming', session: Session = Depends(get_db)):
    if settings.app_mode != 'demo':
        selected, _ = select_games(list(session.scalars(select(ScheduledGame))), sport=(sport or 'NFL').upper(), season=season, season_type=season_type, week=week, date=date, view=view)
        return [{'id': g.id, 'sport': g.sport, 'home_team': g.home_team, 'away_team': g.away_team,
                 'starts_at': g.starts_at, 'data_mode': 'historical' if g.status == 'completed' else 'live'} for g in selected if g.starts_at]
    statement = select(Game).order_by(Game.starts_at)
    if settings.app_mode != "demo":
        statement = statement.where(Game.data_mode != "demo")
    if sport:
        statement = statement.where(Game.sport == sport.upper())
    return list(session.scalars(statement))


@app.get("/api/v1/projections", response_model=list[ProjectionResponse])
def projections(sport: str | None = Query(default=None), session: Session = Depends(get_db)) -> list[Projection]:
    statement = select(Projection).order_by(Projection.sport, Projection.player)
    if sport:
        statement = statement.where(Projection.sport == sport.upper())
    return list(session.scalars(statement))


@app.get("/api/v1/real/projections")
def real_projections(sport: str = "NFL", season: int | None = None, season_type: str | None = None, week: int | None = None, session: Session = Depends(get_db)):
    board = weekly_board(session, sport=sport.upper(), season=season, season_type=season_type, week=week)
    return [{**m['forecast'], 'id': f"{p['game_id']}:{p['player_id']}:{m['market']}",
             'game_id': p['game_id'], 'player_id': p['player_id'], 'player': p['player'], 'team': p['team'],
             'sport': sport.upper(), 'market': m['market'], 'line': None, 'over_probability': None,
             'under_probability': None, 'source': 'nflverse', 'data_quality': 'matchup_model'}
            for p in board['players'] for m in p['markets'] if m['forecast']['available']]


@app.get("/api/v1/slate")
def slate(sport: Literal['NFL', 'NBA'] = 'NFL', season: int | None = None,
          season_type: Literal['REG', 'PRE', 'POST'] | None = None,
          week: int | None = Query(None, ge=1, le=25), date: str | None = None,
          view: Literal['upcoming', 'completed', 'history', 'all'] = 'upcoming',
          sportsbook: str | None = None, session: Session = Depends(get_db)):
    return weekly_board(session, sport, season, season_type, week, date, view, sportsbook)


@app.post("/api/v1/data/refresh")
def refresh_data(sport: Literal['NFL', 'NBA'] = 'NFL', session: Session = Depends(get_db)):
    from .real_ingestion import ingest_nfl
    from .nba_ingestion import ingest_nba
    try:
        return ingest_nfl(session) if sport == 'NFL' else ingest_nba(session)
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.post("/api/v1/slate/quotes/refresh")
def refresh_slate_quotes(sport: Literal['NFL', 'NBA'] = 'NFL', season: int | None = None,
                         season_type: Literal['REG', 'PRE', 'POST'] | None = None,
                         week: int | None = Query(None, ge=1, le=25), date: str | None = None,
                         session: Session = Depends(get_db)):
    games, _ = select_games(list(session.scalars(select(ScheduledGame))), sport, season, season_type, week, date)
    try:
        return refresh_quotes(session, games, sport)
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.post("/api/v1/slate/snapshot")
def save_slate_snapshot(sport: Literal['NFL', 'NBA'] = 'NFL', season: int | None = None,
                        season_type: Literal['REG', 'PRE', 'POST'] | None = None,
                        week: int | None = None, date: str | None = None, session: Session = Depends(get_db)):
    board = weekly_board(session, sport, season, season_type, week, date)
    now = datetime.now(timezone.utc)
    saved = 0
    for game in board['games']:
        if not game['starts_at'] or datetime.fromisoformat(game['starts_at']) <= now:
            continue
        saved += 1
        payload = {'game': game, 'created_at': now.isoformat(), 'players': [p for p in board['players'] if p['game_id'] == game['id']]}
        session.add(ForecastSnapshot(id=uuid.uuid4().hex, game_id=game['id'], created_at=now, payload=payload))
    session.commit()
    return {'saved_games': saved}


@app.get("/api/v1/providers", response_model=list[CapabilityResponse])
def providers() -> list[CapabilityResponse]:
    capabilities = NFLVerseProvider().capabilities() + NBAApiProvider().capabilities() + OddsApiProvider().capabilities()
    return [CapabilityResponse(**capability.__dict__) for capability in capabilities]


@app.get("/api/v1/coverage", response_model=CoverageResponse | None)
def coverage(session: Session = Depends(get_db)) -> CoverageResponse | None:
    run = session.scalar(select(ProviderRun).order_by(ProviderRun.started_at.desc()))
    if run is None:
        return None
    return CoverageResponse(provider=run.provider, sport=run.sport, status=run.status, records=run.records, coverage=run.coverage_json or {}, message=run.message)


@app.post("/api/v1/odds", response_model=OddsResponse)
def odds(payload: OddsInput) -> OddsResponse:
    if payload.decimal_odds is None and payload.american_odds is None:
        raise HTTPException(status_code=422, detail="Provide American or decimal odds")
    decimal = payload.decimal_odds or american_to_decimal(payload.american_odds or 0)
    probability = decimal_to_implied_probability(decimal)
    return OddsResponse(decimal_odds=decimal, implied_probability=probability, break_even_probability=probability, potential_profit=payload.stake * (decimal - 1), stake=payload.stake)


@app.post("/api/v1/parlays/evaluate", response_model=ParlayResponse)
def parlay(payload: ParlayRequest) -> ParlayResponse:
    result = evaluate_parlay([leg.model_dump() for leg in payload.legs], payload.stake, payload.quoted_decimal_odds)
    return ParlayResponse(**result.__dict__)
