from app.services.odds import american_to_decimal, decimal_to_implied_probability, evaluate_parlay, normalize_no_vig


def test_american_odds_conversion():
    assert american_to_decimal(150) == 2.5
    assert american_to_decimal(-200) == 1.5


def test_no_vig_normalization():
    result = normalize_no_vig([0.55, 0.5])
    assert sum(result) == 1
    assert result[0] > result[1]


def test_parlay_uses_independent_different_games():
    result = evaluate_parlay([
        {"id": "a", "game_id": "g1", "probability": 0.6, "decimal_odds": 1.8},
        {"id": "b", "game_id": "g2", "probability": 0.5, "decimal_odds": 2.0},
    ], 10)
    assert result.valid is True
    assert result.joint_probability == 0.3
    assert result.correlation_status == "assumed_independent"


def test_parlay_rejects_same_game_and_duplicates():
    same_game = evaluate_parlay([
        {"id": "a", "game_id": "g1", "probability": 0.6, "decimal_odds": 1.8},
        {"id": "b", "game_id": "g1", "probability": 0.5, "decimal_odds": 2.0},
    ], 10)
    duplicate = evaluate_parlay([
        {"id": "a", "game_id": "g1", "probability": 0.6, "decimal_odds": 1.8},
        {"id": "a", "game_id": "g2", "probability": 0.5, "decimal_odds": 2.0},
    ], 10)
    assert same_game.valid is False
    assert duplicate.valid is False
