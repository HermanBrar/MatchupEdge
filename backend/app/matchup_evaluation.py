"""Reproducible chronological validation and same-player opponent sensitivity."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import json
from sqlalchemy import select
from .slate_models import ScheduledGame, RosterMembership
from .slates import model_for, select_games, weekly_board
from .matchup_model import METRICS


def evaluate_matchups(session, output='data/reports/matchup_evaluation.json'):
    now = datetime.now(timezone.utc)
    games = list(session.scalars(select(ScheduledGame).where(ScheduledGame.sport == 'NFL')))
    model = model_for(session, games, now)
    report = {'model': 'matchup-ridge-empirical-v2', 'generated_at': now.isoformat(), 'metrics': {}}
    for market, metric in METRICS.items():
        fitted = model.fit(metric)
        if fitted:
            report['metrics'][market] = fitted[2]
    upcoming, selection = select_games(games, now=now)
    report['selection'] = selection
    player = session.scalar(select(RosterMembership).where(RosterMembership.player_id == 'NFL:nflverse:00-0035640', RosterMembership.season == selection['season']).order_by(RosterMembership.week.desc()))
    actual = next((g for g in upcoming if player and player.team in (g.home_team,g.away_team)), None)
    if actual:
        original = model.forecast(player.player_id, player.team, player.position, actual, 'Receiving yards')
        alternate = SimpleNamespace(**{k:v for k,v in vars(actual).items() if not k.startswith('_')})
        if player.team == alternate.home_team:
            alternate.away_team = 'BUF' if alternate.away_team != 'BUF' else 'NYJ'
        else:
            alternate.home_team = 'BUF' if alternate.home_team != 'BUF' else 'NYJ'
        changed = model.forecast(player.player_id, player.team, player.position, alternate, 'Receiving yards')
        for forecast in (original, changed):
            forecast.pop('_samples', None)
        report['opponent_sensitivity'] = {'player_id': player.player_id, 'player': player.name, 'market': 'Receiving yards',
             'actual_matchup': f'{actual.away_team}@{actual.home_team}', 'counterfactual_matchup': f'{alternate.away_team}@{alternate.home_team}',
             'note': 'Counterfactual only: same player, cutoff, home/away and rest; change opponent identity.',
             'actual': original, 'counterfactual': changed}
    board = weekly_board(session, now=now)
    identities = [(p['player_id'],p['game_id']) for p in board['players']]
    report['weekly_checks'] = {'games':len(board['games']), 'players':len(board['players']), 'unique_player_games':len(set(identities)),
         'duplicate_player_games':len(identities)-len(set(identities)), 'quotes':sum(len(m['quotes']) for p in board['players'] for m in p['markets']),
         'aj_brown':[p for p in board['players'] if p['player_id']=='NFL:nflverse:00-0035676']}
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report,indent=2))
    return {'report':str(target), 'metrics':report['metrics'], 'checks':{k:v for k,v in report['weekly_checks'].items() if k != 'aj_brown'},
            'opponent_example':{k:report.get('opponent_sensitivity',{}).get(k) for k in ('player','actual_matchup','counterfactual_matchup')}}
