# NBA API Explorer

A Flask + Vue 3 web app that proxies `nba_api` for live NBA data and visualizes
the API structure as an interactive node graph.

---

## Quick Start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 server.py          # → http://localhost:5000
```

---

## Status

### Completed

| Area | Detail |
|---|---|
| Core API | 10 routes covering teams, players, standings, games, box scores |
| Advanced Analytics | 3 new endpoints: last night, full-season advanced stats, Lakers dashboard |
| Frontend | Vue 3 SPA — interactive canvas node graph, data tables, charts, nested-array rendering for analytics responses |
| In-memory cache | TTL-based per endpoint (300–3600s); warm-up on test session start |
| Unit tests | 62 tests, mocked nba_api, no internet required, ~13s |
| Integration tests | 111 tests across all 13 API nodes, real nba_api calls, ~60–90s |

### API Endpoints

#### Core

| Route | Description | Cache TTL |
|---|---|---|
| `GET /` | Serves index.html | — |
| `GET /api/map` | Node graph structure | — |
| `GET /api/teams` | All 30 NBA teams | 3600s |
| `GET /api/teams/<id>` | Single team + roster | — |
| `GET /api/players` | All players (per-game stats), optional `?team_id=` | 3600s |
| `GET /api/players/<id>` | Player info + season averages | 3600s |
| `GET /api/players/<id>/gamelog` | Per-game log, optional `?n=` | 300s |
| `GET /api/standings` | Current standings, optional `?conference=` | 600s |
| `GET /api/games` | Recent games, optional `?date=YYYY-MM-DD` | 300s |
| `GET /api/games/<id>` | Full box score | 3600s |

#### Analytics

| Route | Description | Cache TTL |
|---|---|---|
| `GET /api/analytics/last-night` | Scores + top performers from last night (falls back to prior night on off-days). Returns `games`, `top_performers` with computed TS%. | 3600s |
| `GET /api/analytics/season` | Season-wide advanced stats. `top_players_ts` / `top_players_net` / `top_players_usg` (≥20 GP), all 30 teams by NetRtg. | 3600s |
| `GET /api/analytics/lakers` | Lakers dashboard: W/L record, home/away splits, L10, streak, team advanced stats (NetRtg, OffRtg, DefRtg, Pace, TS%, eFG%), roster sorted by PPG with TS%/USG%/NetRtg per player, last 10 games. | 600s |

### Test Coverage

```
test_unit.py       62 tests   — unit, mocked, ~13s, no internet
test_server.py    111 tests   — integration, real API, ~60–90s
─────────────────────────────
Total             173 tests
```

Unit tests cover: route status codes, response shapes, filter logic (team_id,
conference), cache hit/miss/expiry, 404 handling, TS% computation, GP minimum
filter, sort orders (pct desc, ppg desc, net_rating desc).

Integration tests cover: all 13 API nodes, real response shapes, Jokic/Nuggets
as stable fixtures, Lakers team_id `1610612747`, conference filters,
`?n=` param, date param, box score structure.

### Known Issues / Tech Debt

- `CURRENT_SEASON = "2025-26"` in `server.py` must be updated manually each year
- In-memory cache is lost on server restart; a production deploy needs Redis or
  disk persistence
- The player list (~400+ entries) returns everything in one response — no
  pagination or cursor support
- `season_type` is hardcoded to `"Regular Season"`; no Playoffs mode
- The `/api/analytics/lakers` endpoint is team-specific; there is no generic
  `/api/analytics/team/<id>` equivalent yet
- Frontend layout is two-column fixed-width; not mobile-responsive

---

## Conventions

- All JSON responses: `{ "data": ..., "_meta": { "endpoint": "..." } }`
- Cache keys are descriptive strings (`"teams"`, `"players"`, `"last_night"`, etc.)
- Tests grouped by API node in classes (`TestTeams`, `TestLakersDashboard`, etc.)
- Unit test client fixture is named `unit_client` (not `client`) to avoid a
  scope conflict with conftest's session-scoped `client` used by `warm_cache`

---

## Running Tests

```bash
# Fast unit tests — no internet required
pytest test_unit.py -v

# Full integration suite — requires internet, ~60–90s
pytest test_server.py -v

# Both
pytest test_unit.py test_server.py -v
```

---

## Next Steps

> **ACTION REQUIRED — Design Walkthrough**
> A design review session with the user is needed before implementing items below.
> Topics to cover: analytics UX (how to surface last-night data on load, Lakers
> sidebar vs. dedicated page), team dashboard generalization, mobile layout,
> and playoff mode.

### Prioritised Backlog

| Priority | Item | Notes |
|---|---|---|
| P0 | **Design walkthrough** | Schedule before any UX-impacting work |
| ~~P1~~ | ~~Generalize team dashboard~~ | ✓ Done — `/api/analytics/team/<id>` added; Lakers is now an alias |
| P1 | Playoff mode toggle | `season_type` param; affects games, standings, analytics |
| ~~P1~~ | ~~Auto-update `CURRENT_SEASON`~~ | ✓ Done — `_current_nba_season()` derives from system clock |
| P2 | Pagination for `/api/players` | Cursor or `?page=` / `?limit=` |
| P2 | Player / team search | Filter by name substring; frontend search box |
| P2 | Frontend error states | Surface API errors in the panel instead of raw JSON |
| P2 | Persistent cache | Redis or SQLite; survive restarts |
| P3 | Mobile-responsive layout | Collapse side panel to bottom sheet on small screens |
| P3 | Shot chart endpoint | `shotchartdetail` nba_api endpoint |
| P3 | Head-to-head comparison | Compare two players or two teams side by side |
| P3 | CI pipeline | GitHub Actions: run `test_unit.py` on every PR |

---

## Stack

- **Backend**: Python 3.14 / Flask 3.1 (`server.py`)
- **Frontend**: Vue 3 via CDN, single-file (`static/index.html`)
- **Data source**: `nba_api` 1.11.4 (stats.nba.com)
- **Tests**: pytest 9.0 — `test_unit.py` (mocked) + `test_server.py` (integration)

## Related Project

B-Ball Tactics (autochess) lives in `../BballTactics/`.
