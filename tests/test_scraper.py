from unittest.mock import patch
import sys
import pathlib

sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))

import scraper
import database
from api import scrape as api_scrape, list_watches

SAMPLE_HTML = """
<html><body>
<article class='article-item'>
  <a class='article-name' href='https://example.com/rolex'>Rolex Submariner</a>
  <div class='article-price'>USD 10000</div>
</article>
<article class='article-item'>
  <a class='article-name' href='https://example.com/omega'>Omega Speedmaster</a>
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
        results = scraper.fetch_watch_prices("rolex", source="chrono24")
    assert len(results) == 2
    assert results[0]["name"] == "Rolex Submariner"
    assert results[0]["price"] == "USD 10000"
    assert results[0]["details"] == "https://example.com/rolex"
    assert results[0]["source"] == "chrono24"


def test_api_scrape_and_list():
    database.client = None
    database.init_db()

    with patch("scraper.requests.get", mock_get):
        response = api_scrape("rolex")
        assert response == {"count": 2}

    data = list_watches()
    assert len(data) == 2
    assert data[1]["name"] == "Omega Speedmaster"
    assert data[0]["details"] == "https://example.com/rolex"
    assert data[0]["source"] == "chrono24"
