import os
import datetime
import time
import random
from typing import List, Dict

from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from pymongo import MongoClient

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium_stealth import stealth

MONGO_URI = "mongodb+srv://test:2RGdjwLiJyuzFwWn@super-mongo.zizsavi.mongodb.net?retryWrites=true&w=majority&appName=super-mongo"
DRIVER_PATH = os.environ.get("CHROMEDRIVER_PATH") or os.path.join(os.path.dirname(__file__), "chromedriver")


def create_driver(headless: bool = True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ko-KR")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(DRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=options)

    stealth(driver,
        languages=["ko-KR", "ko"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    return driver


class Chrono24SeleniumScraper:
    BASE_URL = "https://www.chrono24.kr"

    def __init__(self, headless: bool = True, debug: bool = False):
        self.driver = create_driver(headless=headless)
        self.debug = debug

    def _wait_for_page_load(self, timeout: int = 15):
        WebDriverWait(self.driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

    def _save_debug_html(self, filename: str):
        with open(filename, "w", encoding="utf-8") as f:
            f.write(self.driver.page_source)
        print(f"  💾 HTML 저장: {filename}")

    def fetch_page(self, brand: str, page: int = 1, page_size: int = 120) -> List[Dict]:
        url = f"{self.BASE_URL}/{brand}/index-{page}.html?pageSize={page_size}&sortorder=5"
        print(f"\n📄 [LIST] {url}")

        self.driver.get(url)
        try:
            self._wait_for_page_load(timeout=20)
        except Exception:
            pass
        time.sleep(random.uniform(3, 5))

        if self.debug:
            self._save_debug_html(f"debug_list_{brand}_p{page}.html")

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        items = soup.select("div.js-article-item-container")
        print(f"   → {len(items)}개 아이템 발견")

        if not items:
            print(f"  ❌ 아이템 없음. 페이지 제목: {soup.title.get_text() if soup.title else 'N/A'}")
            return []

        today = datetime.datetime.now().strftime("%Y-%m-%d")
        results = []

        for item in items:
            try:
                link_tag = item.select_one("a.wt-listing-item-link")
                if not link_tag:
                    continue
                href = link_tag.get("href", "")
                detail_url = href if href.startswith("http") else self.BASE_URL + href

                title_tag = link_tag.select_one("p.text-bold.text-sm")
                title = title_tag.get_text(strip=True) if title_tag else ""

                subtitle_tags = link_tag.select("p.text-ellipsis")
                subtitle = subtitle_tags[1].get_text(strip=True) if len(subtitle_tags) > 1 else ""

                price_tag = link_tag.select_one("p.text-bold.text-md")
                price = price_tag.get_text(strip=True) if price_tag else ""

                image = ""
                for watch_div in item.select("div.watch-image"):
                    if not watch_div.get("inert"):
                        img = watch_div.select_one("img")
                        if img:
                            src = (
                                img.get("data-lazy-sweet-spot-master-src")
                                or img.get("src", "")
                            )
                            image = src.replace("_SIZE_", "480") if src else ""
                        break

                location_tag = item.select_one("span.text-uppercase")
                location = location_tag.get_text(strip=True) if location_tag else ""

                results.append({
                    "brand": brand,
                    "title": title,
                    "subtitle": subtitle,
                    "price": price,
                    "image": image,
                    "location": location,
                    "detail_url": detail_url,
                    "source": "chrono24",
                    "crawled_date": today,
                    "detail_fetched": False,
                })

            except Exception as e:
                print(f"  ⚠️ 파싱 오류: {e}")
                continue

        return results

    def fetch_detail(self, url: str) -> Dict:
        try:
            print(f"    🔗 상세 이동: {url}")
            self.driver.get(url)
            self._wait_for_page_load(timeout=20)
            time.sleep(random.uniform(0.2, 0.3))

            if self.debug:
                self._save_debug_html("debug_detail.html")

            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            return self._parse_detail(soup, url)

        except Exception as e:
            print(f"  ❌ [DETAIL] 오류: {e}")
            return {}

    def _parse_detail(self, soup: BeautifulSoup, url: str) -> Dict:
        specs = {}
        for row in soup.select("table tr"):
            key_tag = row.select_one("td.p-r-2 strong")
            tds = row.select("td")
            if key_tag and len(tds) >= 2:
                key = key_tag.get_text(strip=True)
                val = tds[1].get_text(strip=True)
                if key:
                    specs[key] = val

        condition = ""
        for row in soup.select("table tr"):
            key_tag = row.select_one("td.p-r-2 strong")
            if key_tag and key_tag.get_text(strip=True) == "제품 컨디션":
                btn = row.select_one("button.js-conditions")
                condition = btn.get_text(strip=True) if btn else specs.get("제품 컨디션", "")
                break

        description_tag = soup.select_one("span.js-watch-notes")
        description = description_tag.get_text(strip=True) if description_tag else ""

        return {
            "brand":            specs.get("브랜드", ""),
            "model":            specs.get("모델", ""),
            "ref":              specs.get("인증 번호", ""),
            "movement":         specs.get("무브먼트", ""),
            "case_material":    specs.get("케이스 소재", ""),
            "strap_material":   specs.get("시계줄 소재", ""),
            "bracelet_color":   specs.get("브레이슬릿 색상", ""),
            "clasp":            specs.get("잠금장치", ""),
            "year":             specs.get("생산 연도", ""),
            "condition":        condition,
            "accessories":      specs.get("구성품", ""),
            "gender":           specs.get("성별", ""),
            "location_detail":  specs.get("위치", ""),
            "price_detail":     specs.get("가격", ""),
            "case_diameter":    specs.get("케이스 지름", ""),
            "water_resistance": specs.get("방수", ""),
            "bezel_material":   specs.get("베젤 소재", ""),
            "glass":            specs.get("유리", ""),
            "dial":             specs.get("다이얼", ""),
            "dial_numbers":     specs.get("다이얼번호", ""),
            "caliber":          specs.get("무브먼트/칼리버", ""),
            "power_reserve":    specs.get("파워리저브", ""),
            "jewels":           specs.get("보석의 갯수", ""),
            "description":      description,
            "detail_url":       url,
            "detail_fetched":   True,
            "date":             datetime.datetime.now().strftime("%Y-%m-%d"),
        }

    def fetch_multi_pages(self, brand: str, start_page: int = 1, end_page: int = 10,
                          page_size: int = 120, fetch_detail: bool = True,
                          save_callback=None) -> List[Dict]:
        all_results = []

        for page in range(start_page, end_page + 1):
            print(f"\n{'='*50}")
            print(f"🕐 [{brand.upper()}] 페이지 {page}/{end_page}")

            items = self.fetch_page(brand, page, page_size)
            if not items:
                print(f"  ⚠️ 결과 없음, 중단")
                break

            if fetch_detail:
                for i, item in enumerate(items):
                    print(f"  📋 상세 [{i+1}/{len(items)}] {item.get('title', '')[:40]}")
                    detail = self.fetch_detail(item["detail_url"])
                    item.update(detail)
                    time.sleep(random.uniform(0.2, 0.3))

            if save_callback and items:
                save_callback(items)

            all_results.extend(items)

            if page < end_page:
                delay = random.uniform(0.2, 0.3)
                print(f"\n⏳ {delay:.1f}초 대기...")
                time.sleep(delay)

        return all_results

    def close(self):
        self.driver.quit()


if __name__ == "__main__":
    client = MongoClient(MONGO_URI)
    collection = client["watchdb"]["chrono24"]

    def save_to_mongo(items: List[Dict]):
        for item in items:
            try:
                collection.update_one(
                    {"detail_url": item["detail_url"]},
                    {"$set": item},
                    upsert=True,
                )
            except Exception as e:
                print(f"  ⚠️ 저장 오류: {e}")
        print(f"  ✅ {len(items)}개 저장 완료")

    scraper = Chrono24SeleniumScraper(headless=True, debug=False)
    try:
        brands = ["rolex", "omega", "audemarspiguet", "patekphilippe", "richardmille", "cartier"]
        for brand in brands:
            print(f"\n{'#'*60}")
            print(f"# {brand.upper()}")
            print(f"{'#'*60}")
            scraper.fetch_multi_pages(
                brand=brand,
                start_page=1,
                end_page=3,
                page_size=120,
                fetch_detail=True,
                save_callback=save_to_mongo,
            )
            time.sleep(random.uniform(0.2, 0.3))
    finally:
        scraper.close()
        client.close()
        print("\n🎉 Chrono24 크롤링 완료!")
