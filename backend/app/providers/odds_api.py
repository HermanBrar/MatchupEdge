import json
import ssl
from urllib.error import HTTPError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
import certifi
from ..config import ENV_FILE, get_settings
from .base import ProviderCapability, ProviderError

SPORT_KEYS = {'NFL': 'americanfootball_nfl', 'NBA': 'basketball_nba'}
MARKETS = {
    'NFL': {'player_pass_yds': 'Passing yards', 'player_rush_yds': 'Rushing yards',
            'player_reception_yds': 'Receiving yards', 'player_receptions': 'Receptions',
            'player_anytime_td': 'Anytime touchdown'},
    'NBA': {'player_points': 'Points', 'player_assists': 'Assists',
            'player_rebounds': 'Rebounds', 'player_threes': 'Made three-pointers'},
}


class OddsApiProvider:
    name = 'the_odds_api'
    base_url = 'https://api.the-odds-api.com/v4'

    def __init__(self, api_key: str | None = None, timeout: int = 20):
        configured = get_settings().odds_api_key
        self.api_key = api_key if api_key is not None else (configured.get_secret_value() if configured else None)
        self.timeout = timeout

    def capabilities(self):
        detail = 'Event-level NFL/NBA player props' if self.api_key else f'Set ODDS_API_KEY in {ENV_FILE}; restart the backend.'
        return [ProviderCapability(self.name, 'NFL/NBA', 'current_sportsbook_odds', 'configured' if self.api_key else 'blocked', detail, requires_key=True)]

    def _get(self, path, **params):
        if not self.api_key:
            raise ProviderError(f'Set ODDS_API_KEY in {ENV_FILE}; restart the backend. Never send keys through chat.')
        query = urlencode({'apiKey': self.api_key, **params})
        request = Request(f'{self.base_url}/{path}?{query}', headers={'User-Agent': 'MatchupEdge/0.3'})
        try:
            with urlopen(request, timeout=self.timeout, context=ssl.create_default_context(cafile=certifi.where())) as response:
                quota = {key: response.headers.get(key, '') for key in ('x-requests-remaining', 'x-requests-used', 'x-requests-last')}
                return json.loads(response.read()), quota
        except HTTPError as exc:
            # Never include exception URLs: they contain credentials.
            raise ProviderError(f'The Odds API returned HTTP {exc.code}; check account access/quota locally.') from None
        except Exception:
            raise ProviderError('The Odds API connection failed; check network access.') from None

    def load_events(self, sport):
        return self._get(f'sports/{SPORT_KEYS[sport]}/events', dateFormat='iso')

    def load_event_odds(self, sport, event_id):
        return self._get(f'sports/{SPORT_KEYS[sport]}/events/{quote(event_id, safe="")}/odds',
                         regions='us', markets=','.join(MARKETS[sport]), oddsFormat='american', dateFormat='iso')

    def load_odds(self, sport_key, markets='h2h,spreads,totals'):
        return self._get(f'sports/{sport_key}/odds', regions='us', markets=markets, oddsFormat='american')
