"""
pytest configuration: warm the server's in-memory cache once per session
before any tests run, so individual tests never hit the NBA API cold.
Delays between calls respect stats.nba.com rate limits.
"""

import time
import pytest


@pytest.fixture(scope="session")
def client():
    from server import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def warm_cache(client):
    """Pre-populate the cache for all endpoints used in the test suite."""
    # These two share the leaguestandingsv3 call (teams caches it)
    client.get("/api/teams")
    time.sleep(1.0)

    # Separate leaguedashplayerstats call
    client.get("/api/players")
    time.sleep(1.0)

    # Standings reuses the cached df
    client.get("/api/standings")
    time.sleep(0.5)

    # Games: leaguegamefinder
    client.get("/api/games")
    time.sleep(1.0)

    # Player detail + game log for Jokic (203999)
    client.get("/api/players/203999")
    time.sleep(0.5)
    client.get("/api/players/203999/gamelog")
    time.sleep(1.0)

    # Team detail for Nuggets (1610612743)
    client.get("/api/teams/1610612743")
    time.sleep(0.5)
