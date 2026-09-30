from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import re
import uuid
from threading import RLock
from sqlalchemy import select
from .market_rules import scorer_rules
from .config import get_settings, ENV_FILE
from .slate_models import ScheduledGame, RosterMembership, QuoteBatch, ForecastSnapshot
from .real_models import RealPlayerGameStat, RealPlayer
from .providers.odds_api import OddsApiProvider, MARKETS
from .providers.base import ProviderError
from .matchup_model import MatchupModel, NBAMatchupModel, utc, quote_probabilities
from .services.odds import american_to_decimal

# Provider team names mapped explicitly; never fuzzy-match teams or people.
NFL_TEAMS = dict(zip(
    ['Arizona Cardinals','Atlanta Falcons','Baltimore Ravens','Buffalo Bills','Carolina Panthers','Chicago Bears','Cincinnati Bengals','Cleveland Browns','Dallas Cowboys','Denver Broncos','Detroit Lions','Green Bay Packers','Houston Texans','Indianapolis Colts','Jacksonville Jaguars','Kansas City Chiefs','Las Vegas Raiders','Los Angeles Chargers','Los Angeles Rams','Miami Dolphins','Minnesota Vikings','New England Patriots','New Orleans Saints','New York Giants','New York Jets','Philadelphia Eagles','Pittsburgh Steelers','San Francisco 49ers','Seattle Seahawks','Tampa Bay Buccaneers','Tennessee Titans','Washington Commanders'],
    ['ARI','ATL','BAL','BUF','CAR','CHI','CIN','CLE','DAL','DEN','DET','GB','HOU','IND','JAX','KC','LV','LAC','LA','MIA','MIN','NE','NO','NYG','NYJ','PHI','PIT','SF','SEA','TB','TEN','WAS']))
MODEL_CACHE = {}
MODEL_LOCK = RLock()


def current_season(now):
    return now.year if now.month >= 3 else now.year - 1


def game_json(game):
    return {'id': game.id, 'sport': game.sport, 'season': game.season, 'season_type': game.season_type,
            'week': game.week, 'home_team': game.home_team, 'away_team': game.away_team,
            'starts_at': utc(game.starts_at).isoformat() if game.starts_at else None, 'status': game.status,
            'source': game.source, 'retrieved_at': utc(game.retrieved_at).isoformat()}


def select_games(games, sport='NFL', season=None, season_type=None, week=None, date=None, view='upcoming', now=None):
    now = utc(now or datetime.now(timezone.utc))
    season = season if season is not None else current_season(now)
    candidates = [g for g in games if g.sport == sport and (sport != 'NFL' or g.season == season)]
    future = sorted([g for g in candidates if g.status == 'scheduled' and g.starts_at and utc(g.starts_at) > now], key=lambda g: utc(g.starts_at))
    if sport == 'NFL':
        season_type = season_type or (future[0].season_type if future else 'REG')
        future = [g for g in future if g.season_type == season_type]
        if week is None:
            week = future[0].week if future else (max((g.week for g in candidates if g.season_type == season_type and g.status == 'completed'), default=None) if view != 'upcoming' else None)
        selected = [g for g in candidates if g.season_type == season_type and g.week == week]
    else:
        date = date or (utc(future[0].starts_at).astimezone(ZoneInfo('America/New_York')).date().isoformat() if future else now.astimezone(ZoneInfo('America/New_York')).date().isoformat())
        selected = [g for g in candidates if g.starts_at and utc(g.starts_at).astimezone(ZoneInfo('America/New_York')).date().isoformat() == date]
    if view == 'upcoming':
        selected = [g for g in selected if g.status == 'scheduled' and g.starts_at and utc(g.starts_at) > now]
    elif view == 'completed':
        selected = [g for g in selected if g.status == 'completed']
    return sorted(selected, key=lambda g: utc(g.starts_at) if g.starts_at else datetime.max.replace(tzinfo=timezone.utc)), {'sport': sport, 'season': season, 'season_type': season_type, 'week': week, 'date': date, 'view': view}


def roster_for_games(session, games):
    groups = {}
    for game in games:
        rows = list(session.scalars(select(RosterMembership).where(RosterMembership.season == game.season, RosterMembership.week <= (game.week or 999))))
        latest = {}
        for row in rows:
            if row.player_id.startswith(game.sport + ':') and (row.player_id not in latest or row.week > latest[row.player_id].week):
                latest[row.player_id] = row
        groups[game.id] = [p for p in latest.values() if p.team in (game.home_team, game.away_team)]
    return groups


def match_event(event, games, sport):
    teams = NFL_TEAMS if sport == 'NFL' else nba_teams()
    home, away = teams.get(event.get('home_team')), teams.get(event.get('away_team'))
    try:
        starts = datetime.fromisoformat(event['commence_time'].replace('Z', '+00:00'))
    except (KeyError, ValueError):
        return None
    matches = [g for g in games if g.home_team == home and g.away_team == away and g.starts_at and abs((utc(g.starts_at) - starts).total_seconds()) <= 300]
    return matches[0] if len(matches) == 1 else None


def nba_teams():
    from nba_api.stats.static import teams
    return {t['full_name']: t['abbreviation'] for t in teams.get_teams()}


def normalized_name(name):
    return re.sub(r'[^a-z0-9]', '', name.lower())


def parse_quotes(payload, game, roster, retrieved_at):
    names = {}
    for player in roster:
        names.setdefault(normalized_name(player.name), set()).add(player.player_id)
    quotes, rejected = {}, 0
    for book in payload.get('bookmakers', []):
        for market in book.get('markets', []):
            key = market.get('key')
            if key not in MARKETS[game.sport]:
                continue
            timestamp = market.get('last_update')
            try:
                quote_time = utc(datetime.fromisoformat(timestamp.replace('Z', '+00:00')))
                valid_time = quote_time <= retrieved_at and game.starts_at and quote_time < utc(game.starts_at)
            except (ValueError, AttributeError):
                valid_time = False
            if not valid_time:
                rejected += len(market.get('outcomes', []))
                continue
            for outcome in market.get('outcomes', []):
                ids = names.get(normalized_name(outcome.get('description', '')), set())
                side = outcome.get('name')
                if len(ids) != 1 or side not in ('Over', 'Under', 'Yes', 'No'):
                    rejected += 1
                    continue
                td = key == 'player_anytime_td'
                line = None if td else outcome.get('point')
                if not td and not isinstance(line, (int, float)):
                    rejected += 1
                    continue
                if not isinstance(outcome.get('price'), (int, float)) or abs(outcome['price']) < 100:
                    rejected += 1
                    continue
                player_id = next(iter(ids))
                identity = (player_id, key, 'full_game', line, book['key'])
                entry = quotes.setdefault(identity, {'event_id': payload['id'], 'game_id': game.id, 'player_id': player_id,
                    'commence_time': payload.get('commence_time'), 'market': MARKETS[game.sport][key], 'market_key': key, 'period': 'full_game', 'line': line,
                    'sportsbook': book['title'], 'sportsbook_key': book['key'], 'quote_timestamp': timestamp,
                    'retrieved_at': retrieved_at.isoformat(), 'odds': {},
                    'identity_method': 'unique normalized name within season/week roster, resolved to stable provider ID',
                    'rules': 'Non-passing touchdown scorer; bookmaker settlement rules unverified' if td else 'Full-game statistic; verify bookmaker participation/void rules',
                    'rules_verified': False})
                normalized_side = ('yes' if side == 'Over' else 'no') if td and side in ('Over', 'Under') else side.lower()
                # Conflicting duplicate sides are quarantined rather than overwritten.
                if normalized_side in entry['odds'] and entry['odds'][normalized_side] != outcome['price']:
                    entry['conflict'] = True
                entry['odds'][normalized_side] = outcome['price']
    return [q for q in quotes.values() if not q.get('conflict')], rejected


def refresh_quotes(session, games, sport, now=None):
    now = utc(now or datetime.now(timezone.utc))
    provider = OddsApiProvider()
    events, quota = provider.load_events(sport)
    rosters = roster_for_games(session, games)
    count, rejected, matched, cached = 0, 0, 0, 0
    for event in events:
        game = match_event(event, games, sport)
        if not game or game.status != 'scheduled' or utc(game.starts_at) <= now:
            continue
        matched += 1
        latest = session.scalar(select(QuoteBatch).where(QuoteBatch.game_id == game.id).order_by(QuoteBatch.retrieved_at.desc()))
        if latest and now - utc(latest.retrieved_at) < timedelta(minutes=5):
            cached += 1
            continue
        payload, quota = provider.load_event_odds(sport, event['id'])
        if payload.get('id') != event['id'] or match_event(payload, [game], sport) is None:
            raise ProviderError('Event odds identity/kickoff does not match schedule; no quotes attached')
        quotes, missing = parse_quotes(payload, game, rosters[game.id], now)
        session.add(QuoteBatch(id=uuid.uuid4().hex, game_id=game.id, event_id=event['id'], retrieved_at=now, payload={'quotes': quotes, 'rejected': missing, 'quota': quota, 'commence_time': payload['commence_time']}))
        session.commit()
        count += len(quotes)
        rejected += missing
    return {'quotes': count, 'unresolved_outcomes': rejected, 'matched_events': matched, 'cached_events': cached, 'quota': quota}


def model_for(session, all_games, now, sport='NFL'):
    rows = list(session.scalars(select(RealPlayerGameStat).where(RealPlayerGameStat.sport == sport)))
    revision = max((utc(r.retrieved_at).isoformat() for r in rows), default='empty')
    # Exact source revision and hourly cutoff invalidate cache after refresh or kickoff.
    cutoff = now.replace(minute=0, second=0, microsecond=0)
    schedule_revision = max((utc(g.retrieved_at).isoformat() for g in all_games), default='empty')
    key = (sport, revision, len(rows), schedule_revision, cutoff.isoformat())
    with MODEL_LOCK:
        if key not in MODEL_CACHE:
            if len(MODEL_CACHE) >= 4:
                MODEL_CACHE.pop(next(iter(MODEL_CACHE)))
            model = (MatchupModel if sport == 'NFL' else NBAMatchupModel)(rows, all_games, cutoff)
            for metric in model.examples:
                model.fit(metric)
            MODEL_CACHE[key] = model
        return MODEL_CACHE[key]


def weekly_board(session, sport='NFL', season=None, season_type=None, week=None, date=None, view='upcoming', sportsbook=None, now=None):
    now = utc(now or datetime.now(timezone.utc))
    all_games = list(session.scalars(select(ScheduledGame).where(ScheduledGame.sport == sport)))
    games, selection = select_games(all_games, sport, season, season_type, week, date, view, now)
    memberships = roster_for_games(session, games)
    result = {'selection': selection, 'games': [game_json(g) for g in games], 'players': [],
              'seasons': sorted({g.season for g in all_games} | {current_season(now)}, reverse=True),
              'slates': sorted({(g.season, g.season_type, g.week or 0) for g in all_games}),
              'sportsbooks': [], 'excluded_players': [], 'messages': [], 'as_of': now.isoformat(),
              'mode': 'historical' if view in ('completed', 'history') else 'live'}
    if not games:
        result['messages'].append('No games for this selection. A bye, unpublished schedule or completed slate produces no upcoming player rows.')
    if not get_settings().odds_api_key:
        result['messages'].append(f'Set ODDS_API_KEY in {ENV_FILE} and restart the backend. Never send keys through chat.')
    if view in ('completed', 'history', 'all'):
        snapshots = list(session.scalars(select(ForecastSnapshot).where(ForecastSnapshot.game_id.in_([g.id for g in games])).order_by(ForecastSnapshot.created_at.desc()))) if games else []
        result['snapshots'] = [s.payload for s in snapshots]
        result['messages'].append('Historical view shows saved pregame predictions only; no forecast is rebuilt using current rosters or future statistics.')
        return result
    if sport == 'NBA':
        result['messages'].append('NBA models use season-specific game logs and verified roster assignments where loaded; missing coverage remains unavailable.')
    model = model_for(session, all_games, now, sport) if games else None
    books = set()
    for game in games:
        batch = session.scalar(select(QuoteBatch).where(QuoteBatch.game_id == game.id).order_by(QuoteBatch.retrieved_at.desc()))
        quotes = batch.payload['quotes'] if batch else []
        if batch and batch.payload.get('commence_time') and abs((utc(datetime.fromisoformat(batch.payload['commence_time'].replace('Z', '+00:00'))) - utc(game.starts_at)).total_seconds()) > 300:
            quotes = []
            result['messages'].append(f'{game.id}: stored quotes were for a different kickoff; refresh after rescheduling.')
        books.update((q['sportsbook_key'], q['sportsbook']) for q in quotes)
        for player in sorted(memberships[game.id], key=lambda p: (p.name, p.player_id)):
            if player.position not in ('QB', 'RB', 'WR', 'TE', 'NBA'):
                continue
            item = {'player_id': player.player_id, 'player': player.name, 'team': player.team, 'game_id': game.id,
                    'opponent': game.away_team if player.team == game.home_team else game.home_team,
                    'roster_status': player.status, 'roster_season': player.season, 'roster_week': player.week,
                    'roster_retrieved_at': utc(player.retrieved_at).isoformat(), 'markets': []}
            for market in MARKETS[sport].values():
                if not model or not model.supported(player.position, market):
                    continue
                forecast = model.forecast(player.player_id, player.team, player.position, game, market) if player.status in ('ACT', 'active') else {'available': False, 'reason': f'Roster status {player.status}; availability unconfirmed. Projection withheld.', 'sample_size': 0}
                matching = [dict(q) for q in quotes if q['player_id'] == player.player_id and q['market'] == market and (not sportsbook or q['sportsbook_key'] == sportsbook)]
                for quote in matching:
                    timestamp = datetime.fromisoformat(quote['quote_timestamp'].replace('Z', '+00:00'))
                    quote['stale'] = now - utc(timestamp) > timedelta(minutes=30) or utc(timestamp) > now or utc(timestamp) >= utc(game.starts_at)
                    probabilities = quote_probabilities(forecast, quote['line']) if forecast['available'] else None
                    quote['probabilities'] = probabilities
                    quote['ev'] = {side: probabilities[side] * (american_to_decimal(odds) - 1) - probabilities['under' if side == 'over' else 'over'] for side, odds in quote['odds'].items() if side in ('over', 'under')} if probabilities and not quote['stale'] else None
                    if market == 'Anytime touchdown':
                        rules = scorer_rules(quote['sportsbook_key'])
                        probability = forecast.get('td_probability')
                        quote['rules'] = rules['description'] if rules else quote['rules']
                        quote['rules_source'] = rules['source'] if rules else None
                        quote['rules_verified'] = bool(rules)
                        quote['probabilities'] = {'yes': probability, 'no': 1-probability, 'push': 0} if rules and probability is not None else None
                        quote['ev'] = {side: (probability if side == 'yes' else 1-probability) * american_to_decimal(odds) - 1 for side, odds in quote['odds'].items() if side in ('yes', 'no')} if rules and probability is not None and not quote['stale'] else None  # Unknown settlement rules remain unavailable.
                forecast.pop('_samples', None)
                item['markets'].append({'market': market, 'forecast': forecast, 'quotes': matching, 'line_status': 'Posted' if matching else 'Line not posted' if batch else 'Quotes not fetched'})
            if any(m['forecast']['available'] for m in item['markets']) or player.status not in ('ACT', 'active'):
                result['players'].append(item)
            else:
                result['excluded_players'].append({'player_id': player.player_id, 'player': player.name, 'reason': 'Insufficient pregame history/calibration'})
    selected_teams = {team for game in games for team in (game.home_team, game.away_team)}
    season_roster = list(session.scalars(select(RosterMembership).where(RosterMembership.season == selection['season'], RosterMembership.week <= (selection['week'] or 999))))
    latest = {}
    for member in season_roster:
        if member.player_id.startswith(sport + ':') and (member.player_id not in latest or member.week > latest[member.player_id].week):
            latest[member.player_id] = member
    for member in latest.values():
        if member.team not in selected_teams and member.position in ('QB', 'RB', 'WR', 'TE', 'NBA'):
            result['excluded_players'].append({'player_id': member.player_id, 'player': member.name, 'reason': 'No upcoming game in this selection (bye, completed game or schedule unavailable)'})
    result['sportsbooks'] = [{'key': key, 'title': title} for key, title in sorted(books)]
    result['messages'].append('Touchdown probabilities use FanDuel Indiana offensive/special-teams scorer rules, including overtime, conditional on participation. Other books remain unpriced until their settlement rules are mapped.')
    return result
