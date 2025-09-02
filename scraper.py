"""Web scrapers for various watch marketplaces."""

from typing import List, Dict

import requests
from requests import HTTPError
from bs4 import BeautifulSoup

try:  # Optional dependency for bypassing basic anti-bot protections
    import cloudscraper
except Exception:  # pragma: no cover - fallback when library is unavailable
    cloudscraper = None

BASE_URLS = {
    "chrono24": "https://www.chrono24.com/search/index.htm",
    "danggeun": "https://www.daangn.com/search/",
    "watchcafe": "https://watchcafe.example.com/search",
}


def fetch_watch_prices(query: str, source: str = "chrono24") -> List[Dict[str, str]]:
    """Fetch watch listings from the given source.

    Args:
        query: Search string for the watch model or brand.
        source: Marketplace to scrape ("chrono24", "danggeun", "watchcafe").

    Returns:
        A list of dictionaries with watch ``name``, ``price``, ``details`` and ``source`` fields.
    """

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9," "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    url = BASE_URLS.get(source, BASE_URLS["chrono24"])
    params = {"query": query, "dosearch": "true"} if source == "chrono24" else None
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if getattr(response, "status_code", None) == 403 and cloudscraper is not None:
            scraper = cloudscraper.create_scraper()
            response = scraper.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
    except HTTPError:
        raise
    except requests.RequestException as exc:  # pragma: no cover - network error handling
        raise RuntimeError(f"{source}에서 데이터를 가져오는 데 실패했습니다: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    watches: List[Dict[str, str]] = []
    for item in soup.select("article"):
        name_tag = item.select_one("a.article-name") or item.select_one("a")
        price_tag = item.select_one(".article-price") or item.select_one(".price")
        if not name_tag or not price_tag:
            continue
        name = name_tag.get_text(strip=True)
        price = price_tag.get_text(strip=True)
        details = name_tag.get("href", "")
        watches.append({"name": name, "price": price, "details": details, "source": source})
    return watches

