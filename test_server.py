"""
Integration tests for every node defined in index.html's FALLBACK_MAP.
Tests make real nba-api calls — requires internet access and may take ~60s.

Known stable IDs used:
  Nikola Jokic  player_id = 203999  (Denver Nuggets)
  Denver Nuggets team_id  = 1610612743
"""

import json
import pytest
from server import app


# ── Helpers ───────────────────────────────────────────────────────────────────

def json_body(response):
    return json.loads(response.data)


@pytest.fixture(scope="session")
def recent_game_id(client):
    """Fetch a real game ID from /api/games for use in game_detail tests."""
    body = json_body(client.get("/api/games"))
    games = body.get("data", [])
    return games[0]["id"] if games else None


# ── / (index.html) ────────────────────────────────────────────────────────────

class TestIndex:
    def test_index_returns_200(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_index_content_type_is_html(self, client):
        r = client.get("/")
        assert "text/html" in r.content_type

    def test_index_contains_vue_app_mount_point(self, client):
        r = client.get("/")
        assert b'id="app"' in r.data


# ── /api/map ──────────────────────────────────────────────────────────────────

EXPECTED_NODES = {
    "root", "teams", "players", "standings", "games",
    "team_detail", "player_detail", "game_log", "game_detail",
    "analytics", "last_night", "season_analytics", "team_dashboard", "lakers_dashboard",
}


class TestApiMap:
    def test_returns_200(self, client):
        r = client.get("/api/map")
        assert r.status_code == 200

    def test_content_type_json(self, client):
        r = client.get("/api/map")
        assert r.content_type == "application/json"

    def test_contains_all_nodes(self, client):
        body = json_body(client.get("/api/map"))
        assert EXPECTED_NODES == set(body.keys())

    def test_each_node_has_label(self, client):
        body = json_body(client.get("/api/map"))
        for key, node in body.items():
            assert "label" in node, f"node '{key}' missing 'label'"

    def test_endpoint_nodes_have_endpoint_key(self, client):
        body = json_body(client.get("/api/map"))
        nodes_with_endpoints = {k for k, v in body.items() if v.get("endpoint")}
        assert "root" not in nodes_with_endpoints
        assert "analytics" not in nodes_with_endpoints  # hub node, no endpoint
        assert EXPECTED_NODES - {"root", "analytics"} == nodes_with_endpoints

    def test_analytics_children_include_team_dashboard(self, client):
        body = json_body(client.get("/api/map"))
        assert "team_dashboard" in body["analytics"]["children"]


# ── node: teams  →  GET /api/teams ───────────────────────────────────────────

class TestTeams:
    def test_returns_200(self, client):
        r = client.get("/api/teams")
        assert r.status_code == 200

    def test_response_has_data_and_meta(self, client):
        body = json_body(client.get("/api/teams"))
        assert "data" in body
        assert "_meta" in body

    def test_data_is_list(self, client):
        body = json_body(client.get("/api/teams"))
        assert isinstance(body["data"], list)

    def test_returns_all_30_teams(self, client):
        body = json_body(client.get("/api/teams"))
        assert len(body["data"]) == 30

    def test_meta_count_matches_data_length(self, client):
        body = json_body(client.get("/api/teams"))
        assert body["_meta"]["count"] == len(body["data"])

    def test_team_shape(self, client):
        body = json_body(client.get("/api/teams"))
        team = body["data"][0]
        for field in ("id", "name", "city", "abbrev", "conference", "division"):
            assert field in team, f"team missing field '{field}'"

    def test_meta_endpoint_label(self, client):
        body = json_body(client.get("/api/teams"))
        assert body["_meta"]["endpoint"] == "teams"


# ── node: team_detail  →  GET /api/teams/<id> ────────────────────────────────

NUGGETS_ID = 1610612743


class TestTeamDetail:
    def test_returns_200_for_valid_id(self, client):
        r = client.get(f"/api/teams/{NUGGETS_ID}")
        assert r.status_code == 200

    def test_response_has_data_and_meta(self, client):
        body = json_body(client.get(f"/api/teams/{NUGGETS_ID}"))
        assert "data" in body
        assert "_meta" in body

    def test_data_contains_team_fields(self, client):
        body = json_body(client.get(f"/api/teams/{NUGGETS_ID}"))
        for field in ("id", "name", "city", "abbrev", "conference", "division"):
            assert field in body["data"]

    def test_correct_team_returned(self, client):
        body = json_body(client.get(f"/api/teams/{NUGGETS_ID}"))
        assert body["data"]["abbrev"] == "DEN"

    def test_data_contains_roster(self, client):
        body = json_body(client.get(f"/api/teams/{NUGGETS_ID}"))
        assert "roster" in body["data"]
        assert isinstance(body["data"]["roster"], list)

    def test_roster_is_non_empty(self, client):
        body = json_body(client.get(f"/api/teams/{NUGGETS_ID}"))
        assert len(body["data"]["roster"]) > 0

    def test_roster_contains_jokic(self, client):
        body = json_body(client.get(f"/api/teams/{NUGGETS_ID}"))
        ids = [p["id"] for p in body["data"]["roster"]]
        assert 203999 in ids

    def test_roster_player_shape(self, client):
        body = json_body(client.get(f"/api/teams/{NUGGETS_ID}"))
        player = body["data"]["roster"][0]
        for field in ("id", "name", "pos", "num"):
            assert field in player

    def test_meta_endpoint_label(self, client):
        body = json_body(client.get(f"/api/teams/{NUGGETS_ID}"))
        assert body["_meta"]["endpoint"] == "team_detail"

    def test_returns_404_for_invalid_id(self, client):
        r = client.get("/api/teams/9999999")
        assert r.status_code == 404


# ── node: players  →  GET /api/players ───────────────────────────────────────

class TestPlayers:
    def test_returns_200(self, client):
        r = client.get("/api/players")
        assert r.status_code == 200

    def test_response_has_data_and_meta(self, client):
        body = json_body(client.get("/api/players"))
        assert "data" in body
        assert "_meta" in body

    def test_data_is_list(self, client):
        body = json_body(client.get("/api/players"))
        assert isinstance(body["data"], list)

    def test_returns_many_players(self, client):
        body = json_body(client.get("/api/players"))
        assert len(body["data"]) > 100

    def test_meta_count_matches_data_length(self, client):
        body = json_body(client.get("/api/players"))
        assert body["_meta"]["count"] == len(body["data"])

    def test_player_shape(self, client):
        body = json_body(client.get("/api/players"))
        player = body["data"][0]
        for field in ("id", "name", "team_id", "ppg", "rpg", "apg"):
            assert field in player

    def test_filter_by_team_id(self, client):
        body = json_body(client.get(f"/api/players?team_id={NUGGETS_ID}"))
        assert all(p["team_id"] == NUGGETS_ID for p in body["data"])

    def test_filter_by_team_id_returns_subset(self, client):
        all_body = json_body(client.get("/api/players"))
        filtered_body = json_body(client.get(f"/api/players?team_id={NUGGETS_ID}"))
        assert 0 < len(filtered_body["data"]) < len(all_body["data"])

    def test_meta_endpoint_label(self, client):
        body = json_body(client.get("/api/players"))
        assert body["_meta"]["endpoint"] == "players"


# ── node: player_detail  →  GET /api/players/<id> ────────────────────────────

JOKIC_ID = 203999


class TestPlayerDetail:
    def test_returns_200_for_valid_id(self, client):
        r = client.get(f"/api/players/{JOKIC_ID}")
        assert r.status_code == 200

    def test_response_has_data_and_meta(self, client):
        body = json_body(client.get(f"/api/players/{JOKIC_ID}"))
        assert "data" in body
        assert "_meta" in body

    def test_data_is_correct_player(self, client):
        body = json_body(client.get(f"/api/players/{JOKIC_ID}"))
        assert body["data"]["id"] == JOKIC_ID
        assert "Joki" in body["data"]["name"]

    def test_player_shape(self, client):
        body = json_body(client.get(f"/api/players/{JOKIC_ID}"))
        for field in ("id", "name", "team_id", "pos", "ppg", "rpg", "apg"):
            assert field in body["data"]

    def test_meta_endpoint_label(self, client):
        body = json_body(client.get(f"/api/players/{JOKIC_ID}"))
        assert body["_meta"]["endpoint"] == "player_detail"


# ── node: game_log  →  GET /api/players/<id>/gamelog ─────────────────────────

class TestGameLog:
    def test_returns_200(self, client):
        r = client.get(f"/api/players/{JOKIC_ID}/gamelog")
        assert r.status_code == 200

    def test_response_has_data_and_meta(self, client):
        body = json_body(client.get(f"/api/players/{JOKIC_ID}/gamelog"))
        assert "data" in body
        assert "_meta" in body

    def test_default_n_is_10(self, client):
        body = json_body(client.get(f"/api/players/{JOKIC_ID}/gamelog"))
        assert len(body["data"]) == 10

    def test_custom_n_param(self, client):
        body = json_body(client.get(f"/api/players/{JOKIC_ID}/gamelog?n=5"))
        assert len(body["data"]) == 5

    def test_game_log_entry_shape(self, client):
        body = json_body(client.get(f"/api/players/{JOKIC_ID}/gamelog"))
        entry = body["data"][0]
        for field in ("game", "date", "pts", "reb", "ast", "fg_pct", "min"):
            assert field in entry, f"game log entry missing '{field}'"

    def test_meta_contains_player_id(self, client):
        body = json_body(client.get(f"/api/players/{JOKIC_ID}/gamelog"))
        assert body["_meta"]["player_id"] == JOKIC_ID

    def test_meta_endpoint_label(self, client):
        body = json_body(client.get(f"/api/players/{JOKIC_ID}/gamelog"))
        assert body["_meta"]["endpoint"] == "game_log"


# ── node: standings  →  GET /api/standings ───────────────────────────────────

class TestStandings:
    def test_returns_200(self, client):
        r = client.get("/api/standings")
        assert r.status_code == 200

    def test_response_has_data_and_meta(self, client):
        body = json_body(client.get("/api/standings"))
        assert "data" in body
        assert "_meta" in body

    def test_data_is_list_of_all_teams(self, client):
        body = json_body(client.get("/api/standings"))
        assert len(body["data"]) == 30

    def test_standings_entry_shape(self, client):
        body = json_body(client.get("/api/standings"))
        entry = body["data"][0]
        for field in ("id", "name", "wins", "losses", "pct", "rank"):
            assert field in entry, f"standings entry missing '{field}'"

    def test_sorted_by_pct_descending(self, client):
        body = json_body(client.get("/api/standings"))
        pcts = [s["pct"] for s in body["data"]]
        assert pcts == sorted(pcts, reverse=True)

    def test_rank_field_is_sequential(self, client):
        body = json_body(client.get("/api/standings"))
        ranks = [s["rank"] for s in body["data"]]
        assert ranks == list(range(1, 31))

    def test_filter_by_conference_east(self, client):
        body = json_body(client.get("/api/standings?conference=East"))
        assert all(s["conference"] == "East" for s in body["data"])
        assert len(body["data"]) == 15

    def test_filter_by_conference_west(self, client):
        body = json_body(client.get("/api/standings?conference=West"))
        assert all(s["conference"] == "West" for s in body["data"])
        assert len(body["data"]) == 15

    def test_filter_is_case_insensitive(self, client):
        body_lower = json_body(client.get("/api/standings?conference=east"))
        body_upper = json_body(client.get("/api/standings?conference=East"))
        assert len(body_lower["data"]) == len(body_upper["data"])

    def test_meta_endpoint_label(self, client):
        body = json_body(client.get("/api/standings"))
        assert body["_meta"]["endpoint"] == "standings"


# ── node: games  →  GET /api/games ──────────────────────────────────────────

class TestGames:
    def test_returns_200(self, client):
        r = client.get("/api/games")
        assert r.status_code == 200

    def test_response_has_data_and_meta(self, client):
        body = json_body(client.get("/api/games"))
        assert "data" in body
        assert "_meta" in body

    def test_data_is_list(self, client):
        body = json_body(client.get("/api/games"))
        assert isinstance(body["data"], list)

    def test_returns_recent_games(self, client):
        body = json_body(client.get("/api/games"))
        assert len(body["data"]) > 0

    def test_game_shape(self, client):
        body = json_body(client.get("/api/games"))
        game = body["data"][0]
        for field in ("id", "date", "home", "away", "home_score", "away_score", "winner"):
            assert field in game, f"game missing field '{field}'"

    def test_winner_is_home_or_away(self, client):
        body = json_body(client.get("/api/games"))
        for game in body["data"]:
            assert game["winner"] in (game["home"], game["away"])

    def test_meta_endpoint_label(self, client):
        body = json_body(client.get("/api/games"))
        assert body["_meta"]["endpoint"] == "games"

    def test_accepts_date_query_param(self, client):
        r = client.get("/api/games?date=2026-02-25")
        assert r.status_code == 200


# ── node: game_detail  →  GET /api/games/<id> ────────────────────────────────

@pytest.fixture(scope="session")
def game_detail_body(client, recent_game_id):
    """Fetch game detail once and share across all TestGameDetail tests."""
    if not recent_game_id:
        return None
    r = client.get(f"/api/games/{recent_game_id}")
    if r.status_code not in (200, 503):
        return None
    return json_body(r)


class TestGameDetail:
    def test_returns_200(self, client, recent_game_id, game_detail_body):
        if not recent_game_id:
            pytest.skip("No recent games available")
        r = client.get(f"/api/games/{recent_game_id}")
        assert r.status_code in (200, 503)  # 503 = NBA API temporarily unavailable

    def test_response_has_data_or_error(self, client, game_detail_body):
        if game_detail_body is None:
            pytest.skip("No recent games or NBA API unavailable")
        assert "data" in game_detail_body or "error" in game_detail_body

    def test_response_has_data_and_meta(self, client, game_detail_body):
        if game_detail_body is None or "error" in game_detail_body:
            pytest.skip("No recent games or NBA API unavailable")
        assert "data" in game_detail_body
        assert "_meta" in game_detail_body

    def test_data_contains_id(self, client, recent_game_id, game_detail_body):
        if game_detail_body is None or "error" in game_detail_body:
            pytest.skip("No recent games or NBA API unavailable")
        assert game_detail_body["data"]["id"] == recent_game_id

    def test_data_shape(self, client, game_detail_body):
        if game_detail_body is None or "error" in game_detail_body:
            pytest.skip("No recent games or NBA API unavailable")
        for field in ("id", "home", "away", "home_score", "away_score", "box_score"):
            assert field in game_detail_body["data"], f"game_detail missing field '{field}'"

    def test_home_and_away_are_team_objects(self, client, game_detail_body):
        if game_detail_body is None or "error" in game_detail_body:
            pytest.skip("No recent games or NBA API unavailable")
        for side in ("home", "away"):
            team = game_detail_body["data"][side]
            for field in ("id", "name", "abbrev"):
                assert field in team, f"team '{side}' missing field '{field}'"

    def test_box_score_has_two_teams(self, client, game_detail_body):
        if game_detail_body is None or "error" in game_detail_body:
            pytest.skip("No recent games or NBA API unavailable")
        assert len(game_detail_body["data"]["box_score"]) == 2

    def test_box_score_entries_shape(self, client, game_detail_body):
        if game_detail_body is None or "error" in game_detail_body:
            pytest.skip("No recent games or NBA API unavailable")
        for abbrev, roster in game_detail_body["data"]["box_score"].items():
            assert isinstance(roster, list)
            assert len(roster) > 0
            for entry in roster:
                for field in ("name", "pts", "reb", "ast"):
                    assert field in entry

    def test_meta_endpoint_label(self, client, game_detail_body):
        if game_detail_body is None or "error" in game_detail_body:
            pytest.skip("No recent games or NBA API unavailable")
        assert game_detail_body["_meta"]["endpoint"] == "game_detail"


# ── node: last_night  →  GET /api/analytics/last-night ───────────────────────

class TestLastNightAnalytics:
    def test_returns_200(self, client):
        r = client.get("/api/analytics/last-night")
        assert r.status_code == 200

    def test_response_has_data_and_meta(self, client):
        body = json_body(client.get("/api/analytics/last-night"))
        assert "data" in body
        assert "_meta" in body

    def test_meta_endpoint_label(self, client):
        body = json_body(client.get("/api/analytics/last-night"))
        assert body["_meta"]["endpoint"] == "last_night"

    def test_data_shape(self, client):
        body = json_body(client.get("/api/analytics/last-night"))
        data = body["data"]
        for field in ("date", "game_count", "games", "top_performers"):
            assert field in data, f"last_night data missing '{field}'"

    def test_game_count_matches_games_list(self, client):
        body = json_body(client.get("/api/analytics/last-night"))
        data = body["data"]
        assert data["game_count"] == len(data["games"])

    def test_games_is_list(self, client):
        body = json_body(client.get("/api/analytics/last-night"))
        assert isinstance(body["data"]["games"], list)

    def test_top_performers_is_list(self, client):
        body = json_body(client.get("/api/analytics/last-night"))
        assert isinstance(body["data"]["top_performers"], list)

    def test_game_shape_when_games_present(self, client):
        body = json_body(client.get("/api/analytics/last-night"))
        games = body["data"]["games"]
        if not games:
            pytest.skip("No games found for last night or prior night")
        game = games[0]
        for field in ("id", "date", "home", "away", "home_score", "away_score", "winner"):
            assert field in game, f"game missing field '{field}'"

    def test_top_performer_shape(self, client):
        body = json_body(client.get("/api/analytics/last-night"))
        performers = body["data"]["top_performers"]
        if not performers:
            pytest.skip("No top performers found")
        p = performers[0]
        for field in ("name", "team", "pts", "reb", "ast", "fg_pct", "min"):
            assert field in p, f"top_performer missing field '{field}'"

    def test_top_performers_sorted_by_pts(self, client):
        body = json_body(client.get("/api/analytics/last-night"))
        performers = body["data"]["top_performers"]
        if len(performers) < 2:
            pytest.skip("Not enough performers to check ordering")
        pts = [p["pts"] for p in performers]
        assert pts == sorted(pts, reverse=True)


# ── node: season_analytics  →  GET /api/analytics/season ─────────────────────

class TestSeasonAnalytics:
    def test_returns_200(self, client):
        r = client.get("/api/analytics/season")
        assert r.status_code == 200

    def test_response_has_data_and_meta(self, client):
        body = json_body(client.get("/api/analytics/season"))
        assert "data" in body
        assert "_meta" in body

    def test_meta_endpoint_label(self, client):
        body = json_body(client.get("/api/analytics/season"))
        assert body["_meta"]["endpoint"] == "season_analytics"

    def test_data_shape(self, client):
        body = json_body(client.get("/api/analytics/season"))
        data = body["data"]
        for field in ("season", "top_players_ts", "top_players_net", "top_players_usg", "teams"):
            assert field in data, f"season_analytics data missing '{field}'"

    def test_season_matches_current(self, client):
        body = json_body(client.get("/api/analytics/season"))
        from server import CURRENT_SEASON
        assert body["data"]["season"] == CURRENT_SEASON

    def test_top_players_ts_is_list(self, client):
        body = json_body(client.get("/api/analytics/season"))
        assert isinstance(body["data"]["top_players_ts"], list)

    def test_teams_is_list_of_all_30(self, client):
        body = json_body(client.get("/api/analytics/season"))
        assert len(body["data"]["teams"]) == 30

    def test_teams_sorted_by_net_rating(self, client):
        body = json_body(client.get("/api/analytics/season"))
        ratings = [t["net_rating"] for t in body["data"]["teams"] if t["net_rating"] is not None]
        assert ratings == sorted(ratings, reverse=True)

    def test_player_advanced_shape(self, client):
        body = json_body(client.get("/api/analytics/season"))
        players = body["data"]["top_players_ts"]
        if not players:
            pytest.skip("No qualified players returned")
        p = players[0]
        for field in ("id", "name", "team", "gp", "ts_pct", "efg_pct", "usg_pct", "net_rating"):
            assert field in p, f"player advanced entry missing '{field}'"

    def test_team_advanced_shape(self, client):
        body = json_body(client.get("/api/analytics/season"))
        team = body["data"]["teams"][0]
        for field in ("id", "name", "net_rating", "off_rating", "def_rating", "pace"):
            assert field in team, f"team advanced entry missing '{field}'"

    def test_top_players_sorted_by_ts_pct(self, client):
        body = json_body(client.get("/api/analytics/season"))
        players = body["data"]["top_players_ts"]
        if len(players) < 2:
            pytest.skip("Not enough players")
        ts_vals = [p["ts_pct"] for p in players if p["ts_pct"] is not None]
        assert ts_vals == sorted(ts_vals, reverse=True)

    def test_top_players_net_sorted_by_net_rating(self, client):
        body = json_body(client.get("/api/analytics/season"))
        players = body["data"]["top_players_net"]
        if len(players) < 2:
            pytest.skip("Not enough players")
        ratings = [p["net_rating"] for p in players if p["net_rating"] is not None]
        assert ratings == sorted(ratings, reverse=True)

    def test_min_gp_filter_applied(self, client):
        """Every returned player should have played at least 20 games."""
        body = json_body(client.get("/api/analytics/season"))
        for bucket in ("top_players_ts", "top_players_net", "top_players_usg"):
            for p in body["data"][bucket]:
                assert p["gp"] >= 20, f"Player {p['name']} has only {p['gp']} GP"


# ── node: lakers_dashboard  →  GET /api/analytics/lakers ─────────────────────

LAKERS_TEAM_ID = 1610612747


class TestLakersDashboard:
    def test_returns_200(self, client):
        r = client.get("/api/analytics/lakers")
        assert r.status_code == 200

    def test_response_has_data_and_meta(self, client):
        body = json_body(client.get("/api/analytics/lakers"))
        assert "data" in body
        assert "_meta" in body

    def test_meta_endpoint_label(self, client):
        body = json_body(client.get("/api/analytics/lakers"))
        assert body["_meta"]["endpoint"] == "lakers_dashboard"

    def test_data_shape(self, client):
        body = json_body(client.get("/api/analytics/lakers"))
        data = body["data"]
        for field in ("team", "standing", "team_advanced", "recent_games", "roster_stats"):
            assert field in data, f"lakers_dashboard data missing '{field}'"

    def test_team_is_lakers(self, client):
        body = json_body(client.get("/api/analytics/lakers"))
        team = body["data"]["team"]
        assert team.get("id") == LAKERS_TEAM_ID or team.get("abbrev") == "LAL"

    def test_standing_has_wins_and_losses(self, client):
        body = json_body(client.get("/api/analytics/lakers"))
        standing = body["data"]["standing"]
        assert "wins" in standing
        assert "losses" in standing
        assert isinstance(standing["wins"], int)
        assert isinstance(standing["losses"], int)

    def test_standing_has_record_fields(self, client):
        body = json_body(client.get("/api/analytics/lakers"))
        standing = body["data"]["standing"]
        for field in ("home_record", "away_record", "last_10", "streak"):
            assert field in standing, f"standing missing '{field}'"

    def test_recent_games_is_list(self, client):
        body = json_body(client.get("/api/analytics/lakers"))
        assert isinstance(body["data"]["recent_games"], list)

    def test_recent_games_capped_at_10(self, client):
        body = json_body(client.get("/api/analytics/lakers"))
        assert len(body["data"]["recent_games"]) <= 10

    def test_recent_game_shape(self, client):
        body = json_body(client.get("/api/analytics/lakers"))
        games = body["data"]["recent_games"]
        if not games:
            pytest.skip("No recent Lakers games found")
        game = games[0]
        for field in ("date", "matchup", "wl", "pts", "plus_minus"):
            assert field in game, f"recent_game missing '{field}'"

    def test_roster_stats_is_list(self, client):
        body = json_body(client.get("/api/analytics/lakers"))
        assert isinstance(body["data"]["roster_stats"], list)

    def test_roster_all_lakers(self, client):
        """Every player in roster_stats should be on the Lakers."""
        from server import _get_players
        body = json_body(client.get("/api/analytics/lakers"))
        # All players returned should only be Lakers players
        ids = {p["id"] for p in body["data"]["roster_stats"]}
        all_players = _get_players()
        lakers_ids = {p["id"] for p in all_players if p["team_id"] == LAKERS_TEAM_ID}
        assert ids.issubset(lakers_ids)

    def test_roster_sorted_by_ppg(self, client):
        body = json_body(client.get("/api/analytics/lakers"))
        roster = body["data"]["roster_stats"]
        if len(roster) < 2:
            pytest.skip("Not enough roster entries")
        ppgs = [p["ppg"] for p in roster if p.get("ppg") is not None]
        assert ppgs == sorted(ppgs, reverse=True)

    def test_roster_player_shape(self, client):
        body = json_body(client.get("/api/analytics/lakers"))
        roster = body["data"]["roster_stats"]
        if not roster:
            pytest.skip("No roster stats returned")
        p = roster[0]
        for field in ("id", "name", "gp", "ppg", "rpg", "apg", "fg_pct", "ts_pct", "usg_pct"):
            assert field in p, f"roster_stat missing '{field}'"

    def test_team_advanced_shape(self, client):
        body = json_body(client.get("/api/analytics/lakers"))
        adv = body["data"]["team_advanced"]
        for field in ("net_rating", "off_rating", "def_rating", "pace", "ts_pct", "efg_pct"):
            assert field in adv, f"team_advanced missing '{field}'"


# ── node: team_dashboard  →  GET /api/analytics/team/<id> ────────────────────

NUGGETS_ID = 1610612743


class TestTeamDashboard:
    def test_returns_200_for_nuggets(self, client):
        r = client.get(f"/api/analytics/team/{NUGGETS_ID}")
        assert r.status_code == 200

    def test_returns_404_for_invalid_id(self, client):
        r = client.get("/api/analytics/team/9999999")
        assert r.status_code == 404

    def test_response_has_data_and_meta(self, client):
        body = json_body(client.get(f"/api/analytics/team/{NUGGETS_ID}"))
        assert "data" in body and "_meta" in body

    def test_meta_endpoint_label(self, client):
        body = json_body(client.get(f"/api/analytics/team/{NUGGETS_ID}"))
        assert body["_meta"]["endpoint"] == "team_dashboard"

    def test_meta_team_id(self, client):
        body = json_body(client.get(f"/api/analytics/team/{NUGGETS_ID}"))
        assert body["_meta"]["team_id"] == NUGGETS_ID

    def test_data_shape(self, client):
        body = json_body(client.get(f"/api/analytics/team/{NUGGETS_ID}"))
        for field in ("team", "standing", "team_advanced", "recent_games", "roster_stats"):
            assert field in body["data"]

    def test_correct_team_returned(self, client):
        body = json_body(client.get(f"/api/analytics/team/{NUGGETS_ID}"))
        assert body["data"]["team"]["id"] == NUGGETS_ID

    def test_standing_fields(self, client):
        body = json_body(client.get(f"/api/analytics/team/{NUGGETS_ID}"))
        standing = body["data"]["standing"]
        for field in ("wins", "losses", "pct", "home_record", "away_record", "last_10", "streak"):
            assert field in standing

    def test_roster_contains_jokic(self, client):
        body = json_body(client.get(f"/api/analytics/team/{NUGGETS_ID}"))
        ids = [p["id"] for p in body["data"]["roster_stats"]]
        assert 203999 in ids

    def test_roster_sorted_by_ppg(self, client):
        body = json_body(client.get(f"/api/analytics/team/{NUGGETS_ID}"))
        roster = body["data"]["roster_stats"]
        if len(roster) < 2:
            pytest.skip("Not enough roster entries")
        ppgs = [p["ppg"] for p in roster if p.get("ppg") is not None]
        assert ppgs == sorted(ppgs, reverse=True)

    def test_roster_player_shape(self, client):
        body = json_body(client.get(f"/api/analytics/team/{NUGGETS_ID}"))
        p = body["data"]["roster_stats"][0]
        for field in ("id", "name", "gp", "ppg", "rpg", "apg", "fg_pct", "ts_pct", "usg_pct"):
            assert field in p

    def test_team_advanced_shape(self, client):
        body = json_body(client.get(f"/api/analytics/team/{NUGGETS_ID}"))
        adv = body["data"]["team_advanced"]
        for field in ("net_rating", "off_rating", "def_rating", "pace", "ts_pct"):
            assert field in adv

    def test_recent_games_capped_at_10(self, client):
        body = json_body(client.get(f"/api/analytics/team/{NUGGETS_ID}"))
        assert len(body["data"]["recent_games"]) <= 10

    def test_lakers_and_generic_return_same_shape(self, client):
        """The Lakers alias and the generic endpoint return structurally identical responses."""
        generic = json_body(client.get(f"/api/analytics/team/{LAKERS_TEAM_ID}"))
        alias = json_body(client.get("/api/analytics/lakers"))
        assert set(generic["data"].keys()) == set(alias["data"].keys())
