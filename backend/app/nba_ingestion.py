"""NBA schedule, season roster and game logs. Failures remain explicit."""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import ssl
from urllib.request import urlopen
import certifi
import pandas as pd
from sqlalchemy.orm import Session
from .providers.base import ProviderError
from .real_models import RealPlayer, RealPlayerGameStat
from .slate_models import ScheduledGame, RosterMembership


def ingest_nba(session: Session, seasons=None):
    from nba_api.stats.endpoints import commonallplayers, leaguegamelog
    from nba_api.stats.static import teams
    now = datetime.now(timezone.utc)
    year = now.year if now.month >= 7 else now.year - 1
    seasons = seasons or [year-2, year-1]
    team_map = {str(t['id']): t['abbreviation'] for t in teams.get_teams()}
    report = {'sport': 'NBA', 'games': 0, 'players': 0, 'stats': 0, 'errors': []}
    try:
        with urlopen('https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json', timeout=25, context=ssl.create_default_context(cafile=certifi.where())) as response:
            payload = json.loads(response.read())
        for day in payload['leagueSchedule']['gameDates']:
            for game in day['games']:
                starts = datetime.fromisoformat(game['gameDateTimeUTC'].replace('Z', '+00:00'))
                home, away = game['homeTeam']['teamTricode'], game['awayTeam']['teamTricode']
                if not home or not away:
                    continue
                label = game.get('gameLabel', '')
                status = 'completed' if game['gameStatus'] == 3 else 'scheduled' if game['gameStatus'] == 1 else 'in_progress'
                if 'postpon' in game.get('gameStatusText','').lower():
                    status = 'postponed'
                session.merge(ScheduledGame(id=f'nba:{game["gameId"]}', sport='NBA', season=int(payload['leagueSchedule']['seasonYear'][:4]), season_type='PRE' if 'preseason' in label.lower() else 'REG', week=None, home_team=home, away_team=away, starts_at=starts, status=status, source='nba.com', retrieved_at=now, context={}))
                report['games'] += 1
        session.commit()
    except Exception as exc:
        session.rollback()
        report['errors'].append(f'NBA schedule unavailable: {type(exc).__name__}')
    try:
        roster = commonallplayers.CommonAllPlayers(is_only_current_season=1, season=f'{year}-{str(year+1)[-2:]}', timeout=20).get_data_frames()[0]
        for record in roster.to_dict('records'):
            team = team_map.get(str(record['TEAM_ID']))
            if not team:
                continue
            pid = f'NBA:nba_api:{record["PERSON_ID"]}'
            name = record['DISPLAY_FIRST_LAST']
            session.merge(RealPlayer(id=pid, sport='NBA', provider='nba_api', provider_id=str(record['PERSON_ID']), name=name, team=team, position='NBA', status='active', updated_at=now))
            session.merge(RosterMembership(id=f'{pid}:{year}:0', player_id=pid, season=year, week=0, team=team, name=name, position='NBA', status='active', retrieved_at=now))
            report['players'] += 1
        session.commit()
    except Exception as exc:
        session.rollback()
        report['errors'].append(f'NBA season roster unavailable: {type(exc).__name__}')
    for season in seasons:
        season_count = 0
        try:
            cache = Path(f'data/cache/nba/game_logs_{season}.json')
            if cache.exists() and season < year:
                records = json.loads(cache.read_text())
            else:
                frame = leaguegamelog.LeagueGameLog(player_or_team_abbreviation='P', season=f'{season}-{str(season+1)[-2:]}', season_type_all_star='Regular Season', timeout=25).get_data_frames()[0]
                records = json.loads(frame.to_json(orient='records'))
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(records))
            for r in records:
                gid, pid = f'nba:{r["GAME_ID"]}', f'NBA:nba_api:{r["PLAYER_ID"]}'
                matchup = r['MATCHUP'].split()
                home = r['TEAM_ABBREVIATION'] if matchup[1] == 'vs.' else matchup[-1]
                away = matchup[-1] if matchup[1] == 'vs.' else r['TEAM_ABBREVIATION']
                # Logs have dates only. Use end-of-day plus model lag for availability;
                # never pretend these imprecise timestamps are exact kickoffs.
                dt = datetime.combine(pd.Timestamp(r['GAME_DATE']).date(), datetime.max.time(), tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)
                existing = session.get(ScheduledGame, gid)
                if existing is None:
                    session.add(ScheduledGame(id=gid, sport='NBA', season=season, season_type='REG', week=None, home_team=home, away_team=away, starts_at=dt, status='completed', source='nba_api', retrieved_at=now, context={'time_precision':'date_only'}))
                    session.flush()
                values = {'team':r['TEAM_ABBREVIATION'], 'position':'NBA', 'season':season, 'points':r['PTS'], 'assists':r['AST'], 'rebounds':r['REB'], 'threes':r['FG3M'], 'minutes':r['MIN'], 'fga':r['FGA'], 'fta':r['FTA'], 'oreb':r['OREB'], 'tov':r['TOV']}
                session.merge(RealPlayerGameStat(id=f'{gid}:{pid}', player_id=pid, game_id=gid, sport='NBA', game_date=dt, values=values, source='nba_api', retrieved_at=datetime.fromtimestamp(cache.stat().st_mtime, timezone.utc)))
                season_count += 1
            session.commit()
            report['stats'] += season_count
        except Exception as exc:
            session.rollback()
            report['errors'].append(f'NBA {season} game logs unavailable: {type(exc).__name__}')
    if not report['games']:
        try:
            from .providers.odds_api import OddsApiProvider
            from .slates import nba_teams
            events, _ = OddsApiProvider().load_events('NBA')
            aliases = nba_teams()
            for event in events:
                starts = datetime.fromisoformat(event['commence_time'].replace('Z', '+00:00'))
                home, away = aliases.get(event['home_team']), aliases.get(event['away_team'])
                if home and away:
                    session.merge(ScheduledGame(id=f'odds:{event["id"]}', sport='NBA', season=starts.year if starts.month >= 7 else starts.year-1, season_type='REG', week=None, home_team=home, away_team=away, starts_at=starts, status='scheduled', source='the_odds_api', retrieved_at=now, context={}))
                    report['games'] += 1
            session.commit()
        except Exception as exc:
            session.rollback()
            report['errors'].append(f'NBA event schedule unavailable: {type(exc).__name__}')
    return report
