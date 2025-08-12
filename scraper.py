import requests
from bs4 import BeautifulSoup
from typing import List, Dict

BASE_URL = "https://www.chrono24.com/search/index.htm"


def fetch_watch_prices(query: str) -> List[Dict[str, str]]:
    """Fetch watch listings from Chrono24 search results.

    Args:
        query: Search string for the watch model or brand.

    Returns:
        A list of dictionaries with watch ``name`` and ``price`` fields.
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    params = {"query": query, "dosearch": "true"}
    response = requests.get(BASE_URL, params=params, headers=headers, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    watches: List[Dict[str, str]] = []
    for item in soup.select("article.article-item"):
        name_tag = item.select_one(".article-name")
        price_tag = item.select_one(".article-price")
        if not name_tag or not price_tag:
            continue
        name = name_tag.get_text(strip=True)
        price = price_tag.get_text(strip=True)
        watches.append({"name": name, "price": price})
    return watches
