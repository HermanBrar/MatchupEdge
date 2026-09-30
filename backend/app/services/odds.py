from dataclasses import dataclass


class OddsError(ValueError):
    pass


def american_to_decimal(american: int) -> float:
    if american == 0:
        raise OddsError("American odds cannot be zero")
    return 1 + (american / 100 if american > 0 else 100 / abs(american))


def decimal_to_implied_probability(decimal: float) -> float:
    if decimal <= 1:
        raise OddsError("Decimal odds must be greater than 1")
    return 1 / decimal


def normalize_no_vig(probabilities: list[float]) -> list[float]:
    if len(probabilities) < 2 or any(probability <= 0 for probability in probabilities):
        raise OddsError("At least two positive probabilities are required")
    total = sum(probabilities)
    return [probability / total for probability in probabilities]


def expected_return(probability: float, decimal_odds: float, stake: float) -> float:
    if not 0 <= probability <= 1 or decimal_odds <= 1 or stake < 0:
        raise OddsError("Invalid probability, odds, or stake")
    return probability * stake * (decimal_odds - 1) - (1 - probability) * stake


@dataclass(frozen=True)
class ParlayResult:
    valid: bool
    message: str
    joint_probability: float | None = None
    decimal_odds: float | None = None
    potential_profit: float | None = None
    expected_return: float | None = None
    correlation_status: str = "unknown"


def evaluate_parlay(legs: list[dict], stake: float, quoted_decimal_odds: float | None = None) -> ParlayResult:
    if len(legs) < 2 or len(legs) > 4:
        return ParlayResult(False, "Parlays must contain 2 to 4 legs", correlation_status="unavailable")
    ids = [leg["id"] for leg in legs]
    if len(ids) != len(set(ids)):
        return ParlayResult(False, "Duplicate legs are not allowed", correlation_status="unavailable")
    games = [leg["game_id"] for leg in legs]
    if len(games) != len(set(games)):
        return ParlayResult(False, "Same-game correlation is unavailable in Milestone 1", correlation_status="unavailable")
    joint = 1.0
    for leg in legs:
        probability = leg["probability"]
        if not 0 <= probability <= 1 or leg["decimal_odds"] <= 1:
            return ParlayResult(False, "Each leg needs valid probability and decimal odds", correlation_status="unavailable")
        joint *= probability
    decimal_odds = quoted_decimal_odds or _product_odds(legs)
    return ParlayResult(
        valid=True,
        message="Independent-leg estimate; different games are not proven independent.",
        joint_probability=joint,
        decimal_odds=decimal_odds,
        potential_profit=stake * (decimal_odds - 1),
        expected_return=expected_return(joint, decimal_odds, stake),
        correlation_status="assumed_independent",
    )


def _product_odds(legs: list[dict]) -> float:
    result = 1.0
    for leg in legs:
        result *= leg["decimal_odds"]
    return result
