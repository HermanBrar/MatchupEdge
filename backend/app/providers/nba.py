from .base import ProviderCapability, ProviderError


class NBAApiProvider:
    name = "nba_api"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(self.name, "NBA", "teams_and_players", "supported", "nba_api static datasets",),
            ProviderCapability(self.name, "NBA", "schedules", "supported", "NBA.com live scoreboard endpoint through nba_api"),
            ProviderCapability(self.name, "NBA", "player_game_stats", "supported", "NBA.com playergamelog endpoint; rate limits apply"),
            ProviderCapability(self.name, "NBA", "injuries", "unavailable", "nba_api does not provide a reliable official injury feed"),
            ProviderCapability(self.name, "NBA", "odds", "unavailable", "Use The Odds API adapter for sportsbook markets"),
        ]

    def load_teams(self):
        try:
            from nba_api.stats.static import teams
            return teams.get_teams()
        except Exception as exc:
            raise ProviderError(f"nba_api static teams unavailable: {exc}") from exc

    def load_players(self, current_only: bool = True):
        try:
            from nba_api.stats.static import players
            records = players.get_active_players() if current_only else players.get_players()
            return records
        except Exception as exc:
            raise ProviderError(f"nba_api static players unavailable: {exc}") from exc

    def load_schedule(self):
        try:
            from nba_api.live.nba.endpoints import scoreboard
            return scoreboard.ScoreBoard().get_dict()
        except Exception as exc:
            raise ProviderError(f"NBA.com scoreboard unavailable: {exc}") from exc

    def load_player_game_log(self, player_id: str, season: str):
        try:
            from nba_api.stats.endpoints import playergamelog
            return playergamelog.PlayerGameLog(player_id=player_id, season=season).get_data_frames()[0]
        except Exception as exc:
            raise ProviderError(f"NBA.com player game log unavailable for {player_id}: {exc}") from exc
