from fastapi import FastAPI, Query
from pymongo import MongoClient
from typing import List, Dict
from scraper import Chrono24SeleniumScraper

app = FastAPI(title="Chrono24 Selenium Scraper API")

# MongoDB 설정 (동기 PyMongo)
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "watchdb"
client = MongoClient(MONGO_URI)
db = client[DB_NAME]


@app.get("/chrono24")
def search_chrono24(
    brand: str = Query(..., description="검색할 브랜드 예: rolex"),
    pages: str = Query("1-1", description="크롤링할 페이지 범위 예: 1-3"),
    group: str = Query("", description="그룹명 (선택)"),
    page_size: int = Query(60, description="페이지당 아이템 개수 (기본 60)")
):
    """
    Chrono24 페이징 크롤링 API (동기 버전)
    예시: /chrono24?brand=rolex&pages=1-2
    """
    try:
        start_page, end_page = [int(x) for x in pages.split("-")]
    except Exception:
        return {"error": "pages 파라미터는 'start-end' 형식이어야 합니다. 예: 1-3"}

    scraper = Chrono24SeleniumScraper(headless=True)
    try:
        results = scraper.fetch_multi_pages(
            brand=brand,
            start_page=start_page,
            end_page=end_page,
            group_str=group,
            page_size=page_size
        )

        if results:
            db["chrono24"].insert_many(results)

        return {"brand": brand, "pages": pages, "count": len(results), "results": results[:10]}
    finally:
        scraper.close()
