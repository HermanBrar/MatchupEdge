"""Pregame, chronological matchup model with held-out predictive distributions.

Historical source revisions are not point-in-time archives. Replay evaluation is
explicitly retrospective; archived live forecasts retain their actual cutoff.
"""
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import hashlib
import math
import numpy as np
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.isotonic import IsotonicRegression
from .market_rules import touchdown_target, FANDUEL_TD

VERSION = 'matchup-ridge-empirical-v2'
METRICS = {'Passing yards': 'passing_yards', 'Rushing yards': 'rushing_yards',
           'Receiving yards': 'receiving_yards', 'Receptions': 'receptions',
           'Anytime touchdown': 'qualifying_td', 'Points': 'points', 'Assists': 'assists',
           'Rebounds': 'rebounds', 'Made three-pointers': 'threes'}
FEATURES = ['recent_stat', 'recent_opportunities', 'recent_efficiency', 'workload_share',
            'team_volume', 'team_efficiency', 'opponent_efficiency_ratio',
            'opponent_sack_rate', 'home', 'rest_days', 'recent_catches', 'recent_yards']


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def number(values, key):
    value = values.get(key)
    return float(value) if isinstance(value, (float, int)) and math.isfinite(value) else 0.0


def channel(metric):
    return 'rush' if metric == 'rushing_yards' else 'pass'


class MatchupModel:
    def __init__(self, rows, games, cutoff):
        self.cutoff = utc(cutoff)
        self.source_retrieved_at = max((utc(r.retrieved_at).isoformat() for r in rows if hasattr(r, 'retrieved_at')), default=None)
        self.games = {g.id: g for g in games}
        self.player_history = defaultdict(list)
        self.team_history = defaultdict(list)
        self.defense_history = defaultdict(list)
        self.position_history = defaultdict(list)
        self.prior_cache = {}
        self.examples = defaultdict(list)
        self.fits = {}
        grouped = defaultdict(list)
        seen = set()
        for row in rows:
            if row.game_id not in self.games or (row.player_id, row.game_id) in seen:
                continue
            game = self.games[row.game_id]
            # Conservative availability lag; same-game and concurrent outcomes excluded.
            if game.status != 'completed' or not game.starts_at or utc(game.starts_at) + timedelta(hours=8) >= self.cutoff:
                continue
            seen.add((row.player_id, row.game_id))
            values = dict(row.values)
            values['qualifying_td'] = touchdown_target(values)
            grouped[row.game_id].append((row.player_id, values))
        pending = deque()
        for game_id in sorted(grouped, key=lambda key: utc(self.games[key].starts_at)):
            game = self.games[game_id]
            kickoff = utc(game.starts_at)
            while pending and pending[0][0] < kickoff:
                self._observe(*pending.popleft()[1:])
            records = grouped[game_id]
            for player_id, values in records:
                position = values.get('position', values.get('position_group', ''))
                if position not in ('QB', 'RB', 'WR', 'TE', 'NBA'):
                    continue
                team = values['team']
                for market, metric in METRICS.items():
                    if metric not in values or values[metric] is None:
                        continue
                    if not self.supported(position, market):
                        continue
                    features, sample = self.features(player_id, team, position, game, metric)
                    if sample >= 3:
                        self.examples[metric].append((kickoff, features, number(values, metric)))
            pending.append((kickoff + timedelta(hours=8), game, records))
        while pending:
            self._observe(*pending.popleft()[1:])
        self.last_game_at = max((utc(self.games[key].starts_at) for key in grouped), default=None)

    @staticmethod
    def supported(position, market):
        return market == 'Anytime touchdown' or (market == 'Passing yards' and position == 'QB') or (market == 'Rushing yards' and position in ('QB', 'RB')) or (market in ('Receiving yards', 'Receptions') and position in ('RB', 'WR', 'TE'))

    def _observe(self, game, records):
        totals = {}
        for team in (game.home_team, game.away_team):
            own = [v for _, v in records if v['team'] == team]
            totals[team] = {k: sum(number(v, k) for v in own) for k in ('attempts', 'passing_yards', 'sacks_suffered', 'carries', 'rushing_yards', 'targets')}
        # Compare allowed efficiency to what that offense previously produced.
        for team, total in totals.items():
            opponent = game.away_team if team == game.home_team else game.home_team
            prior = self.team_history[team][-8:]
            defense = dict(total)
            for kind, yards, opps in [('pass', 'passing_yards', 'attempts'), ('rush', 'rushing_yards', 'carries')]:
                league_rate = 7.0 if kind == 'pass' else 4.3
                expected = (sum(p[yards] for p in prior) + 100 * league_rate) / (sum(p[opps] for p in prior) + 100)
                defense[kind + '_expected_yards'] = expected * total[opps]
            self.defense_history[opponent].append(defense)
        for team, total in totals.items():
            self.team_history[team].append(total)
        for player_id, values in records:
            self.player_history[player_id].append(values)
            position = values.get('position', values.get('position_group', ''))
            self.position_history[position].append(values)

    def position_prior(self, position, metric):
        history = self.position_history[position]
        key = (position, metric)
        cached = self.prior_cache.get(key)
        if cached is None or cached[0] != len(history):
            recent = history[-500:]
            mean = sum(number(v, metric) for v in recent) / max(1, len(recent))
            self.prior_cache[key] = (len(history), mean)
        return self.prior_cache[key][1]

    def features(self, player_id, team, position, game, metric):
        history = self.player_history[player_id][-8:]
        position_rows = self.position_history[position][-500:]
        # Shrink small samples toward position-specific history, never future rows.
        prior = self.position_prior(position, metric)
        recent = history[-5:]
        baseline = (sum(number(v, metric) for v in recent) + 2 * prior) / (len(recent) + 2)
        opps = 'carries' if channel(metric) == 'rush' else 'attempts' if position == 'QB' else 'targets'
        volume = np.mean([number(v, opps) for v in recent]) if recent else 0.0
        efficiency = sum(number(v, metric) for v in history) / max(1, sum(number(v, opps) for v in history))
        offense = self.team_history[team][-8:]
        kind = channel(metric)
        team_opps = 'carries' if kind == 'rush' else 'attempts'
        team_yards = 'rushing_yards' if kind == 'rush' else 'passing_yards'
        team_volume = np.mean([v[team_opps] for v in offense]) if offense else 0.0
        team_eff = sum(v[team_yards] for v in offense) / max(1, sum(v[team_opps] for v in offense))
        share = np.mean([number(v, 'target_share') for v in recent]) if opps == 'targets' and recent else volume / max(1, team_volume)
        opponent = game.away_team if team == game.home_team else game.home_team
        defense = self.defense_history[opponent][-8:]
        # Opportunity normalization, opponent-offense normalization and 100-opportunity shrinkage.
        prior_yards = 100 * (7.0 if kind == 'pass' else 4.3)
        defense_ratio = (sum(v[team_yards] for v in defense) + prior_yards) / (sum(v[kind + '_expected_yards'] for v in defense) + prior_yards)
        sacks = (sum(v['sacks_suffered'] for v in defense) + 6) / (sum(v['attempts'] + v['sacks_suffered'] for v in defense) + 100)
        home = team == game.home_team
        rest = (game.context or {}).get('home_rest' if home else 'away_rest')
        rest = min(float(rest), 21) if rest is not None else 7
        catches = np.mean([number(v, 'receptions') for v in recent]) if recent else 0.0
        yards = np.mean([number(v, 'receiving_yards') for v in recent]) if recent else 0.0
        return [float(x) for x in [baseline, volume, efficiency, share, team_volume, team_eff, defense_ratio, sacks, int(home), rest, catches, yards]], len(history)

    def fit(self, metric):
        if metric in self.fits:
            return self.fits[metric]
        examples = self.examples[metric]
        if len(examples) < 150:
            self.fits[metric] = None
            return None
        # Split at full kickoff boundaries, not individual players in the same game.
        times = sorted(set(x[0] for x in examples))
        train_end, cal_end = times[int(len(times) * .6)], times[int(len(times) * .8)]
        train = [e for e in examples if e[0] < train_end]
        cal = [e for e in examples if train_end <= e[0] < cal_end]
        test = [e for e in examples if e[0] >= cal_end]
        if min(map(len, (train, cal, test))) < 30:
            self.fits[metric] = None
            return None
        x, y = np.array([e[1] for e in train]), np.array([e[2] for e in train])
        is_td = metric == 'qualifying_td'
        estimator = LogisticRegression(C=.1, max_iter=500) if is_td else Ridge(alpha=100)
        model = make_pipeline(StandardScaler(), estimator)
        model.fit(x, y)
        cx, cy = np.array([e[1] for e in cal]), np.array([e[2] for e in cal])
        tx, ty = np.array([e[1] for e in test]), np.array([e[2] for e in test])
        report = {'train_n': len(train), 'calibration_n': len(cal), 'test_n': len(test),
                  'train_before': train_end.isoformat(), 'test_from': cal_end.isoformat(),
                  'evaluation': 'chronological held-out; retrospective revised stats, not archived as-of data'}
        if is_td:
            calibration = IsotonicRegression(out_of_bounds='clip').fit(model.predict_proba(cx)[:, 1], cy)
            pred = calibration.predict(model.predict_proba(tx)[:, 1])
            report['brier'] = float(np.mean((pred - ty) ** 2))
            report['base_rate_brier'] = float(np.mean((np.mean(y) - ty) ** 2))
            fitted = (model, calibration, report)
        else:
            residuals = cy - model.predict(cx)
            predictions = model.predict(tx)
            threshold = float(np.median(y)) + .5
            means, covered, probabilities = [], [], []
            # Bound memory when evaluating full NBA seasons.
            for start in range(0, len(predictions), 128):
                samples = np.rint(predictions[start:start+128, None] + residuals[None, :])
                if metric not in ('passing_yards', 'rushing_yards', 'receiving_yards'):
                    samples = np.maximum(0, samples)
                lower, upper = np.quantile(samples, [.1, .9], axis=1)
                means.extend(samples.mean(axis=1))
                actual = ty[start:start+128]
                covered.extend((actual >= lower) & (actual <= upper))
                probabilities.extend((samples > threshold).mean(axis=1))
            report.update(mae=float(np.mean(np.abs(ty - np.array(means)))), interval_80_coverage=float(np.mean(covered)))
            report['threshold_brier'] = float(np.mean((np.array(probabilities) - (ty > threshold)) ** 2))
            report['validation_threshold'] = threshold
            fitted = (model, residuals, report)
        self.fits[metric] = fitted
        return fitted

    def forecast(self, player_id, team, position, game, market):
        metric = METRICS[market]
        features, n = self.features(player_id, team, position, game, metric)
        fitted = self.fit(metric)
        if n < 3 or fitted is None:
            return {'available': False, 'reason': 'Insufficient player history or chronological calibration data', 'sample_size': n}
        model, distribution, report = fitted
        td = metric == 'qualifying_td'
        if td:
            probability = float(distribution.predict(model.predict_proba([features])[:, 1])[0])
            samples = None
            projected, lower, upper = probability, 0, 1
        else:
            center = float(model.predict([features])[0])
            samples = np.rint(center + distribution)
            if metric not in ('passing_yards', 'rushing_yards', 'receiving_yards'):
                samples = np.maximum(0, samples)
            projected = float(np.mean(samples))
            lower, upper = [float(x) for x in np.quantile(samples, [.1, .9])]
            probability = None
        inputs = dict(zip(FEATURES, features))
        model_id = hashlib.sha256(str((VERSION, metric, report['train_before'], report['train_n'], self.source_retrieved_at)).encode()).hexdigest()[:12]
        return {'available': True, 'projected': projected, 'predictive_lower': lower, 'predictive_upper': upper,
                'td_probability': probability, 'td_rules': FANDUEL_TD if td else None, 'sample_size': n, 'model_version': VERSION + ':' + model_id,
                'feature_cutoff': self.cutoff.isoformat(), 'source_retrieved_at': self.source_retrieved_at, 'last_input_game': self.last_game_at.isoformat() if self.last_game_at else None,
                'inputs': inputs, 'validation': report, '_samples': samples,
                'factors': [f'Recent shrunk statistic {features[0]:.1f}; opportunities {features[1]:.1f}',
                            f'Opponent opportunity/strength-adjusted efficiency ratio {features[6]:.3f}',
                            f'Team volume {features[4]:.1f}; opponent sack rate {features[7]:.3f}',
                            f'{"Home" if features[8] else "Away"}; {features[9]:g} days rest'],
                'uncertainties': ['No current injury, starting-QB availability, routes/snaps, weather forecast or pregame spread inputs. Projections and EV are conditional on participation.',
                                  'Past workload proxies role; no explicit injury adjustment. Historical source revisions may affect evaluation.',
                                  'Empirical residual distribution assumes errors remain comparable; held-out validation is not a profitability claim.']}


def quote_probabilities(forecast, line):
    samples = forecast.get('_samples')
    if samples is None or line is None:
        return None
    return {'over': float(np.mean(samples > line)), 'under': float(np.mean(samples < line)), 'push': float(np.mean(samples == line))}


class NBAMatchupModel(MatchupModel):
    """Minutes/pace-driven NBA model, with opponent production per possession."""
    @staticmethod
    def supported(position, market):
        return market in ('Points', 'Assists', 'Rebounds', 'Made three-pointers')

    def _observe(self, game, records):
        for team in (game.home_team, game.away_team):
            own = [v for _, v in records if v['team'] == team]
            total = {k: sum(number(v, k) for v in own) for k in ('points','assists','rebounds','threes','minutes','fga','fta','oreb','tov')}
            total['possessions'] = max(1, total['fga'] + .44 * total['fta'] - total['oreb'] + total['tov'])
            opponent = game.away_team if team == game.home_team else game.home_team
            defense = dict(total)
            prior = self.team_history[team][-10:]
            for metric in ('points','assists','rebounds','threes'):
                rate = sum(p[metric] for p in prior) / max(1, sum(p['possessions'] for p in prior)) if prior else total[metric] / total['possessions']
                defense[metric+'_expected'] = rate * total['possessions']
            self.defense_history[opponent].append(defense)
            self.team_history[team].append(total)
        for pid, values in records:
            self.player_history[pid].append(values)
            self.position_history['NBA'].append(values)

    def features(self, player_id, team, position, game, metric):
        recent = self.player_history[player_id][-10:]
        population = self.position_history['NBA'][-500:]
        prior = self.position_prior('NBA', metric)
        baseline = (sum(number(v, metric) for v in recent) + 2*prior) / (len(recent)+2)
        minutes = np.mean([number(v, 'minutes') for v in recent]) if recent else 0
        efficiency = sum(number(v, metric) for v in recent) / max(1, sum(number(v, 'minutes') for v in recent))
        own = self.team_history[team][-10:]
        pace = np.mean([v['possessions'] for v in own]) if own else 100
        own_eff = sum(v[metric] for v in own) / max(1, sum(v['possessions'] for v in own))
        opponent = game.away_team if team == game.home_team else game.home_team
        defense = self.defense_history[opponent][-10:]
        expected = sum(v[metric+'_expected'] for v in defense)
        allowed = sum(v[metric] for v in defense)
        # Two games of shrinkage toward a ratio of one; actual impact is learned.
        ratio = (allowed + 2*max(prior*5,1)) / (expected + 2*max(prior*5,1))
        home = team == game.home_team
        rest = (game.context or {}).get('home_rest' if home else 'away_rest', 2)
        fga = np.mean([number(v,'fga') for v in recent]) if recent else 0
        fta = np.mean([number(v,'fta') for v in recent]) if recent else 0
        return [float(v) for v in [baseline, minutes, efficiency, minutes/48, pace, own_eff, ratio, 0, home, rest, fga, fta]], len(recent)

    def forecast(self, player_id, team, position, game, market):
        output = super().forecast(player_id, team, position, game, market)
        if output['available']:
            old = list(output['inputs'].values())
            names = ['recent_stat','minutes','stat_per_minute','minutes_share','team_possessions','team_stat_per_possession','opponent_efficiency_ratio','unused','home','rest_days','recent_fga','recent_fta']
            output['inputs'] = dict(zip(names, old))
            output['factors'] = [f'Recent shrunk statistic {old[0]:.1f}; minutes {old[1]:.1f}', f'Team estimated possessions {old[4]:.1f}; opponent efficiency ratio {old[6]:.3f}', f'{"Home" if old[8] else "Away"}; rest input {old[9]:g} days']
            output['uncertainties'] = ['No current injury, starting lineup or explicit rotation adjustment.', 'Pace uses estimated possessions; date-only historical logs use conservative availability times.', 'Rest defaults to two days where unavailable. Empirical residuals assume comparable future errors.']
        return output
