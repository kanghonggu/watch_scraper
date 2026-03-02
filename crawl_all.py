import time
import random
from typing import List, Dict
from pymongo import MongoClient

from crawl_chrono import Chrono24SeleniumScraper
from crawl_viver import ViverSeleniumScraper, save_to_mongo as viver_save
from crawl_cafe import NaverCafeScraper

MONGO_URI = "mongodb+srv://test:2RGdjwLiJyuzFwWn@super-mongo.zizsavi.mongodb.net?retryWrites=true&w=majority&appName=super-mongo"

if __name__ == "__main__":
    client = MongoClient(MONGO_URI)

    # ── 1. Chrono24 ──────────────────────────────
    print("\n" + "#" * 60)
    print("# 1. Chrono24 크롤링 시작")
    print("#" * 60)

    chrono_col = client["watchdb"]["chrono24"]

    def save_chrono(items: List[Dict]):
        for item in items:
            try:
                chrono_col.update_one(
                    {"detail_url": item["detail_url"]},
                    {"$set": item},
                    upsert=True,
                )
            except Exception as e:
                print(f"  ⚠️ 저장 오류: {e}")
        print(f"  ✅ {len(items)}개 저장 완료")

    chrono = Chrono24SeleniumScraper(headless=True)
    try:
        brands = ["rolex", "omega", "audemarspiguet", "patekphilippe", "richardmille", "cartier"]
        for brand in brands:
            print(f"\n{'#'*60}")
            print(f"# {brand.upper()}")
            print(f"{'#'*60}")
            chrono.fetch_multi_pages(
                brand=brand,
                start_page=1,
                end_page=3,
                page_size=120,
                fetch_detail=True,
                save_callback=save_chrono,
            )
            time.sleep(random.uniform(0.2, 0.3))
    finally:
        chrono.close()

    # ── 2. Viver ─────────────────────────────────
    print("\n" + "#" * 60)
    print("# 2. Viver 크롤링 시작")
    print("#" * 60)

    viver = ViverSeleniumScraper(headless=True)
    try:
        data = viver.fetch_list(
            "https://www.viver.co.kr/shop",
            max_pages=30,
            only_today=True,
        )
        saved = viver_save(data, mongo_uri=MONGO_URI, db_name="watchdb", collection_name="viver")
        print(f"  ✅ {saved}개 저장 완료")
    finally:
        viver.close()

    # ── 3. Naver Cafe ─────────────────────────────
    print("\n" + "#" * 60)
    print("# 3. Naver Cafe 크롤링 시작")
    print("#" * 60)

    cafe = NaverCafeScraper(headless=True)
    try:
        cafe.login_with_cookies("naver_cookies.pkl")
        posts = cafe.fetch_posts_until_no_new(
            menu_url="https://cafe.naver.com/f-e/cafes/18629593/menus/832?page=1&size=50&headId=1400",
            start_page=1,
            page_size=50,
        )
        if posts:
            client["watchdb"]["naver_cafe"].insert_many(posts)
            print(f"  ✅ {len(posts)}개 저장 완료")
        else:
            print("  ℹ️ 새 게시글 없음")
    finally:
        cafe.close()

    client.close()
    print("\n🎉 전체 크롤링 완료!")
