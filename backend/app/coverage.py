from dataclasses import dataclass


@dataclass(frozen=True)
class CoverageSummary:
    rostered_players: int
    players_with_upcoming_game: int
    players_with_projection: int
    players_with_market: int
    failures: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "rostered_players": self.rostered_players,
            "players_with_upcoming_game": self.players_with_upcoming_game,
            "players_with_projection": self.players_with_projection,
            "players_with_market": self.players_with_market,
            "failures": list(self.failures),
        }
