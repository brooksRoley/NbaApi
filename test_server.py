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


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


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

EXPECTED_NODES = {"root", "teams", "players", "standings", "games",
                  "team_detail", "player_detail", "game_log", "game_detail"}


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
        assert EXPECTED_NODES - {"root"} == nodes_with_endpoints


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
