# MatchupEdge

A local NFL/NBA matchup projection board with real schedules, verified player IDs,
sportsbook comparison, pregame snapshots and explicit Demo/Historical/Live modes.

## Run

Run commands from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

In another terminal:

```bash
npm install --prefix frontend
npm run dev --prefix frontend
```

Default URLs: frontend `http://localhost:5173`, backend `http://localhost:8000`.
`frontend/.env.local` can set `VITE_API_URL`; restart Vite after changing it.
This development session uses frontend `http://localhost:5175` and API
`http://localhost:8010` because the original ports were occupied.

## Credentials

The backend reads **`/Users/hermanbrar/MatchupEdge/Project/.env`** in this checkout.
`backend/app/config.py` resolves that path from the repository root, independent
of the process working directory. Environment variables override the file.

Set locally, without sending the value through chat:

```dotenv
APP_MODE=live
ODDS_API_KEY=your_key_here
```

The provided key has been stored in that ignored local file with private file
permissions. Restart the backend after changing it. Rotate a key shared in chat.
Secrets are excluded from provider exceptions, API responses and source files.

## Ingest and evaluate

```bash
PYTHONPATH=backend python -m app.cli ingest-nfl --seasons 2024 2025 2026
PYTHONPATH=backend python -m app.cli ingest-nba
PYTHONPATH=backend python -m app.cli evaluate-matchups
PYTHONPATH=backend pytest backend/tests
npm run build --prefix frontend
```

The UI also has separate buttons to refresh statistics/schedules, fetch lines,
and save pregame snapshots. Quote reads do not spend provider credits. Explicit
quote refresh uses the free events endpoint, then event-level player props for
only the selected slate; successful batches have a five-minute request cache.
The provider's quota headers are returned. Missing markets say "Line not posted";
unfetched markets say "Quotes not fetched". No fabricated lines are supplied.

NFL releases refresh after one hour. NBA completed-season game logs are cached.
The NBA schedule CDN returned HTTP failure during verification; real upcoming
Odds API events supply the NBA slate with `the_odds_api` provenance. The current
NBA feed covered three games on October 20, 2026. NBA rosters/game logs came from
NBA.com via nba_api. Neither failure nor missing coverage falls back to Demo.

## Weekly workflow and identity

`GET /api/v1/slate` defaults to the current NFL season and earliest unstarted
scheduled game, then selects its season type and week. Filters include `sport`,
`season`, `season_type`, `week`, `date`, `view`, and `sportsbook`. NBA dates use
US Eastern time. Completed games and saved prediction snapshots have separate
views; the complete schedule view includes postponed/TBD games.

Player cards contain only their matched game in that slate, grouping supported
markets below the player. GSIS/NBA IDs join statistics; historical game teams are
preserved. Roster assignments carry season/week and timestamps. Odds API props
provide names rather than stable player IDs: only unique normalized names within
the exact event's verified roster resolve to provider IDs. Ambiguous outcomes are
quarantined. Event matching requires both teams and kickoff, and quote identities
include player, game, market, full-game period, exact line and book. Different
lines are never paired as over/under counterparts.

A.J. Brown is GSIS `00-0035676`. The retrieved 2026 week-4 roster places him on NE
with status `RES`. His sole card is NE at BUF; availability is unconfirmed and
his forecast is withheld. His historical PHI games retain PHI.

## Model and limitations

`matchup-ridge-empirical-v2` constructs chronological pregame features from player
workload, team volume/efficiency, opponent efficiency normalized by opportunities
and prior opponent offensive strength, sacks, home field and rest. Small samples
shrink toward historical position priors. NFL models cover passing/rushing/
receiving yards and receptions. NBA models cover points, assists, rebounds and
made threes with minutes, shooting opportunities and possession-normalized
opponent production. Each forecast uses its selected opponent; there is no sum
across weeks and no copied player-season forecast.

Games become statistical inputs only after a conservative eight-hour availability
lag. Training, calibration and test splits are chronological and separated at
kickoff boundaries (60/20/20). Ridge residuals from the calibration partition
form discrete predictive samples; a later holdout checks MAE, 80% coverage and
threshold Brier scores. Integer lines include push mass. EV uses each actual
book's odds and excludes the push stake from losses. Predictions and EV are
conditional on participation; void/DNP probability is not modeled.

Anytime touchdown uses logistic regression with chronological isotonic
calibration. Its target follows FanDuel Indiana's offensive/special-teams scorer
rules, includes overtime, and excludes passing/defensive scores. Ambiguous
fumble-recovery scoring units are missing targets. FanDuel probabilities/EV use
that rule set; other books' quotes remain visible, but their touchdown pricing is
withheld until their rule sets are mapped. See the linked rule source on cards.

Missing inputs are explicitly disclosed: current injuries, quarterback/receiver
availability, routes/snaps, forecast weather and pregame game-total/spread context.
Reserve/inactive roster players have forecasts withheld. NBA rest defaults to two
days when unavailable. The model is not advertised as injury-aware or calibrated
for every subgroup. Full validation is in `data/reports/matchup_evaluation.json`.
Historical source revisions are not point-in-time archives, so evaluation is
labeled retrospective. Historical predictions are immutable saved pregame
snapshots, never recreated from today's roster. Exact historic book odds and
profitability validation are not available from these free statistical feeds.

## Provider documentation

- [The Odds API event-level odds](https://the-odds-api.com/liveapi/guides/v4/#get-event-odds)
- [Supported market keys](https://the-odds-api.com/sports-odds-data/betting-markets.html)
- [nflverse schedule dictionary](https://nflreadr.nflverse.com/articles/dictionary_schedules.html)
- [FanDuel Indiana touchdown rules](https://www.fanduel.com/fanduel-sportsbook-house-rules-in)

See `IMPLEMENTATION_PLAN.md` for completed work and remaining feed/model coverage.
