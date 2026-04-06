# NBA API Explorer

Flask backend + Vue 3 SPA that proxies `nba-api` for live NBA data and visualizes the API structure as an interactive node graph.

## Stack

- **Backend**: Python / Flask (`server.py`)
- **Frontend**: Vue 3 via CDN, single-file (`static/index.html`)
- **Data source**: `nba_api` Python package (stats.nba.com)
- **Tests**: pytest — `test_unit.py` (mocked, fast) + `test_server.py` (integration, real API)

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
source venv/bin/activate
python3 server.py                           # http://localhost:5000
pytest test_unit.py -v                      # unit tests, no internet, ~13s
pytest test_server.py -v                    # integration tests, requires internet, ~60–90s
```

## Architecture

- `server.py` — All routes, caching, and data fetching. In-memory cache with TTL. `CURRENT_SEASON` must be updated manually each year.
- `static/index.html` — Self-contained Vue 3 app with canvas-based graph, side panel, chart rendering, nested-array table renderer for analytics responses. Has a `FALLBACK_MAP` so the UI works without the backend.
- `conftest.py` — Session-scoped cache warming to avoid cold NBA API hits during integration tests. Analytics warm-up is best-effort (try/except) so unit test sessions are not blocked by API failures.
- `test_unit.py` — 62 unit tests. Mocks all nba_api calls with pandas DataFrames. Uses `unit_client` fixture (not `client`) to avoid scope conflict with conftest's session-scoped `client`.
- `test_server.py` — 111 integration tests for every API node. Uses real nba-api calls.

## API Endpoints

### Core

| Route | Description |
|---|---|
| `GET /` | Serves index.html |
| `GET /api/map` | Returns the API node graph structure (13 nodes) |
| `GET /api/teams` | All 30 NBA teams |
| `GET /api/teams/<id>` | Single team + roster |
| `GET /api/players` | All players (per-game stats), optional `?team_id=` |
| `GET /api/players/<id>` | Player info + season averages |
| `GET /api/players/<id>/gamelog` | Per-game log, optional `?n=` |
| `GET /api/standings` | Standings, optional `?conference=` |
| `GET /api/games` | Recent games, optional `?date=YYYY-MM-DD` |
| `GET /api/games/<id>` | Box score detail |

### Analytics

| Route | Description |
|---|---|
| `GET /api/analytics/last-night` | Top performers + scores from last night (falls back to prior night). Returns `date`, `game_count`, `games[]`, `top_performers[]` with computed TS%. |
| `GET /api/analytics/season` | Advanced player stats (TS%, eFG%, USG%, NetRtg, PIE; ≥20 GP) in three sorted lists, plus all-team advanced stats sorted by NetRtg. |
| `GET /api/analytics/lakers` | Lakers (team_id=1610612747) dashboard: standing, home/away/L10/streak, team advanced stats, last 10 games, roster sorted by PPG with TS%/USG%/NetRtg. |

## Constants

- `CURRENT_SEASON` — derived automatically from `_current_nba_season()` (Oct–Dec = new season, Jan–Sep = prior season)
- `LAKERS_TEAM_ID = 1610612747`

## Known Issues

- `CURRENT_SEASON` is auto-derived but computed once at import time; a long-running server started in September won't roll over until restarted
- In-memory cache does not survive server restarts
- No pagination on `/api/players` (returns all ~400+ players)
- `season_type` hardcoded to `"Regular Season"` — no Playoffs mode
- `/api/analytics/lakers` is team-specific, not yet generalized to `/api/analytics/team/<id>`

## Conventions

- All JSON responses use `{ "data": ..., "_meta": { "endpoint": "..." } }` shape
- Cache TTLs: teams/players/player detail/analytics = 3600s; standings/games/gamelog/lakers = 300–600s
- Tests are grouped by API node in classes (e.g., `TestTeams`, `TestLakersDashboard`)
- Unit test client fixture is `unit_client` (not `client`) — scope isolation from conftest

## Related Project

The autochess game ("B-Ball Tactics") lives in `../BballTactics/`.
