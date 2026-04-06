"""
NBA API Explorer - Flask Backend
Proxies calls to nba-api for live NBA data.
Run: python server.py
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import time
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

def _current_nba_season() -> str:
    """Return the active NBA season string, e.g. '2025-26'.
    Seasons begin in October, so Oct–Dec belong to the new season year."""
    now = datetime.now()
    year = now.year
    if now.month >= 10:
        return f"{year}-{str(year + 1)[-2:]}"
    return f"{year - 1}-{str(year)[-2:]}"


CURRENT_SEASON: str = _current_nba_season()
LAKERS_TEAM_ID = 1610612747

# ── In-Memory Cache ───────────────────────────────────────────────────────────

_cache: dict = {}


def _cached(key: str, fn, ttl: int = 600):
    now = time.time()
    if key in _cache and now - _cache[key]["ts"] < ttl:
        return _cache[key]["data"]
    data = fn()
    _cache[key] = {"ts": now, "data": data}
    return data


# ── Data Fetchers ─────────────────────────────────────────────────────────────

def _fetch_teams():
    from nba_api.stats.static import teams as nba_teams_static
    from nba_api.stats.endpoints import leaguestandingsv3

    static_map = {t["id"]: t for t in nba_teams_static.get_teams()}
    df = leaguestandingsv3.LeagueStandingsV3(
        season=CURRENT_SEASON
    ).standings.get_data_frame()

    return [
        {
            "id": int(row["TeamID"]),
            "name": row["TeamName"],
            "city": row["TeamCity"],
            "abbrev": static_map.get(int(row["TeamID"]), {}).get("abbreviation", ""),
            "conference": row["Conference"],
            "division": row["Division"],
        }
        for _, row in df.iterrows()
    ]


def _get_teams():
    return _cached("teams", _fetch_teams, ttl=3600)


def _fetch_players():
    from nba_api.stats.endpoints import leaguedashplayerstats

    df = leaguedashplayerstats.LeagueDashPlayerStats(
        season=CURRENT_SEASON,
        per_mode_detailed="PerGame",
    ).league_dash_player_stats.get_data_frame()

    return [
        {
            "id": int(row["PLAYER_ID"]),
            "name": row["PLAYER_NAME"],
            "team_id": int(row["TEAM_ID"]),
            "pos": "",
            "ppg": round(float(row["PTS"]), 1),
            "rpg": round(float(row["REB"]), 1),
            "apg": round(float(row["AST"]), 1),
        }
        for _, row in df.iterrows()
    ]


def _get_players():
    return _cached("players", _fetch_players, ttl=3600)


def _fetch_standings_df():
    from nba_api.stats.endpoints import leaguestandingsv3

    return leaguestandingsv3.LeagueStandingsV3(
        season=CURRENT_SEASON
    ).standings.get_data_frame()


# ── API Endpoint Map ──────────────────────────────────────────────────────────

API_MAP = {
    "root": {
        "label": "NBA API",
        "description": "Entry point",
        "children": ["teams", "players", "standings", "games", "analytics"],
    },
    "analytics": {
        "label": "Analytics",
        "description": "Advanced analytics hub",
        "children": ["last_night", "season_analytics", "team_dashboard", "lakers_dashboard"],
    },
    "last_night": {
        "label": "Last Night",
        "endpoint": "/api/analytics/last-night",
        "description": "Top performers and scores from last night's games",
        "children": [],
        "params": [],
    },
    "season_analytics": {
        "label": "Season Analytics",
        "endpoint": "/api/analytics/season",
        "description": "Season-wide advanced player and team stats (TS%, eFG%, NetRtg, USG%)",
        "children": [],
        "params": [],
    },
    "lakers_dashboard": {
        "label": "Lakers",
        "endpoint": "/api/analytics/lakers",
        "description": "Lakers dashboard (alias for /api/analytics/team/1610612747)",
        "children": [],
        "params": [],
    },
    "team_dashboard": {
        "label": "Team Dashboard",
        "endpoint": "/api/analytics/team/{id}",
        "description": "Standing, roster advanced stats, and recent games for any team",
        "children": [],
        "params": [{"name": "id", "type": "int", "required": True}],
    },
    "teams": {
        "label": "Teams",
        "endpoint": "/api/teams",
        "description": "All NBA teams",
        "children": ["team_detail"],
        "params": [],
    },
    "players": {
        "label": "Players",
        "endpoint": "/api/players",
        "description": "All players (current season per-game stats)",
        "children": ["player_detail"],
        "params": [{"name": "team_id", "type": "int", "optional": True}],
    },
    "standings": {
        "label": "Standings",
        "endpoint": "/api/standings",
        "description": "Current standings",
        "children": [],
        "params": [{"name": "conference", "type": "str", "optional": True}],
    },
    "games": {
        "label": "Games",
        "endpoint": "/api/games",
        "description": "Recent games",
        "children": ["game_detail"],
        "params": [{"name": "date", "type": "str (YYYY-MM-DD)", "optional": True}],
    },
    "team_detail": {
        "label": "Team Detail",
        "endpoint": "/api/teams/{id}",
        "description": "Single team + roster",
        "children": ["players"],
        "params": [{"name": "id", "type": "int", "required": True}],
    },
    "player_detail": {
        "label": "Player Detail",
        "endpoint": "/api/players/{id}",
        "description": "Player info + season averages",
        "children": ["game_log"],
        "params": [{"name": "id", "type": "int", "required": True}],
    },
    "game_log": {
        "label": "Game Log",
        "endpoint": "/api/players/{id}/gamelog",
        "description": "Per-game stats",
        "children": [],
        "params": [
            {"name": "id", "type": "int", "required": True},
            {"name": "n", "type": "int", "optional": True},
        ],
    },
    "game_detail": {
        "label": "Game Detail",
        "endpoint": "/api/games/{id}",
        "description": "Box score",
        "children": ["player_detail"],
        "params": [{"name": "id", "type": "int", "required": True}],
    },
}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/api/map")
def api_map():
    return jsonify(API_MAP)


@app.route("/api/teams")
def teams():
    data = _get_teams()
    return jsonify({"data": data, "_meta": {"count": len(data), "endpoint": "teams"}})


@app.route("/api/teams/<int:team_id>")
def team_detail(team_id):
    from nba_api.stats.endpoints import commonteamroster

    all_teams = _get_teams()
    team = next((t for t in all_teams if t["id"] == team_id), None)
    if not team:
        return jsonify({"error": "Not found"}), 404

    df = commonteamroster.CommonTeamRoster(
        team_id=team_id, season=CURRENT_SEASON
    ).common_team_roster.get_data_frame()

    roster = [
        {
            "id": int(row["PLAYER_ID"]),
            "name": row["PLAYER"],
            "pos": row["POSITION"],
            "num": row["NUM"],
        }
        for _, row in df.iterrows()
    ]

    return jsonify({
        "data": {**team, "roster": roster},
        "_meta": {"endpoint": "team_detail"},
    })


@app.route("/api/players")
def players():
    tid = request.args.get("team_id", type=int)
    data = _get_players()
    if tid:
        data = [p for p in data if p["team_id"] == tid]
    return jsonify({"data": data, "_meta": {"count": len(data), "endpoint": "players"}})


def _fetch_player_detail(player_id: int) -> dict | None:
    from nba_api.stats.endpoints import commonplayerinfo

    df = commonplayerinfo.CommonPlayerInfo(
        player_id=player_id
    ).common_player_info.get_data_frame()

    if df.empty:
        return None

    row = df.iloc[0]
    all_players = _get_players()
    stats = next((p for p in all_players if p["id"] == player_id), {})

    return {
        "id": player_id,
        "name": row["DISPLAY_FIRST_LAST"],
        "team_id": int(row["TEAM_ID"]) if row["TEAM_ID"] else 0,
        "pos": row["POSITION"],
        "jersey": row["JERSEY"],
        "height": row["HEIGHT"],
        "weight": row["WEIGHT"],
        "country": row["COUNTRY"],
        "ppg": stats.get("ppg", 0),
        "rpg": stats.get("rpg", 0),
        "apg": stats.get("apg", 0),
    }


@app.route("/api/players/<int:player_id>")
def player_detail(player_id):
    data = _cached(
        f"player_{player_id}",
        lambda: _fetch_player_detail(player_id),
        ttl=3600,
    )
    if data is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"data": data, "_meta": {"endpoint": "player_detail"}})


def _fetch_player_gamelog(player_id: int) -> list:
    from nba_api.stats.endpoints import playergamelog

    df = playergamelog.PlayerGameLog(
        player_id=player_id, season=CURRENT_SEASON
    ).player_game_log.get_data_frame()

    return [
        {
            "game": i + 1,
            "date": row["GAME_DATE"],
            "matchup": row["MATCHUP"],
            "pts": int(row["PTS"]),
            "reb": int(row["REB"]),
            "ast": int(row["AST"]),
            "fg_pct": round(float(row["FG_PCT"]), 3),
            "min": str(row["MIN"]),
            "wl": row["WL"],
        }
        for i, (_, row) in enumerate(df.iterrows())
    ]


@app.route("/api/players/<int:player_id>/gamelog")
def game_log(player_id):
    n = request.args.get("n", 10, type=int)
    all_games = _cached(
        f"gamelog_{player_id}",
        lambda: _fetch_player_gamelog(player_id),
        ttl=300,
    )
    return jsonify({
        "data": all_games[:n],
        "_meta": {"endpoint": "game_log", "player_id": player_id},
    })


@app.route("/api/standings")
def standings():
    from nba_api.stats.static import teams as nba_teams_static

    static_map = {t["id"]: t for t in nba_teams_static.get_teams()}
    conf = request.args.get("conference")
    df = _cached("standings_df", _fetch_standings_df, ttl=600)

    result = []
    for _, row in df.iterrows():
        conf_val = row["Conference"]
        if conf and conf_val.lower() != conf.lower():
            continue
        tid = int(row["TeamID"])
        result.append({
            "id": tid,
            "name": row["TeamName"],
            "city": row["TeamCity"],
            "abbrev": static_map.get(tid, {}).get("abbreviation", ""),
            "conference": conf_val,
            "division": row["Division"],
            "wins": int(row["WINS"]),
            "losses": int(row["LOSSES"]),
            "pct": round(float(row["WinPCT"]), 3),
        })

    result.sort(key=lambda x: x["pct"], reverse=True)
    for i, s in enumerate(result):
        s["rank"] = i + 1

    return jsonify({"data": result, "_meta": {"endpoint": "standings"}})


def _fetch_games(date_from: str, date_to: str) -> list:
    from nba_api.stats.endpoints import leaguegamefinder

    df = leaguegamefinder.LeagueGameFinder(
        date_from_nullable=date_from,
        date_to_nullable=date_to,
        season_nullable=CURRENT_SEASON,
        season_type_nullable="Regular Season",
        league_id_nullable="00",
    ).league_game_finder_results.get_data_frame()

    seen: set = set()
    game_list = []
    for _, row in df.iterrows():
        gid = row["GAME_ID"]
        if gid in seen:
            continue
        seen.add(gid)

        rows = df[df["GAME_ID"] == gid]
        if len(rows) < 2:
            continue

        r1, r2 = rows.iloc[0], rows.iloc[1]
        if "vs." in str(r1["MATCHUP"]):
            home, away = r1, r2
        else:
            home, away = r2, r1

        s1 = int(home["PTS"]) if home["PTS"] is not None else 0
        s2 = int(away["PTS"]) if away["PTS"] is not None else 0
        winner = home["TEAM_ABBREVIATION"] if s1 >= s2 else away["TEAM_ABBREVIATION"]

        game_list.append({
            "id": int(gid),
            "date": home["GAME_DATE"],
            "home": home["TEAM_ABBREVIATION"],
            "away": away["TEAM_ABBREVIATION"],
            "home_score": s1,
            "away_score": s2,
            "winner": winner,
        })

    return game_list[:20]


@app.route("/api/games")
def games():
    date_str = request.args.get("date")
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            date_from = date_to = d.strftime("%m/%d/%Y")
        except ValueError:
            date_from = date_to = date_str
    else:
        today = datetime.now()
        date_from = (today - timedelta(days=7)).strftime("%m/%d/%Y")
        date_to = today.strftime("%m/%d/%Y")

    cache_key = f"games_{date_from}_{date_to}"
    data = _cached(cache_key, lambda: _fetch_games(date_from, date_to), ttl=300)
    return jsonify({"data": data, "_meta": {"endpoint": "games"}})


def _fetch_last_night_analytics() -> dict:
    from nba_api.stats.endpoints import leaguegamefinder, leaguedashplayerstats

    def _games_for_date(date_str: str):
        return leaguegamefinder.LeagueGameFinder(
            date_from_nullable=date_str,
            date_to_nullable=date_str,
            season_nullable=CURRENT_SEASON,
            season_type_nullable="Regular Season",
            league_id_nullable="00",
        ).league_game_finder_results.get_data_frame()

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%m/%d/%Y")
    gf_df = _games_for_date(yesterday)
    used_date = yesterday

    if gf_df.empty:
        two_days_ago = (datetime.now() - timedelta(days=2)).strftime("%m/%d/%Y")
        gf_df = _games_for_date(two_days_ago)
        used_date = two_days_ago

    if gf_df.empty:
        return {"date": yesterday, "game_count": 0, "games": [], "top_performers": []}

    # Deduplicate into game summaries (two team rows per game_id)
    seen: set = set()
    games = []
    for gid in gf_df["GAME_ID"].unique():
        rows = gf_df[gf_df["GAME_ID"] == gid]
        if len(rows) < 2 or gid in seen:
            continue
        seen.add(gid)
        r1, r2 = rows.iloc[0], rows.iloc[1]
        home, away = (r1, r2) if "vs." in str(r1["MATCHUP"]) else (r2, r1)
        s1 = int(home["PTS"]) if home["PTS"] is not None else 0
        s2 = int(away["PTS"]) if away["PTS"] is not None else 0
        games.append({
            "id": int(gid),
            "date": home["GAME_DATE"],
            "home": home["TEAM_ABBREVIATION"],
            "away": away["TEAM_ABBREVIATION"],
            "home_score": s1,
            "away_score": s2,
            "winner": home["TEAM_ABBREVIATION"] if s1 >= s2 else away["TEAM_ABBREVIATION"],
        })

    # Player stats scoped to just that date (single-game totals)
    player_df = leaguedashplayerstats.LeagueDashPlayerStats(
        season=CURRENT_SEASON,
        per_mode_detailed="Totals",
        date_from_nullable=used_date,
        date_to_nullable=used_date,
    ).league_dash_player_stats.get_data_frame()

    top = player_df[player_df["PTS"] > 0].nlargest(15, "PTS")
    performers = []
    for _, row in top.iterrows():
        pts = int(row["PTS"])
        fga = int(row["FGA"])
        fta = int(row["FTA"])
        denom = 2 * (fga + 0.44 * fta)
        ts_pct = round(pts / denom * 100, 1) if denom > 0 else None
        performers.append({
            "name": row["PLAYER_NAME"],
            "team": row["TEAM_ABBREVIATION"],
            "pts": pts,
            "reb": int(row["REB"]),
            "ast": int(row["AST"]),
            "stl": int(row["STL"]),
            "blk": int(row["BLK"]),
            "tov": int(row["TOV"]),
            "fg_pct": round(float(row["FG_PCT"]), 3) if row["FG_PCT"] is not None else 0,
            "ts_pct": ts_pct,
            "min": str(row["MIN"]),
        })

    date_display = gf_df.iloc[0]["GAME_DATE"] if not gf_df.empty else used_date
    return {
        "date": date_display,
        "game_count": len(games),
        "games": games,
        "top_performers": performers,
    }


def _fetch_season_analytics() -> dict:
    from nba_api.stats.endpoints import leaguedashplayerstats, leaguedashteamstats

    # Advanced player stats (min 20 GP)
    player_df = leaguedashplayerstats.LeagueDashPlayerStats(
        season=CURRENT_SEASON,
        per_mode_detailed="PerGame",
        measure_type_detailed_defense="Advanced",
    ).league_dash_player_stats.get_data_frame()

    def _safe(val, scale=1, decimals=1):
        try:
            return round(float(val) * scale, decimals)
        except (TypeError, ValueError):
            return None

    players = [
        {
            "id": int(row["PLAYER_ID"]),
            "name": row["PLAYER_NAME"],
            "team": row["TEAM_ABBREVIATION"],
            "gp": int(row["GP"]),
            "ts_pct": _safe(row["TS_PCT"], 100),
            "efg_pct": _safe(row["EFG_PCT"], 100),
            "usg_pct": _safe(row["USG_PCT"], 100),
            "net_rating": _safe(row["NET_RATING"]),
            "pie": _safe(row["PIE"], 100),
            "ast_pct": _safe(row["AST_PCT"], 100),
            "reb_pct": _safe(row["REB_PCT"], 100),
        }
        for _, row in player_df.iterrows()
        if int(row["GP"]) >= 20
    ]

    # Advanced team stats
    team_df = leaguedashteamstats.LeagueDashTeamStats(
        season=CURRENT_SEASON,
        per_mode_detailed="PerGame",
        measure_type_detailed_defense="Advanced",
    ).league_dash_team_stats.get_data_frame()

    teams = [
        {
            "id": int(row["TEAM_ID"]),
            "name": row["TEAM_NAME"],
            "net_rating": _safe(row["NET_RATING"]),
            "off_rating": _safe(row["OFF_RATING"]),
            "def_rating": _safe(row["DEF_RATING"]),
            "pace": _safe(row["PACE"]),
            "ts_pct": _safe(row["TS_PCT"], 100),
            "efg_pct": _safe(row["EFG_PCT"], 100),
            "pie": _safe(row["PIE"], 100),
        }
        for _, row in team_df.iterrows()
    ]
    teams.sort(key=lambda x: (x["net_rating"] or 0), reverse=True)

    return {
        "season": CURRENT_SEASON,
        "top_players_ts": sorted(players, key=lambda x: (x["ts_pct"] or 0), reverse=True)[:20],
        "top_players_net": sorted(players, key=lambda x: (x["net_rating"] or 0), reverse=True)[:20],
        "top_players_usg": sorted(players, key=lambda x: (x["usg_pct"] or 0), reverse=True)[:20],
        "teams": teams,
    }


def _fetch_team_analytics(team_id: int) -> dict | None:
    from nba_api.stats.endpoints import leaguegamefinder, leaguedashplayerstats, leaguedashteamstats

    # Validate team exists
    all_teams = _get_teams()
    team_info = next((t for t in all_teams if t["id"] == team_id), None)
    if team_info is None:
        return None

    # Standings row for extended record fields
    standings_df = _cached("standings_df", _fetch_standings_df, ttl=600)
    team_row = standings_df[standings_df["TeamID"] == team_id]
    standing: dict = {}
    if not team_row.empty:
        r = team_row.iloc[0]
        standing = {
            "wins": int(r["WINS"]),
            "losses": int(r["LOSSES"]),
            "pct": round(float(r["WinPCT"]), 3),
            "conference_rank": int(r.get("PlayoffRank", 0)) if r.get("PlayoffRank") is not None else None,
            "home_record": str(r.get("HOME", "")),
            "away_record": str(r.get("ROAD", "")),
            "last_10": str(r.get("L10", "")),
            "streak": str(r.get("strCurrentStreak", "")),
        }

    # Recent games (last 10)
    recent_df = leaguegamefinder.LeagueGameFinder(
        team_id_nullable=team_id,
        season_nullable=CURRENT_SEASON,
        season_type_nullable="Regular Season",
    ).league_game_finder_results.get_data_frame()

    recent_games = [
        {
            "date": row["GAME_DATE"],
            "matchup": row["MATCHUP"],
            "wl": row["WL"],
            "pts": int(row["PTS"]) if row["PTS"] is not None else 0,
            "plus_minus": int(row["PLUS_MINUS"]) if row["PLUS_MINUS"] is not None else 0,
            "fg_pct": round(float(row["FG_PCT"]) * 100, 1) if row["FG_PCT"] is not None else 0,
            "fg3_pct": round(float(row["FG3_PCT"]) * 100, 1) if row["FG3_PCT"] is not None else 0,
        }
        for _, row in recent_df.head(10).iterrows()
    ]

    # Traditional per-game stats for team's players
    trad_df = leaguedashplayerstats.LeagueDashPlayerStats(
        season=CURRENT_SEASON,
        per_mode_detailed="PerGame",
        team_id_nullable=team_id,
    ).league_dash_player_stats.get_data_frame()

    # Advanced per-game stats for team's players
    adv_df = leaguedashplayerstats.LeagueDashPlayerStats(
        season=CURRENT_SEASON,
        per_mode_detailed="PerGame",
        measure_type_detailed_defense="Advanced",
        team_id_nullable=team_id,
    ).league_dash_player_stats.get_data_frame()

    adv_map: dict = {int(row["PLAYER_ID"]): row for _, row in adv_df.iterrows()}

    def _s(val, scale=1, decimals=1):
        try:
            return round(float(val) * scale, decimals)
        except (TypeError, ValueError):
            return None

    roster_stats = []
    for _, row in trad_df.iterrows():
        pid = int(row["PLAYER_ID"])
        adv = adv_map.get(pid)
        roster_stats.append({
            "id": pid,
            "name": row["PLAYER_NAME"],
            "gp": int(row["GP"]),
            "min": _s(row["MIN"]),
            "ppg": _s(row["PTS"]),
            "rpg": _s(row["REB"]),
            "apg": _s(row["AST"]),
            "fg_pct": _s(row["FG_PCT"], 100),
            "fg3_pct": _s(row["FG3_PCT"], 100),
            "ft_pct": _s(row["FT_PCT"], 100),
            "ts_pct": _s(adv.get("TS_PCT"), 100) if adv is not None else None,
            "usg_pct": _s(adv.get("USG_PCT"), 100) if adv is not None else None,
            "net_rating": _s(adv.get("NET_RATING")) if adv is not None else None,
        })
    roster_stats.sort(key=lambda x: (x["ppg"] or 0), reverse=True)

    # Team-level advanced stats (fetch all, filter to this team)
    team_adv_df = leaguedashteamstats.LeagueDashTeamStats(
        season=CURRENT_SEASON,
        per_mode_detailed="PerGame",
        measure_type_detailed_defense="Advanced",
    ).league_dash_team_stats.get_data_frame()

    team_adv_row = team_adv_df[team_adv_df["TEAM_ID"] == team_id]
    team_advanced: dict = {}
    if not team_adv_row.empty:
        r = team_adv_row.iloc[0]
        team_advanced = {
            "net_rating": _s(r["NET_RATING"]),
            "off_rating": _s(r["OFF_RATING"]),
            "def_rating": _s(r["DEF_RATING"]),
            "pace": _s(r["PACE"]),
            "ts_pct": _s(r["TS_PCT"], 100),
            "efg_pct": _s(r["EFG_PCT"], 100),
            "pie": _s(r["PIE"], 100),
        }

    return {
        "team": team_info,
        "standing": standing,
        "team_advanced": team_advanced,
        "recent_games": recent_games,
        "roster_stats": roster_stats,
    }


def _fetch_lakers_analytics() -> dict:
    return _fetch_team_analytics(LAKERS_TEAM_ID)


def _fetch_game_detail(game_id: int) -> dict | None:
    from nba_api.stats.endpoints import boxscoretraditionalv3

    # NBA game IDs are 10-char zero-padded strings (e.g. "0022500851")
    nba_game_id = f"{game_id:010d}"
    bs = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=nba_game_id, timeout=60)
    team_df = bs.team_stats.get_data_frame()
    player_df = bs.player_stats.get_data_frame()

    if team_df.empty:
        return None

    teams_in_game = {
        row["teamTricode"]: {
            "id": int(row["teamId"]),
            "name": f"{row['teamCity']} {row['teamName']}",
            "abbrev": row["teamTricode"],
        }
        for _, row in team_df.iterrows()
    }

    box_score: dict = {}
    for _, row in player_df.iterrows():
        abbrev = row["teamTricode"]
        if abbrev not in box_score:
            box_score[abbrev] = []
        box_score[abbrev].append({
            "name": f"{row['firstName']} {row['familyName']}",
            "pts": int(row["points"]) if row["points"] is not None else 0,
            "reb": int(row["reboundsTotal"]) if row["reboundsTotal"] is not None else 0,
            "ast": int(row["assists"]) if row["assists"] is not None else 0,
        })

    team_list = list(teams_in_game.values())
    home = team_list[0] if team_list else {}
    away = team_list[1] if len(team_list) > 1 else {}

    def get_score(abbrev: str) -> int:
        rows = team_df[team_df["teamTricode"] == abbrev]
        if rows.empty:
            return 0
        v = rows.iloc[0]["points"]
        return int(v) if v is not None else 0

    return {
        "id": game_id,
        "home": home,
        "away": away,
        "home_score": get_score(home.get("abbrev", "")),
        "away_score": get_score(away.get("abbrev", "")),
        "box_score": box_score,
    }


@app.route("/api/games/<int:game_id>")
def game_detail(game_id):
    try:
        data = _cached(
            f"game_{game_id}",
            lambda: _fetch_game_detail(game_id),
            ttl=3600,
        )
    except Exception as e:
        return jsonify({"error": f"NBA API error: {type(e).__name__}"}), 503
    if data is None:
        return jsonify({"error": "Game not found"}), 404
    return jsonify({"data": data, "_meta": {"endpoint": "game_detail"}})


@app.route("/api/analytics/last-night")
def last_night_analytics():
    data = _cached("last_night", _fetch_last_night_analytics, ttl=3600)
    return jsonify({"data": data, "_meta": {"endpoint": "last_night"}})


@app.route("/api/analytics/season")
def season_analytics():
    data = _cached("season_analytics", _fetch_season_analytics, ttl=3600)
    return jsonify({"data": data, "_meta": {"endpoint": "season_analytics"}})


@app.route("/api/analytics/team/<int:team_id>")
def team_dashboard(team_id):
    data = _cached(
        f"team_dashboard_{team_id}",
        lambda: _fetch_team_analytics(team_id),
        ttl=600,
    )
    if data is None:
        return jsonify({"error": "Team not found"}), 404
    return jsonify({"data": data, "_meta": {"endpoint": "team_dashboard", "team_id": team_id}})


@app.route("/api/analytics/lakers")
def lakers_analytics():
    data = _cached("lakers_dashboard", _fetch_lakers_analytics, ttl=600)
    return jsonify({"data": data, "_meta": {"endpoint": "lakers_dashboard"}})


@app.route("/")
def index():
    return app.send_static_file("index.html")


if __name__ == "__main__":
    print("🏀 NBA API Explorer backend running on http://localhost:5000")
    app.run(debug=True, port=5000)
