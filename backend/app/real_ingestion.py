from __future__ import annotations
import math
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
from sqlalchemy.orm import Session
from .models import Game
from .providers.base import ProviderError
from .providers.nflverse import NFLVerseProvider
from .providers.nba import NBAApiProvider
from .real_models import ProviderRun, RealPlayer, RealPlayerGameStat
from .slate_models import ScheduledGame, RosterMembership

NFL_MARKETS = {
    'QB': {'Passing yards': 'passing_yards', 'Rushing yards': 'rushing_yards'},
    'RB': {'Rushing yards': 'rushing_yards', 'Receiving yards': 'receiving_yards', 'Receptions': 'receptions'},
    'WR': {'Receiving yards': 'receiving_yards', 'Receptions': 'receptions'},
    'TE': {'Receiving yards': 'receiving_yards', 'Receptions': 'receptions'},
}


def ingest_nfl(session: Session, cache_dir='data/cache/nflverse', seasons=None):
    provider = NFLVerseProvider(cache_dir=cache_dir)
    now = datetime.now(timezone.utc)
    current_season = now.year if now.month >= 3 else now.year - 1
    seasons = seasons or [current_season - 2, current_season - 1, current_season]
    run = ProviderRun(id=f'nflverse-{uuid.uuid4().hex}', provider=provider.name, sport='NFL', started_at=now, status='running')
    session.add(run)
    session.commit()
    run_id = run.id
    try:
        schedules = provider.load_schedules()
        # Load every requested season, preserving each game's season and historic team.
        _upsert_games(session, schedules[schedules.season.isin(set(seasons) | {current_season})], retrieved_at=datetime.fromtimestamp((Path(cache_dir) / 'schedules/games.csv').stat().st_mtime, timezone.utc))
        roster = provider.load_roster(current_season)
        _upsert_players(session, roster[roster.season.eq(current_season)], retrieved_at=datetime.fromtimestamp((Path(cache_dir) / f'rosters/roster_{current_season}.csv').stat().st_mtime, timezone.utc))
        frames, missing = [], []
        for season in seasons:
            try:
                frame = provider.load_player_stats(season)
                frame['_source_retrieved_at'] = datetime.fromtimestamp((Path(cache_dir) / f'stats_player/stats_player_week_{season}.csv').stat().st_mtime, timezone.utc).isoformat()
                frames.append(frame)
            except ProviderError as exc:
                missing.append(str(exc))
        count = _upsert_stats(session, pd.concat(frames, ignore_index=True), schedules) if frames else 0
        run.status = 'completed' if not missing else 'partial'
        run.completed_at = datetime.now(timezone.utc)
        run.records = count
        run.coverage_json = {'missing': missing, 'roster_season': current_season, 'model': 'on-demand pregame matchup model'}
        run.message = f'Loaded {count} historical player/game rows. Forecasts are scoped to the selected slate.'
        session.commit()
        return {'status': run.status, 'records': count, 'coverage': run.coverage_json}
    except Exception as exc:
        session.rollback()
        failed = session.get(ProviderRun, run_id)
        failed.status, failed.message = 'failed', str(exc)
        failed.completed_at = datetime.now(timezone.utc)
        session.commit()
        raise ProviderError(f'NFL ingestion failed: {exc}') from exc


def _upsert_games(session, schedules, season=None, retrieved_at=None):
    if season is not None:
        schedules = schedules[schedules.season.eq(season)]
    now = retrieved_at or datetime.now(timezone.utc)
    for row in schedules.itertuples(index=False):
        starts = _parse_game_time(row.gameday, row.gametime)
        completed = pd.notna(row.home_score) and pd.notna(row.away_score)
        status = 'completed' if completed else 'scheduled' if starts else 'postponed'
        game_id = f'nflverse:{row.game_id}'
        # Final scores, closing lines and observed weather MUST NOT be pregame features.
        context = {key: _number_or_none(getattr(row, key, None)) for key in ['home_rest', 'away_rest', 'roof']}
        session.merge(ScheduledGame(id=game_id, sport='NFL', season=int(row.season), season_type=('POST' if str(row.game_type) in ('WC', 'DIV', 'CON', 'SB') else str(row.game_type)), week=int(row.week), home_team=str(row.home_team), away_team=str(row.away_team), starts_at=starts, status=status, source='nflverse', retrieved_at=now, context=context))
        if starts:
            session.merge(Game(id=game_id, sport='NFL', home_team=str(row.home_team), away_team=str(row.away_team), starts_at=starts, data_mode='historical' if completed else 'live'))
    session.flush()


def _upsert_players(session, roster, retrieved_at=None):
    now = retrieved_at or datetime.now(timezone.utc)
    roster = roster.dropna(subset=['gsis_id', 'full_name', 'team']).copy()
    # Conflicting identities/teams at the same effective week are quarantined.
    keys = ['gsis_id', 'season', 'week']
    conflicts = roster.groupby(keys).team.transform('nunique') > 1
    roster = roster[~conflicts].drop_duplicates(keys)
    for row in roster.itertuples(index=False):
        player_id = f'NFL:nflverse:{row.gsis_id}'
        session.merge(RosterMembership(id=f'{player_id}:{row.season}:{row.week}', player_id=player_id, season=int(row.season), week=int(row.week), team=str(row.team), name=str(row.full_name), position=str(row.position), status=str(row.status), retrieved_at=now))
    for row in roster.sort_values(['season', 'week']).drop_duplicates('gsis_id', keep='last').itertuples(index=False):
        session.merge(RealPlayer(id=f'NFL:nflverse:{row.gsis_id}', sport='NFL', provider='nflverse', provider_id=str(row.gsis_id), name=str(row.full_name), team=str(row.team), position=str(row.position), status=str(row.status), updated_at=now))
    session.flush()
    return len(roster)


def _upsert_stats(session, stats, schedules):
    schedule_map = schedules.set_index('game_id').to_dict('index')
    count = 0
    # A stable player/game key prevents team joins from multiplying records.
    if stats.duplicated(['player_id', 'game_id']).any():
        raise ProviderError('Duplicate player/game statistics; refusing ambiguous import')
    for record in stats.to_dict('records'):
        game = schedule_map.get(record.get('game_id'))
        if not game or pd.isna(record.get('player_id')):
            continue
        if int(record['season']) != int(game['season']) or record['team'] not in (game['home_team'], game['away_team']):
            raise ProviderError('Statistics season/team does not match provider game ID')
        if str(record.get('season_type')) != ('POST' if str(game['game_type']) in ('WC', 'DIV', 'CON', 'SB') else str(game['game_type'])) or int(record['week']) != int(game['week']):
            raise ProviderError('Statistics week/type does not match provider game ID')
        kickoff = _parse_game_time(game['gameday'], game['gametime'])
        if kickoff is None or pd.isna(game['home_score']):
            continue
        player_id, game_id = record['player_id'], record['game_id']
        # Preserve all opportunity/efficiency columns, including original game team.
        values = {key: _number_or_none(value) for key, value in record.items() if key not in ('player_id', 'game_id', 'headshot_url', '_source_retrieved_at')}
        # Keep the legacy key format so re-ingestion upgrades records in place.
        session.merge(RealPlayerGameStat(id=f'nflverse:{game_id}:{player_id}:{record["team"]}', player_id=f'NFL:nflverse:{player_id}', game_id=f'nflverse:{game_id}', sport='NFL', game_date=kickoff, values=values, source='nflverse', retrieved_at=datetime.fromisoformat(record['_source_retrieved_at']) if record.get('_source_retrieved_at') else datetime.now(timezone.utc)))
        count += 1
    session.flush()
    return count


def _parse_game_time(gameday, gametime):
    if pd.isna(gameday) or pd.isna(gametime) or not gametime:
        return None
    # nflverse gametime is US Eastern, including daylight saving time.
    return datetime.combine(pd.Timestamp(gameday).date(), pd.Timestamp(str(gametime)).time(), tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)


def _number_or_none(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return str(value)


def ingest_nba_roster(session):
    provider = NBAApiProvider()
    players = provider.load_players(current_only=True)
    for record in players:
        session.merge(RealPlayer(id=f'NBA:nba_api:{record["id"]}', sport='NBA', provider=provider.name, provider_id=str(record['id']), name=record['full_name'], team=None, position=None, status='active', updated_at=datetime.now(timezone.utc)))
    session.commit()
    return {'players': len(players), 'team_assignment': 'unavailable from static endpoint'}
