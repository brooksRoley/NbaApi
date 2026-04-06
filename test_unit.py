"""
Unit tests for the NBA API Explorer Flask backend.

These tests mock all nba_api calls so they run without internet access
and complete in milliseconds.  They focus on:
  - Route status codes and response shapes
  - Filter / derived-field logic
  - Cache TTL behaviour
  - Error handling (404, bad input, upstream failure)

The fixture is named `unit_client` (not `client`) to avoid a scope conflict
with conftest.py's session-scoped `client` used by the `warm_cache` autouse
fixture — pytest does not allow a session fixture to depend on a function-
scoped one.
"""

import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import server
from server import app, _cache, _current_nba_season


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def unit_client():
    """Function-scoped test client; independent of conftest's session client."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clear_cache():
    """Each unit test gets a cold cache and leaves one too."""
    _cache.clear()
    yield
    _cache.clear()


# ── Minimal sample data helpers ───────────────────────────────────────────────

TEAMS_STATIC = [
    {"id": 1610612747, "abbreviation": "LAL"},
    {"id": 1610612743, "abbreviation": "DEN"},
]

STANDINGS_DF = pd.DataFrame([
    {
        "TeamID": 1610612747, "TeamName": "Lakers", "TeamCity": "Los Angeles",
        "Conference": "West", "Division": "Pacific",
        "WINS": 45, "LOSSES": 30, "WinPCT": 0.600,
        "PlayoffRank": 3, "HOME": "25-12", "ROAD": "20-18",
        "L10": "7-3", "strCurrentStreak": "W2",
    },
    {
        "TeamID": 1610612743, "TeamName": "Nuggets", "TeamCity": "Denver",
        "Conference": "West", "Division": "Northwest",
        "WINS": 50, "LOSSES": 25, "WinPCT": 0.667,
        "PlayoffRank": 1, "HOME": "28-8", "ROAD": "22-17",
        "L10": "8-2", "strCurrentStreak": "W4",
    },
])

PLAYERS_DF = pd.DataFrame([
    {
        "PLAYER_ID": 203999, "PLAYER_NAME": "Nikola Jokic",
        "TEAM_ID": 1610612743, "TEAM_ABBREVIATION": "DEN",
        "PTS": 29.0, "REB": 13.0, "AST": 10.0, "GP": 68,
    },
    {
        "PLAYER_ID": 2544, "PLAYER_NAME": "LeBron James",
        "TEAM_ID": 1610612747, "TEAM_ABBREVIATION": "LAL",
        "PTS": 24.0, "REB": 7.0, "AST": 8.0, "GP": 65,
    },
])


def _mock_standings():
    m = MagicMock()
    m.standings.get_data_frame.return_value = STANDINGS_DF.copy()
    return m


def _mock_player_stats(df=None):
    m = MagicMock()
    m.league_dash_player_stats.get_data_frame.return_value = (df if df is not None else PLAYERS_DF).copy()
    return m


# ── Season string derivation ──────────────────────────────────────────────────

class TestCurrentNbaSeason:
    def _season_for(self, year, month):
        with patch("server.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(year, month, 15)
            return _current_nba_season()

    def test_april_is_current_season(self):
        assert self._season_for(2026, 4) == "2025-26"

    def test_october_starts_new_season(self):
        assert self._season_for(2026, 10) == "2026-27"

    def test_december_is_new_season(self):
        assert self._season_for(2026, 12) == "2026-27"

    def test_january_is_prior_season(self):
        assert self._season_for(2027, 1) == "2026-27"

    def test_september_is_prior_season(self):
        assert self._season_for(2026, 9) == "2025-26"

    def test_format_is_four_dash_two(self):
        season = self._season_for(2026, 4)
        parts = season.split("-")
        assert len(parts) == 2
        assert len(parts[0]) == 4
        assert len(parts[1]) == 2

    def test_module_constant_matches_function(self):
        """CURRENT_SEASON should equal _current_nba_season() called at import time."""
        # Both are computed from the same clock, so they must agree
        assert server.CURRENT_SEASON == _current_nba_season()


GAMES_DF = pd.DataFrame([
    {
        "GAME_ID": "0022500100", "GAME_DATE": "APR 04, 2026",
        "MATCHUP": "LAL vs. DEN", "TEAM_ABBREVIATION": "LAL",
        "PTS": 110, "WL": "W", "FG_PCT": 0.48, "FG3_PCT": 0.38, "PLUS_MINUS": 5,
    },
    {
        "GAME_ID": "0022500100", "GAME_DATE": "APR 04, 2026",
        "MATCHUP": "DEN @ LAL", "TEAM_ABBREVIATION": "DEN",
        "PTS": 105, "WL": "L", "FG_PCT": 0.46, "FG3_PCT": 0.36, "PLUS_MINUS": -5,
    },
])


def _mock_game_finder(df=GAMES_DF):
    m = MagicMock()
    m.league_game_finder_results.get_data_frame.return_value = df.copy()
    return m


# ── /api/teams ────────────────────────────────────────────────────────────────

class TestTeamsUnit:
    def test_returns_200(self, unit_client):
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()):
            r = unit_client.get("/api/teams")
        assert r.status_code == 200

    def test_response_envelope(self, unit_client):
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()):
            body = unit_client.get("/api/teams").get_json()
        assert "data" in body and "_meta" in body

    def test_team_count_matches_standings_rows(self, unit_client):
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()):
            body = unit_client.get("/api/teams").get_json()
        assert len(body["data"]) == len(STANDINGS_DF)

    def test_team_shape(self, unit_client):
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()):
            body = unit_client.get("/api/teams").get_json()
        t = body["data"][0]
        for field in ("id", "name", "city", "abbrev", "conference", "division"):
            assert field in t

    def test_lakers_abbreviation_resolved(self, unit_client):
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()):
            body = unit_client.get("/api/teams").get_json()
        lakers = next(t for t in body["data"] if t["id"] == 1610612747)
        assert lakers["abbrev"] == "LAL"

    def test_meta_count_matches_data(self, unit_client):
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()):
            body = unit_client.get("/api/teams").get_json()
        assert body["_meta"]["count"] == len(body["data"])


# ── /api/teams/<id> ───────────────────────────────────────────────────────────

ROSTER_DF = pd.DataFrame([
    {"PLAYER_ID": 203999, "PLAYER": "Nikola Jokic", "POSITION": "C", "NUM": "15"},
])


class TestTeamDetailUnit:
    def test_404_for_unknown_team(self, unit_client):
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()):
            r = unit_client.get("/api/teams/9999999")
        assert r.status_code == 404

    def test_200_for_nuggets(self, unit_client):
        roster_mock = MagicMock()
        roster_mock.common_team_roster.get_data_frame.return_value = ROSTER_DF.copy()
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()), \
             patch("nba_api.stats.endpoints.commonteamroster.CommonTeamRoster",
                   return_value=roster_mock):
            r = unit_client.get("/api/teams/1610612743")
        assert r.status_code == 200

    def test_roster_included(self, unit_client):
        roster_mock = MagicMock()
        roster_mock.common_team_roster.get_data_frame.return_value = ROSTER_DF.copy()
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()), \
             patch("nba_api.stats.endpoints.commonteamroster.CommonTeamRoster",
                   return_value=roster_mock):
            body = unit_client.get("/api/teams/1610612743").get_json()
        roster = body["data"]["roster"]
        assert isinstance(roster, list)
        assert len(roster) == 1
        assert roster[0]["id"] == 203999

    def test_roster_player_shape(self, unit_client):
        roster_mock = MagicMock()
        roster_mock.common_team_roster.get_data_frame.return_value = ROSTER_DF.copy()
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()), \
             patch("nba_api.stats.endpoints.commonteamroster.CommonTeamRoster",
                   return_value=roster_mock):
            body = unit_client.get("/api/teams/1610612743").get_json()
        p = body["data"]["roster"][0]
        for field in ("id", "name", "pos", "num"):
            assert field in p


# ── /api/players ──────────────────────────────────────────────────────────────

class TestPlayersUnit:
    def test_returns_200(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=_mock_player_stats()):
            r = unit_client.get("/api/players")
        assert r.status_code == 200

    def test_player_shape(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=_mock_player_stats()):
            body = unit_client.get("/api/players").get_json()
        p = body["data"][0]
        for field in ("id", "name", "team_id", "ppg", "rpg", "apg"):
            assert field in p

    def test_filter_by_team_id(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=_mock_player_stats()):
            body = unit_client.get("/api/players?team_id=1610612747").get_json()
        assert all(p["team_id"] == 1610612747 for p in body["data"])

    def test_filter_returns_subset(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=_mock_player_stats()):
            all_body = unit_client.get("/api/players").get_json()
            lal_body = unit_client.get("/api/players?team_id=1610612747").get_json()
        assert 0 < len(lal_body["data"]) < len(all_body["data"])

    def test_meta_count_matches_data(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=_mock_player_stats()):
            body = unit_client.get("/api/players").get_json()
        assert body["_meta"]["count"] == len(body["data"])


# ── /api/standings ────────────────────────────────────────────────────────────

class TestStandingsUnit:
    def test_returns_200(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()), \
             patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC):
            r = unit_client.get("/api/standings")
        assert r.status_code == 200

    def test_sorted_by_pct_descending(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()), \
             patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC):
            body = unit_client.get("/api/standings").get_json()
        pcts = [s["pct"] for s in body["data"]]
        assert pcts == sorted(pcts, reverse=True)

    def test_rank_sequential(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()), \
             patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC):
            body = unit_client.get("/api/standings").get_json()
        ranks = [s["rank"] for s in body["data"]]
        assert ranks == list(range(1, len(body["data"]) + 1))

    def test_conference_filter_west(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()), \
             patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC):
            body = unit_client.get("/api/standings?conference=West").get_json()
        assert all(s["conference"] == "West" for s in body["data"])

    def test_conference_filter_case_insensitive(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()), \
             patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC):
            lower = unit_client.get("/api/standings?conference=west").get_json()
            upper = unit_client.get("/api/standings?conference=West").get_json()
        assert len(lower["data"]) == len(upper["data"])

    def test_standings_entry_shape(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=_mock_standings()), \
             patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC):
            body = unit_client.get("/api/standings").get_json()
        entry = body["data"][0]
        for field in ("id", "name", "wins", "losses", "pct", "rank"):
            assert field in entry


# ── /api/games ────────────────────────────────────────────────────────────────

class TestGamesUnit:
    def test_returns_200(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=_mock_game_finder()):
            r = unit_client.get("/api/games")
        assert r.status_code == 200

    def test_game_shape(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=_mock_game_finder()):
            body = unit_client.get("/api/games").get_json()
        if body["data"]:
            game = body["data"][0]
            for field in ("id", "date", "home", "away", "home_score", "away_score", "winner"):
                assert field in game

    def test_winner_is_home_or_away(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=_mock_game_finder()):
            body = unit_client.get("/api/games").get_json()
        for game in body["data"]:
            assert game["winner"] in (game["home"], game["away"])

    def test_accepts_date_param(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=_mock_game_finder(pd.DataFrame())):
            r = unit_client.get("/api/games?date=2026-04-04")
        assert r.status_code == 200

    def test_empty_games_returns_empty_list(self, unit_client):
        with patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=_mock_game_finder(pd.DataFrame())):
            body = unit_client.get("/api/games").get_json()
        assert body["data"] == []


# ── /api/players/<id> ─────────────────────────────────────────────────────────

PLAYER_INFO_DF = pd.DataFrame([{
    "DISPLAY_FIRST_LAST": "Nikola Jokic", "TEAM_ID": 1610612743,
    "POSITION": "C", "JERSEY": "15", "HEIGHT": "6-11",
    "WEIGHT": "284", "COUNTRY": "Serbia",
}])


class TestPlayerDetailUnit:
    def test_returns_200_for_valid_player(self, unit_client):
        info_mock = MagicMock()
        info_mock.common_player_info.get_data_frame.return_value = PLAYER_INFO_DF.copy()
        with patch("nba_api.stats.endpoints.commonplayerinfo.CommonPlayerInfo",
                   return_value=info_mock), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=_mock_player_stats()):
            r = unit_client.get("/api/players/203999")
        assert r.status_code == 200

    def test_404_for_empty_response(self, unit_client):
        info_mock = MagicMock()
        info_mock.common_player_info.get_data_frame.return_value = pd.DataFrame()
        with patch("nba_api.stats.endpoints.commonplayerinfo.CommonPlayerInfo",
                   return_value=info_mock), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=_mock_player_stats()):
            r = unit_client.get("/api/players/9999999")
        assert r.status_code == 404

    def test_player_shape(self, unit_client):
        info_mock = MagicMock()
        info_mock.common_player_info.get_data_frame.return_value = PLAYER_INFO_DF.copy()
        with patch("nba_api.stats.endpoints.commonplayerinfo.CommonPlayerInfo",
                   return_value=info_mock), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=_mock_player_stats()):
            body = unit_client.get("/api/players/203999").get_json()
        for field in ("id", "name", "team_id", "pos", "ppg", "rpg", "apg"):
            assert field in body["data"]

    def test_stats_merged_from_league_dash(self, unit_client):
        info_mock = MagicMock()
        info_mock.common_player_info.get_data_frame.return_value = PLAYER_INFO_DF.copy()
        with patch("nba_api.stats.endpoints.commonplayerinfo.CommonPlayerInfo",
                   return_value=info_mock), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=_mock_player_stats()):
            body = unit_client.get("/api/players/203999").get_json()
        assert body["data"]["ppg"] == 29.0


# ── /api/players/<id>/gamelog ─────────────────────────────────────────────────

GAMELOG_DF = pd.DataFrame([
    {
        "GAME_DATE": "APR 04, 2026", "MATCHUP": "DEN vs. LAL",
        "PTS": 35, "REB": 12, "AST": 9,
        "FG_PCT": 0.58, "MIN": "36:00", "WL": "W",
    },
] * 15)  # 15 rows to test n param


class TestGameLogUnit:
    def _mock_gamelog(self):
        m = MagicMock()
        m.player_game_log.get_data_frame.return_value = GAMELOG_DF.copy()
        return m

    def test_default_n_is_10(self, unit_client):
        with patch("nba_api.stats.endpoints.playergamelog.PlayerGameLog",
                   return_value=self._mock_gamelog()):
            body = unit_client.get("/api/players/203999/gamelog").get_json()
        assert len(body["data"]) == 10

    def test_custom_n(self, unit_client):
        with patch("nba_api.stats.endpoints.playergamelog.PlayerGameLog",
                   return_value=self._mock_gamelog()):
            body = unit_client.get("/api/players/203999/gamelog?n=5").get_json()
        assert len(body["data"]) == 5

    def test_n_capped_by_available_games(self, unit_client):
        with patch("nba_api.stats.endpoints.playergamelog.PlayerGameLog",
                   return_value=self._mock_gamelog()):
            body = unit_client.get("/api/players/203999/gamelog?n=100").get_json()
        assert len(body["data"]) == len(GAMELOG_DF)

    def test_game_log_entry_shape(self, unit_client):
        with patch("nba_api.stats.endpoints.playergamelog.PlayerGameLog",
                   return_value=self._mock_gamelog()):
            body = unit_client.get("/api/players/203999/gamelog").get_json()
        entry = body["data"][0]
        for field in ("game", "date", "pts", "reb", "ast", "fg_pct", "min"):
            assert field in entry

    def test_meta_contains_player_id(self, unit_client):
        with patch("nba_api.stats.endpoints.playergamelog.PlayerGameLog",
                   return_value=self._mock_gamelog()):
            body = unit_client.get("/api/players/203999/gamelog").get_json()
        assert body["_meta"]["player_id"] == 203999


# ── Cache behaviour ───────────────────────────────────────────────────────────

class TestCacheBehaviour:
    def test_second_call_does_not_hit_api(self, unit_client):
        call_count = 0

        def counting_stats(**kwargs):
            nonlocal call_count
            call_count += 1
            return _mock_player_stats()

        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   side_effect=counting_stats):
            unit_client.get("/api/players")
            unit_client.get("/api/players")

        assert call_count == 1, "Cache should prevent second API hit"

    def test_cache_expires_after_ttl(self, unit_client):
        call_count = 0

        def counting_stats(**kwargs):
            nonlocal call_count
            call_count += 1
            return _mock_player_stats()

        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   side_effect=counting_stats):
            unit_client.get("/api/players")

        # Manually expire the cache entry
        _cache["players"]["ts"] = time.time() - 9999

        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   side_effect=counting_stats):
            unit_client.get("/api/players")

        assert call_count == 2, "Expired cache should trigger a fresh API call"


# ── /api/map ──────────────────────────────────────────────────────────────────

class TestApiMapUnit:
    EXPECTED_NODES = {
        "root", "teams", "players", "standings", "games",
        "team_detail", "player_detail", "game_log", "game_detail",
        "analytics", "last_night", "season_analytics",
        "team_dashboard", "lakers_dashboard",
    }

    def test_returns_200(self, unit_client):
        r = unit_client.get("/api/map")
        assert r.status_code == 200

    def test_contains_all_nodes(self, unit_client):
        body = unit_client.get("/api/map").get_json()
        assert self.EXPECTED_NODES == set(body.keys())

    def test_analytics_children(self, unit_client):
        body = unit_client.get("/api/map").get_json()
        assert set(body["analytics"]["children"]) == {
            "last_night", "season_analytics", "team_dashboard", "lakers_dashboard"
        }

    def test_root_includes_analytics(self, unit_client):
        body = unit_client.get("/api/map").get_json()
        assert "analytics" in body["root"]["children"]

    def test_endpoint_nodes_have_endpoint_key(self, unit_client):
        body = unit_client.get("/api/map").get_json()
        for key in ("last_night", "season_analytics", "team_dashboard", "lakers_dashboard"):
            assert "endpoint" in body[key], f"Node '{key}' missing 'endpoint'"

    def test_analytics_children_include_team_dashboard(self, unit_client):
        body = unit_client.get("/api/map").get_json()
        assert "team_dashboard" in body["analytics"]["children"]


# ── Analytics endpoints (unit) ────────────────────────────────────────────────

LAST_NIGHT_PLAYER_DF = pd.DataFrame([
    {
        "PLAYER_ID": 2544, "PLAYER_NAME": "LeBron James",
        "TEAM_ABBREVIATION": "LAL",
        "PTS": 38, "REB": 8, "AST": 7, "STL": 2, "BLK": 1, "TOV": 3,
        "FGM": 14, "FGA": 22, "FTA": 6, "FG_PCT": 0.636, "MIN": "38:00",
    },
    {
        "PLAYER_ID": 203999, "PLAYER_NAME": "Nikola Jokic",
        "TEAM_ABBREVIATION": "DEN",
        "PTS": 30, "REB": 14, "AST": 11, "STL": 1, "BLK": 2, "TOV": 2,
        "FGM": 12, "FGA": 18, "FTA": 4, "FG_PCT": 0.667, "MIN": "35:00",
    },
])

ADV_PLAYER_DF = pd.DataFrame([
    {
        "PLAYER_ID": 203999, "PLAYER_NAME": "Nikola Jokic",
        "TEAM_ABBREVIATION": "DEN", "GP": 68,
        "TS_PCT": 0.655, "EFG_PCT": 0.598, "USG_PCT": 0.302,
        "NET_RATING": 12.5, "PIE": 0.178, "AST_PCT": 0.425, "REB_PCT": 0.219,
    },
    {
        "PLAYER_ID": 2544, "PLAYER_NAME": "LeBron James",
        "TEAM_ABBREVIATION": "LAL", "GP": 65,
        "TS_PCT": 0.590, "EFG_PCT": 0.545, "USG_PCT": 0.280,
        "NET_RATING": 5.2, "PIE": 0.155, "AST_PCT": 0.320, "REB_PCT": 0.125,
    },
])

ADV_TEAM_DF = pd.DataFrame([
    {
        "TEAM_ID": 1610612747, "TEAM_NAME": "Lakers",
        "NET_RATING": 4.2, "OFF_RATING": 115.3, "DEF_RATING": 111.1,
        "PACE": 100.5, "TS_PCT": 0.580, "EFG_PCT": 0.540, "PIE": 0.510,
    },
    {
        "TEAM_ID": 1610612743, "TEAM_NAME": "Nuggets",
        "NET_RATING": 8.1, "OFF_RATING": 118.2, "DEF_RATING": 110.1,
        "PACE": 98.3, "TS_PCT": 0.605, "EFG_PCT": 0.565, "PIE": 0.540,
    },
])


class TestLastNightUnit:
    def _patches(self, player_df=None):
        gf_mock = MagicMock()
        gf_mock.league_game_finder_results.get_data_frame.return_value = GAMES_DF.copy()
        ps_mock = MagicMock()
        ps_mock.league_dash_player_stats.get_data_frame.return_value = (
            player_df if player_df is not None else LAST_NIGHT_PLAYER_DF
        ).copy()
        return gf_mock, ps_mock

    def test_returns_200(self, unit_client):
        gf, ps = self._patches()
        with patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=ps):
            r = unit_client.get("/api/analytics/last-night")
        assert r.status_code == 200

    def test_response_envelope(self, unit_client):
        gf, ps = self._patches()
        with patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=ps):
            body = unit_client.get("/api/analytics/last-night").get_json()
        assert "data" in body and "_meta" in body

    def test_data_shape(self, unit_client):
        gf, ps = self._patches()
        with patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=ps):
            body = unit_client.get("/api/analytics/last-night").get_json()
        data = body["data"]
        for field in ("date", "game_count", "games", "top_performers"):
            assert field in data

    def test_top_performers_sorted_by_pts(self, unit_client):
        gf, ps = self._patches()
        with patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=ps):
            body = unit_client.get("/api/analytics/last-night").get_json()
        pts_list = [p["pts"] for p in body["data"]["top_performers"]]
        assert pts_list == sorted(pts_list, reverse=True)

    def test_ts_pct_computed_correctly(self, unit_client):
        gf, ps = self._patches()
        with patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=ps):
            body = unit_client.get("/api/analytics/last-night").get_json()
        lebron = next(p for p in body["data"]["top_performers"] if "LeBron" in p["name"])
        # TS% = 38 / (2 * (22 + 0.44*6)) = 38 / 49.28 ≈ 77.1
        assert lebron["ts_pct"] == pytest.approx(77.1, abs=0.2)

    def test_empty_when_no_games(self, unit_client):
        gf = MagicMock()
        gf.league_game_finder_results.get_data_frame.return_value = pd.DataFrame()
        ps = MagicMock()
        ps.league_dash_player_stats.get_data_frame.return_value = pd.DataFrame()
        with patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=ps):
            body = unit_client.get("/api/analytics/last-night").get_json()
        assert body["data"]["game_count"] == 0
        assert body["data"]["games"] == []

    def test_game_count_matches_games_list(self, unit_client):
        gf, ps = self._patches()
        with patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=ps):
            body = unit_client.get("/api/analytics/last-night").get_json()
        data = body["data"]
        assert data["game_count"] == len(data["games"])


class TestSeasonAnalyticsUnit:
    def _patches(self):
        ps_mock = MagicMock()
        ps_mock.league_dash_player_stats.get_data_frame.return_value = ADV_PLAYER_DF.copy()
        ts_mock = MagicMock()
        ts_mock.league_dash_team_stats.get_data_frame.return_value = ADV_TEAM_DF.copy()
        return ps_mock, ts_mock

    def test_returns_200(self, unit_client):
        ps, ts = self._patches()
        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=ps), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ts):
            r = unit_client.get("/api/analytics/season")
        assert r.status_code == 200

    def test_response_envelope(self, unit_client):
        ps, ts = self._patches()
        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=ps), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ts):
            body = unit_client.get("/api/analytics/season").get_json()
        assert "data" in body and "_meta" in body

    def test_data_shape(self, unit_client):
        ps, ts = self._patches()
        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=ps), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ts):
            body = unit_client.get("/api/analytics/season").get_json()
        data = body["data"]
        for field in ("season", "top_players_ts", "top_players_net", "top_players_usg", "teams"):
            assert field in data

    def test_players_filtered_by_min_gp(self, unit_client):
        """Players with < 20 GP should be excluded."""
        low_gp_df = ADV_PLAYER_DF.copy()
        low_gp_df.loc[0, "GP"] = 5  # Jokic row — should be excluded
        ps_mock = MagicMock()
        ps_mock.league_dash_player_stats.get_data_frame.return_value = low_gp_df
        ts_mock = MagicMock()
        ts_mock.league_dash_team_stats.get_data_frame.return_value = ADV_TEAM_DF.copy()
        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=ps_mock), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ts_mock):
            body = unit_client.get("/api/analytics/season").get_json()
        names_ts = [p["name"] for p in body["data"]["top_players_ts"]]
        assert "Nikola Jokic" not in names_ts

    def test_teams_sorted_by_net_rating(self, unit_client):
        ps, ts = self._patches()
        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=ps), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ts):
            body = unit_client.get("/api/analytics/season").get_json()
        ratings = [t["net_rating"] for t in body["data"]["teams"]]
        assert ratings == sorted(ratings, reverse=True)

    def test_season_field_matches_constant(self, unit_client):
        ps, ts = self._patches()
        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=ps), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ts):
            body = unit_client.get("/api/analytics/season").get_json()
        assert body["data"]["season"] == server.CURRENT_SEASON

    def test_ts_pct_scaled_to_percentage(self, unit_client):
        ps, ts = self._patches()
        with patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=ps), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ts):
            body = unit_client.get("/api/analytics/season").get_json()
        # TS_PCT raw = 0.655 → should be stored as 65.5
        jokic = next(p for p in body["data"]["top_players_ts"] if p["name"] == "Nikola Jokic")
        assert jokic["ts_pct"] == pytest.approx(65.5, abs=0.1)


class TestLakersDashboardUnit:
    def _patches(self):
        standings_mock = _mock_standings()
        gf_mock = MagicMock()
        gf_mock.league_game_finder_results.get_data_frame.return_value = (
            GAMES_DF[GAMES_DF["TEAM_ABBREVIATION"] == "LAL"].copy()
        )
        lal_trad_df = PLAYERS_DF[PLAYERS_DF["TEAM_ABBREVIATION"] == "LAL"].copy()
        lal_trad_df = lal_trad_df.assign(
            FG_PCT=0.48, FG3_PCT=0.36, FT_PCT=0.78, MIN=32.0
        )
        trad_mock = MagicMock()
        trad_mock.league_dash_player_stats.get_data_frame.return_value = lal_trad_df
        adv_mock = MagicMock()
        adv_mock.league_dash_player_stats.get_data_frame.return_value = (
            ADV_PLAYER_DF[ADV_PLAYER_DF["TEAM_ABBREVIATION"] == "LAL"].copy()
        )
        tadv_mock = MagicMock()
        tadv_mock.league_dash_team_stats.get_data_frame.return_value = ADV_TEAM_DF.copy()
        return standings_mock, gf_mock, trad_mock, adv_mock, tadv_mock

    def test_returns_200(self, unit_client):
        sm, gf, tp, ap, ta = self._patches()
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=sm), \
             patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=tp), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ta):
            r = unit_client.get("/api/analytics/lakers")
        assert r.status_code == 200

    def test_data_shape(self, unit_client):
        sm, gf, tp, ap, ta = self._patches()
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=sm), \
             patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=tp), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ta):
            body = unit_client.get("/api/analytics/lakers").get_json()
        data = body["data"]
        for field in ("team", "standing", "team_advanced", "recent_games", "roster_stats"):
            assert field in data

    def test_standing_fields(self, unit_client):
        sm, gf, tp, ap, ta = self._patches()
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=sm), \
             patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=tp), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ta):
            body = unit_client.get("/api/analytics/lakers").get_json()
        standing = body["data"]["standing"]
        assert standing["wins"] == 45
        assert standing["losses"] == 30
        assert standing["last_10"] == "7-3"
        assert standing["streak"] == "W2"

    def test_roster_sorted_by_ppg(self, unit_client):
        sm, gf, tp, ap, ta = self._patches()
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=sm), \
             patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=tp), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ta):
            body = unit_client.get("/api/analytics/lakers").get_json()
        ppgs = [p["ppg"] for p in body["data"]["roster_stats"]]
        assert ppgs == sorted(ppgs, reverse=True)

    def test_team_advanced_fields(self, unit_client):
        sm, gf, tp, ap, ta = self._patches()
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=sm), \
             patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=tp), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ta):
            body = unit_client.get("/api/analytics/lakers").get_json()
        adv = body["data"]["team_advanced"]
        for field in ("net_rating", "off_rating", "def_rating", "pace", "ts_pct"):
            assert field in adv

    def test_recent_games_capped_at_10(self, unit_client):
        big_df = pd.concat(
            [GAMES_DF[GAMES_DF["TEAM_ABBREVIATION"] == "LAL"]] * 15, ignore_index=True
        )
        gf = MagicMock()
        gf.league_game_finder_results.get_data_frame.return_value = big_df
        sm, _, tp, ap, ta = self._patches()
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=sm), \
             patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=tp), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ta):
            body = unit_client.get("/api/analytics/lakers").get_json()
        assert len(body["data"]["recent_games"]) <= 10


# ── /api/analytics/team/<id> ──────────────────────────────────────────────────

class TestTeamDashboardUnit:
    """Generic team dashboard — reuses the same logic as Lakers but with any team_id."""

    def _patches(self, team_abbrev="DEN", team_id=1610612743):
        sm = _mock_standings()
        gf = MagicMock()
        gf.league_game_finder_results.get_data_frame.return_value = (
            GAMES_DF[GAMES_DF["TEAM_ABBREVIATION"] == team_abbrev].copy()
        )
        trad_df = PLAYERS_DF[PLAYERS_DF["TEAM_ABBREVIATION"] == team_abbrev].copy()
        trad_df = trad_df.assign(FG_PCT=0.50, FG3_PCT=0.37, FT_PCT=0.82, MIN=35.0)
        tp = MagicMock()
        tp.league_dash_player_stats.get_data_frame.return_value = trad_df
        ap = MagicMock()
        ap.league_dash_player_stats.get_data_frame.return_value = (
            ADV_PLAYER_DF[ADV_PLAYER_DF["TEAM_ABBREVIATION"] == team_abbrev].copy()
        )
        ta = MagicMock()
        ta.league_dash_team_stats.get_data_frame.return_value = ADV_TEAM_DF.copy()
        return sm, gf, tp, ap, ta

    def test_returns_200_for_valid_team(self, unit_client):
        sm, gf, tp, ap, ta = self._patches()
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=sm), \
             patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=tp), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ta):
            r = unit_client.get("/api/analytics/team/1610612743")
        assert r.status_code == 200

    def test_returns_404_for_unknown_team(self, unit_client):
        sm, gf, tp, ap, ta = self._patches()
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=sm), \
             patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=tp), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ta):
            r = unit_client.get("/api/analytics/team/9999999")
        assert r.status_code == 404

    def test_meta_endpoint_label(self, unit_client):
        sm, gf, tp, ap, ta = self._patches()
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=sm), \
             patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=tp), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ta):
            body = unit_client.get("/api/analytics/team/1610612743").get_json()
        assert body["_meta"]["endpoint"] == "team_dashboard"
        assert body["_meta"]["team_id"] == 1610612743

    def test_data_shape(self, unit_client):
        sm, gf, tp, ap, ta = self._patches()
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=sm), \
             patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=tp), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ta):
            body = unit_client.get("/api/analytics/team/1610612743").get_json()
        for field in ("team", "standing", "team_advanced", "recent_games", "roster_stats"):
            assert field in body["data"]

    def test_correct_team_in_response(self, unit_client):
        sm, gf, tp, ap, ta = self._patches()
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=sm), \
             patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=tp), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ta):
            body = unit_client.get("/api/analytics/team/1610612743").get_json()
        assert body["data"]["team"]["id"] == 1610612743

    def test_lakers_alias_and_generic_same_shape(self, unit_client):
        """Both the /lakers alias and /team/LAL_ID must return the same top-level keys."""
        sm, gf, tp_lal, ap_lal, ta = self._patches(team_abbrev="LAL", team_id=1610612747)
        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=sm), \
             patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   return_value=gf), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=tp_lal), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ta):
            generic = unit_client.get("/api/analytics/team/1610612747").get_json()
            alias = unit_client.get("/api/analytics/lakers").get_json()
        assert set(generic["data"].keys()) == set(alias["data"].keys())

    def test_cache_is_per_team(self, unit_client):
        """Two different team IDs must get separate cache entries."""
        call_count = 0

        def counting_fetcher(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            m.league_game_finder_results.get_data_frame.return_value = pd.DataFrame()
            return m

        sm = _mock_standings()
        tp = MagicMock()
        tp.league_dash_player_stats.get_data_frame.return_value = pd.DataFrame(
            columns=["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "GP",
                     "PTS", "REB", "AST", "FG_PCT", "FG3_PCT", "FT_PCT", "MIN",
                     "TS_PCT", "USG_PCT", "NET_RATING"]
        )
        ta = MagicMock()
        ta.league_dash_team_stats.get_data_frame.return_value = ADV_TEAM_DF.copy()

        with patch("nba_api.stats.static.teams.get_teams", return_value=TEAMS_STATIC), \
             patch("nba_api.stats.endpoints.leaguestandingsv3.LeagueStandingsV3",
                   return_value=sm), \
             patch("nba_api.stats.endpoints.leaguegamefinder.LeagueGameFinder",
                   side_effect=counting_fetcher), \
             patch("nba_api.stats.endpoints.leaguedashplayerstats.LeagueDashPlayerStats",
                   return_value=tp), \
             patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
                   return_value=ta):
            unit_client.get("/api/analytics/team/1610612747")
            unit_client.get("/api/analytics/team/1610612743")

        assert call_count == 2, "Each team should make its own LeagueGameFinder call"
