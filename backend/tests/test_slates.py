from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db import Base
from app.slates import select_games, match_event, parse_quotes, roster_for_games, weekly_board
from app.slate_models import ScheduledGame, RosterMembership
from app.matchup_model import MatchupModel, quote_probabilities
from app.real_ingestion import _parse_game_time, _upsert_stats, _upsert_players
from app.providers.base import ProviderError

NOW = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)


def game(id='g', week=4, **kwargs):
    values = dict(id=id, sport='NFL', season=2026, season_type='REG', week=week,
                  home_team='NE', away_team='BUF', starts_at=NOW + timedelta(days=2),
                  status='scheduled', source='test', retrieved_at=NOW, context={'home_rest': 7, 'away_rest': 7})
    values.update(kwargs)
    return NS(**values)


@pytest.fixture
def session():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_default_week_current_season_and_no_completed_games():
    rows = [game('done', status='completed'), game('next'), game('later', week=5, starts_at=NOW+timedelta(days=9)), game('old', season=2025), game('post', season_type='POST', week=4), game('tbd', starts_at=None, status='postponed')]
    chosen, selection = select_games(rows, now=NOW)
    assert [g.id for g in chosen] == ['next']
    assert selection['season'] == 2026 and selection['week'] == 4
    completed, _ = select_games(rows, week=4, view='completed', now=NOW)
    assert [g.id for g in completed] == ['done']
    all_games, _ = select_games(rows, week=4, view='all', now=NOW)
    assert 'tbd' in [g.id for g in all_games]
    assert select_games(rows, season=2027, now=NOW)[0] == []


def test_nba_date_uses_eastern_calendar():
    g = game(sport='NBA', starts_at=datetime(2026,10,2,1,tzinfo=timezone.utc), week=None)
    assert select_games([g], sport='NBA', date='2026-10-01', now=NOW)[0] == [g]
    assert select_games([g], sport='NBA', date='2026-10-02', now=NOW)[0] == []


def test_nfl_kickoff_is_eastern_with_dst():
    assert _parse_game_time('2026-10-01', '20:15').isoformat() == '2026-10-02T00:15:00+00:00'
    assert _parse_game_time('2026-12-01', '20:15').hour == 1
    assert _parse_game_time('2026-10-01', None) is None


def test_aj_brown_stable_id_only_own_game_and_season(session):
    pid = 'NFL:nflverse:00-0035676'
    for season, week, team in [(2025, 18, 'PHI'), (2026, 3, 'NE')]:
        session.add(RosterMembership(id=f'{pid}:{season}', player_id=pid, season=season, week=week, team=team, name='A.J. Brown', position='WR', status='ACT', retrieved_at=NOW))
    session.flush()
    own, other = game('own'), game('other', home_team='PHI', away_team='DAL')
    roster = roster_for_games(session, [own, other])
    assert [p.player_id for p in roster['own']] == [pid]
    assert roster['other'] == []
    assert roster_for_games(session, [game('past', season=2025, week=17, home_team='PHI')])['past'] == []


def test_ambiguous_roster_teams_not_overwritten(session):
    roster = pd.DataFrame([dict(gsis_id='p', season=2026, week=4, full_name='Same Player', team=t, position='WR', status='ACT') for t in ['NE','BUF']])
    assert _upsert_players(session, roster) == 0
    assert list(session.scalars(select(RosterMembership))) == []


def payload():
    return {'id': 'odds-event', 'home_team': 'New England Patriots', 'away_team': 'Buffalo Bills', 'commence_time': (NOW+timedelta(days=2)).isoformat(), 'bookmakers': [{'key': 'book', 'title': 'Book', 'markets': [{'key': 'player_reception_yds', 'last_update': NOW.isoformat(), 'outcomes': [
        {'name': 'Over', 'description': 'A.J. Brown', 'point': 51.5, 'price': -110},
        {'name': 'Under', 'description': 'A.J. Brown', 'point': 51.5, 'price': -105},
        {'name': 'Over', 'description': 'A.J. Brown', 'point': 52.5, 'price': 100},
    ]}]}]}


def test_event_and_quote_identity_includes_line_period_and_game():
    g = game()
    p = payload()
    assert match_event(p, [g], 'NFL') == g
    assert match_event(p, [game(starts_at=NOW+timedelta(days=9))], 'NFL') is None
    assert match_event(p, [g, game('duplicate')], 'NFL') is None
    roster = [NS(name='A.J. Brown', player_id='NFL:nflverse:00-0035676')]
    quotes, _ = parse_quotes(p, g, roster, NOW)
    assert len(quotes) == 2
    assert quotes[0]['odds'] == {'over': -110, 'under': -105}
    assert quotes[1]['odds'] == {'over': 100}
    assert all(q['game_id'] == g.id and q['period'] == 'full_game' for q in quotes)
    assert parse_quotes(p, g, roster + [NS(name='AJ Brown', player_id='other-person')], NOW)[0] == []


def test_future_and_same_game_stats_never_features():
    games = [game('old', starts_at=NOW-timedelta(days=7), status='completed'), game('future', starts_at=NOW+timedelta(days=1), status='completed')]
    rows = [NS(game_id=g.id, player_id='p', values={'team':'NE', 'position':'WR', 'receiving_yards':value, 'targets':5, 'receptions':3}) for g, value in zip(games,[40,9999])]
    model = MatchupModel(rows, games, NOW)
    assert len(model.player_history['p']) == 1
    assert model.player_history['p'][0]['receiving_yards'] == 40
    same = MatchupModel(rows, games, games[0].starts_at)
    assert same.player_history['p'] == []


def test_opponent_changes_inputs_and_can_change_fitted_forecast():
    model = MatchupModel([], [], NOW)
    model.player_history['p'] = [{'receiving_yards':60,'targets':8,'receptions':5,'target_share':.25}] * 8
    model.position_history['WR'] = model.player_history['p']
    model.defense_history['BUF'] = [{'passing_yards':300,'attempts':30,'sacks_suffered':1,'pass_expected_yards':210}] * 8
    model.defense_history['NYJ'] = [{'passing_yards':120,'attempts':30,'sacks_suffered':5,'pass_expected_yards':210}] * 8
    a, _ = model.features('p','NE','WR',game(), 'receiving_yards')
    b, _ = model.features('p','NE','WR',game(away_team='NYJ'), 'receiving_yards')
    assert a[6] > b[6] and a[7] < b[7]
    # Train historical effects from outcomes; no hard-coded opponent yardage bonus.
    for i in range(250):
        x = list(a if i % 2 else b)
        x[0] += i % 5
        model.examples['receiving_yards'].append((NOW-timedelta(days=300-i), x, 40+25*x[6]+i%3))
    fa = model.forecast('p','NE','WR',game(), 'Receiving yards')
    fb = model.forecast('p','NE','WR',game(away_team='NYJ'), 'Receiving yards')
    assert fa['available'] and fb['available']
    assert fa['projected'] > fb['projected']
    assert fa['validation']['train_before'] < fa['validation']['test_from']


def test_discrete_predictive_probabilities_include_push_and_half_lines():
    forecast = {'_samples': np.array([50,51,51,52])}
    assert quote_probabilities(forecast, 51) == {'over': .25, 'under': .25, 'push': .5}
    assert quote_probabilities(forecast, 51.5) == {'over': .25, 'under': .75, 'push': 0}


def test_duplicate_stats_rejected_before_join(session):
    with pytest.raises(ProviderError, match='Duplicate'):
        _upsert_stats(session, pd.DataFrame([{'player_id':'p','game_id':'g'}]*2), pd.DataFrame([{'game_id':'g'}]))


def test_historical_view_does_not_rebuild_using_current_roster(session):
    g = game(status='completed')
    session.add(ScheduledGame(**vars(g)))
    session.flush()
    board = weekly_board(session, season=2026, week=4, view='completed', now=NOW)
    assert len(board['games']) == 1
    assert board['players'] == [] and board['snapshots'] == []


def test_touchdown_rules_exclude_passes_defense_and_include_returns():
    from app.market_rules import touchdown_target, scorer_rules
    values = dict(passing_tds=4, rushing_tds=0, receiving_tds=0, special_teams_tds=0, fumble_recovery_tds=0, def_tds=1)
    assert touchdown_target(values) == 0
    assert touchdown_target({**values, 'special_teams_tds':1}) == 1
    assert touchdown_target({**values, 'rushing_tds':1}) == 1
    assert touchdown_target({**values, 'fumble_recovery_tds':1}) is None
    assert touchdown_target({**values, 'fumble_recovery_tds':1, 'def_tds':0}) == 1
    assert scorer_rules('fanduel') is not None and scorer_rules('unknown') is None


def test_bad_quote_timestamps_and_non_full_game_markets_are_rejected():
    p = payload()
    roster = [NS(name='A.J. Brown', player_id='p')]
    p['bookmakers'][0]['markets'][0]['last_update'] = 'not-a-date'
    assert parse_quotes(p, game(), roster, NOW)[0] == []
    p['bookmakers'][0]['markets'][0]['last_update'] = NOW.isoformat()
    p['bookmakers'][0]['markets'][0]['key'] = 'player_reception_yds_h1'
    assert parse_quotes(p, game(), roster, NOW)[0] == []


def test_nba_opponent_inputs_use_possessions_and_minutes():
    from app.matchup_model import NBAMatchupModel
    model = NBAMatchupModel([], [], NOW)
    model.player_history['p'] = [{'points':25,'minutes':32,'fga':18,'fta':4}] * 5
    model.position_history['NBA'] = model.player_history['p']
    model.defense_history['BUF'] = [{'points':130,'points_expected':110}] * 8
    model.defense_history['NYJ'] = [{'points':90,'points_expected':110}] * 8
    a, n = model.features('p','NE','NBA',game(), 'points')
    b, _ = model.features('p','NE','NBA',game(away_team='NYJ'), 'points')
    assert a[1] == 32 and n == 5 and a[6] > b[6]


def test_provider_uses_event_endpoint_and_redacts_network_errors(monkeypatch):
    from app.providers.odds_api import OddsApiProvider
    import app.providers.odds_api as module
    provider = OddsApiProvider(api_key='test-private-value')
    calls = []
    monkeypatch.setattr(provider, '_get', lambda path, **params: calls.append((path,params)) or ({},{}))
    provider.load_event_odds('NFL','event-id')
    assert calls[0][0] == 'sports/americanfootball_nfl/events/event-id/odds'
    assert 'player_reception_yds' in calls[0][1]['markets']
    provider = OddsApiProvider(api_key='test-private-value')
    def fail(*args, **kwargs):
        raise RuntimeError('URL with test-private-value')
    monkeypatch.setattr(module, 'urlopen', fail)
    with pytest.raises(ProviderError) as exc:
        provider.load_events('NFL')
    assert 'test-private-value' not in str(exc.value)


def test_newest_empty_quote_batch_replaces_prior_quotes(session):
    from app.slate_models import QuoteBatch
    session.add(QuoteBatch(id='older',game_id='g',event_id='e',retrieved_at=NOW-timedelta(minutes=10),payload={'quotes':[{'market':'Receiving yards'}]}))
    session.add(QuoteBatch(id='newer',game_id='g',event_id='e',retrieved_at=NOW,payload={'quotes':[]}))
    session.flush()
    latest=session.scalar(select(QuoteBatch).where(QuoteBatch.game_id=='g').order_by(QuoteBatch.retrieved_at.desc()))
    assert latest.payload['quotes'] == []


def test_schedule_source_freshness_uses_retrieval_time(session):
    from app.real_ingestion import _upsert_games
    retrieved = NOW-timedelta(hours=2)
    frame=pd.DataFrame([dict(game_id='2026_04_NE_BUF',season=2026,game_type='REG',week=4,home_team='BUF',away_team='NE',home_score=None,away_score=None,gameday='2026-10-04',gametime='13:00')])
    _upsert_games(session,frame,retrieved_at=retrieved)
    stored=session.get(ScheduledGame,'nflverse:2026_04_NE_BUF')
    assert stored.retrieved_at.replace(tzinfo=timezone.utc) == retrieved
