from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

import time
import certifi
import pandas as pd

from .base import ProviderCapability, ProviderError


class NFLVerseProvider:
    name = "nflverse"
    base_url = "https://github.com/nflverse/nflverse-data/releases/download"

    def __init__(self, cache_dir: str | Path = "data/cache/nflverse", timeout: int = 60):
        self.cache_dir = Path(cache_dir)
        self.timeout = timeout

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(self.name, "NFL", "schedules", "supported", "Public nflverse games.csv release"),
            ProviderCapability(self.name, "NFL", "rosters", "supported", "Public season roster release"),
            ProviderCapability(self.name, "NFL", "player_game_stats", "supported", "Public weekly player stats"),
            ProviderCapability(self.name, "NFL", "injuries", "supported", "Historical injury reports; current availability can lag",),
            ProviderCapability(self.name, "NFL", "odds", "unavailable", "nflverse schedule odds are historical game markets, not current sportsbook quotes"),
        ]

    def load_schedules(self) -> pd.DataFrame:
        return self._csv("schedules", "games.csv")

    def load_players(self) -> pd.DataFrame:
        return self._csv("players", "players.csv")

    def load_roster(self, season: int) -> pd.DataFrame:
        return self._csv("rosters", f"roster_{season}.csv")

    def load_player_stats(self, season: int) -> pd.DataFrame:
        return self._csv("stats_player", f"stats_player_week_{season}.csv")

    def load_teams(self) -> pd.DataFrame:
        return self._csv("teams", "teams.csv")

    def load_injuries(self, season: int) -> pd.DataFrame:
        return self._csv("injuries", f"injuries_{season}.csv")

    def _csv(self, release: str, filename: str) -> pd.DataFrame:
        target = self.cache_dir / release / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or time.time() - target.stat().st_mtime > 3600:
            url = f"{self.base_url}/{release}/{filename}"
            request = Request(url, headers={"User-Agent": "MatchupEdge/0.2"})
            try:
                import ssl

                context = ssl.create_default_context(cafile=certifi.where())
                with urlopen(request, timeout=self.timeout, context=context) as response:
                    target.write_bytes(response.read())
            except Exception as exc:
                raise ProviderError(f"nflverse download failed for {filename}: {exc}") from exc
        try:
            return pd.read_csv(target, low_memory=False)
        except Exception as exc:
            raise ProviderError(f"nflverse parse failed for {target}: {exc}") from exc

    @staticmethod
    def retrieved_at() -> datetime:
        return datetime.now(timezone.utc)
