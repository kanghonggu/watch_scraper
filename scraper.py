"""Web scrapers for various watch marketplaces."""

from typing import List, Dict

import requests
from bs4 import BeautifulSoup

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

    headers = {"User-Agent": "Mozilla/5.0"}
    url = BASE_URLS.get(source, BASE_URLS["chrono24"])
    params = {"query": query, "dosearch": "true"} if source == "chrono24" else None
    response = requests.get(url, params=params, headers=headers, timeout=10)
    response.raise_for_status()

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

