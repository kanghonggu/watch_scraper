import time, random
from typing import List, Dict
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pymongo import MongoClient


# =============================
# Chrono24 Scraper
# =============================
class Chrono24SeleniumScraper:
    def __init__(self, headless: bool = True):
        options = uc.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        self.driver = uc.Chrome(options=options)

    def fetch_page(self, brand: str, page: int = 1, page_size: int = 60) -> List[Dict]:
        base_url = "https://www.chrono24.com"
        url = f"{base_url}/{brand}/index-{page}.html?pageSize={page_size}"
        print(f"📄 [Chrono24] Opening {url}")
        self.driver.get(url)

        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div#wt-watches a.js-article-item"))
            )
        except Exception as e:
            print(f"❌ [Chrono24] Timeout on {brand} page {page}: {e}")
            return []

        time.sleep(random.uniform(2, 4))
        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        items = soup.select("div#wt-watches a.js-article-item")

        results: List[Dict] = []
        for el in items:
            title_tag = el.select_one(".text-sm.text-sm-md.text-ellipsis.m-b-2")
            price_tag = el.select_one("div.d-flex.justify-content-between.m-b-1 div.text-bold")

            img_tag = el.select_one("div.js-scroll-container.scroll-container img")

            results.append({
                "brand": brand,
                "title": title_tag.get_text(strip=True) if title_tag else "",
                "price": price_tag.get_text(strip=True) if price_tag else "",
                "link": base_url + el.get("href", ""),
                "image": img_tag.get("data-lazy-sweet-spot-master-src", "").replace("_SIZE_", "480") if img_tag else "",
                "source": "chrono24"
            })
        return results

    def fetch_multi_pages(self, brand: str, start_page: int = 1, end_page: int = 2, page_size: int = 60) -> List[Dict]:
        all_results = []
        for page in range(start_page, end_page + 1):
            page_results = self.fetch_page(brand, page, page_size)
            if not page_results:
                break
            all_results.extend(page_results)
            time.sleep(random.uniform(3, 6))
        return all_results

    def close(self):
        self.driver.quit()


# =============================
# Daangn Scraper
# =============================
class DaangnScraper:
    def __init__(self, driver):
        self.driver = driver

    def fetch(self, region_in: str, search: str, max_results: int = 20) -> List[Dict]:
        url = f"https://www.daangn.com/kr/buy-sell/?in={region_in}&only_on_sale=true&search={search}"
        print(f"📄 [Daangn] Opening {url}")
        self.driver.get(url)

        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(random.uniform(2, 4))

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        results: List[Dict] = []
        articles = soup.select("a")

        for el in articles:
            title_tag = el.select_one("span.sprinkles_fontWeight_regular__1byufe81x")
            price_tag = el.select_one("span.sprinkles_fontWeight_bold__1byufe81z")
            if not title_tag or not price_tag:
                continue

            results.append({
                "title": title_tag.get_text(strip=True),
                "price": price_tag.get_text(strip=True),
                "link": "https://www.daangn.com" + el.get("href", ""),
                "image": el.select_one("img")["src"] if el.select_one("img") else "",
                "source": "daangn",
                "region": region_in,
                "keyword": search
            })

            if len(results) >= max_results:
                break

        return results


# =============================
# Main Execution
# =============================
if __name__ == "__main__":
    # MongoDB 연결
    client = MongoClient("mongodb://localhost:27017")
    db = client["watchdb"]

    # 크롬 드라이버 1개 공유
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    driver = uc.Chrome(options=options)

    try:
        chrono_scraper = Chrono24SeleniumScraper(headless=False)
        daangn_scraper = DaangnScraper(driver)

        # =========================
        # Chrono24 크롤링 (여러 브랜드)
        # =========================
        brands = ["rolex", "omega", "audemarspiguet", "patekphilippe", "richardmille", "cartier"]
        for brand in brands:
            data = chrono_scraper.fetch_multi_pages(brand, start_page=1, end_page=10, page_size=120)
            if data:
                db["chrono24"].insert_many(data)
                print(f"✅ [Chrono24] {brand} {len(data)}개 저장 완료")

        # =========================
        # Daangn 크롤링 (예시)
        # =========================
        daangn_data = daangn_scraper.fetch(region_in="청담동-386", search="명품시계", max_results=100)
        if daangn_data:
            db["daangn"].insert_many(daangn_data)
            print(f"✅ [Daangn] {len(daangn_data)}개 저장 완료")

    finally:
        chrono_scraper.close()
        driver.quit()
