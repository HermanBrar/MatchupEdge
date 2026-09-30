from fastapi.testclient import TestClient

from app.main import app


def test_health_and_status():
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        status = client.get("/api/v1/status").json()
        assert status["mode"] == "demo"
        assert status["live_configured"] is False


def test_demo_workflow_endpoints():
    with TestClient(app) as client:
        games = client.get("/api/v1/games").json()
        projections = client.get("/api/v1/projections").json()
        assert len(games) >= 2
        assert len(projections) >= 4
        assert all(item["data_mode"] == "demo" for item in projections)


def test_odds_endpoint():
    with TestClient(app) as client:
        response = client.post("/api/v1/odds", json={"american_odds": 150, "stake": 20})
        assert response.status_code == 200
        assert response.json()["decimal_odds"] == 2.5


def test_explicit_demo_is_isolated_from_real_slate():
    with TestClient(app) as client:
        demo = client.get('/api/v1/demo?sport=NFL').json()
        assert demo['status']['mode'] == 'demo'
        assert all(g['id'].startswith('demo-') for g in demo['games'])
        real = client.get('/api/v1/slate?season=2099').json()
        assert real['games'] == [] and real['players'] == []
