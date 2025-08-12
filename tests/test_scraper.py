import os
from fastapi.testclient import TestClient
from unittest.mock import patch

import scraper
import database
from api import app

SAMPLE_HTML = """
<html><body>
<article class='article-item'>
  <div class='article-name'>Rolex Submariner</div>
  <div class='article-price'>USD 10000</div>
</article>
<article class='article-item'>
  <div class='article-name'>Omega Speedmaster</div>
  <div class='article-price'>EUR 5000</div>
</article>
</body></html>
"""


class DummyResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


def mock_get(url, params=None, headers=None, timeout=10):
    return DummyResponse(SAMPLE_HTML)


def test_fetch_watch_prices():
    with patch("scraper.requests.get", mock_get):
        results = scraper.fetch_watch_prices("rolex")
    assert len(results) == 2
    assert results[0]["name"] == "Rolex Submariner"
    assert results[0]["price"] == "USD 10000"


def test_api_scrape_and_list(tmp_path, monkeypatch):
    # Use temporary DB for the test
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_NAME", str(db_path))

    with patch("scraper.requests.get", mock_get):
        with TestClient(app) as client:
            response = client.post("/scrape", params={"query": "rolex"})
            assert response.status_code == 200
            assert response.json() == {"count": 2}

            response = client.get("/watches")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[1]["name"] == "Omega Speedmaster"
