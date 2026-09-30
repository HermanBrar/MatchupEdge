"""Book-specific touchdown definitions; unknown rules are never inferred."""
FANDUEL_TD = {
    'id': 'fanduel-in-offense-special-teams-td-v1',
    'source': 'https://www.fanduel.com/fanduel-sportsbook-house-rules-in',
    'checked_at': '2026-09-29',
    'description': 'FanDuel Indiana: individual offensive or special-teams scorer, including overtime; passing and defensive touchdowns excluded. Conditional on playing a snap; no-snap selections void.',
}


def touchdown_target(values):
    """At least one offensive/special-teams touchdown, not a passing TD.

Fumble recoveries without enough unit information are missing targets, never
silently graded as defensive or offensive. Positive known qualifying TDs suffice.
"""
    fields = ('rushing_tds', 'receiving_tds', 'special_teams_tds', 'fumble_recovery_tds', 'def_tds')
    if any(values.get(k) is None for k in fields):
        return None
    if sum(float(values[k]) for k in fields[:3]) > 0:
        return 1.0
    fumbles, defensive = float(values['fumble_recovery_tds']), float(values['def_tds'])
    if fumbles > 0:
        return 1.0 if fumbles > defensive else None
    return 0.0


def scorer_rules(book_key):
    return FANDUEL_TD if book_key == 'fanduel' else None
