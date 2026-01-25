import time
import random
from typing import List, Dict
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class Chrono24SeleniumScraper:
    def __init__(self, headless: bool = True):
        options = uc.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        self.driver = uc.Chrome(options=options)

    def fetch_page(self, brand: str, page: int = 1, group_str: str = "", page_size: int = 60) -> List[Dict[str, str]]:
        """Chrono24 특정 페이지 크롤링"""
        base_url = "https://www.chrono24.com"
        url = f"{base_url}/{brand}/index-{page}.html?pageSize={page_size}"
        print(f"📄 Opening {url}")
        self.driver.get(url)

        # 상품 영역이 로드될 때까지 대기
        WebDriverWait(self.driver, 20).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div#wt-watches a.js-article-item"))
        )
        time.sleep(random.uniform(2, 4))  # 자연스러운 대기

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        values = soup.select("div#wt-watches a.js-article-item")

        results: List[Dict[str, str]] = []
        for element in values:
            link = base_url + element.get("href", "")

            image = element.select_one("div.js-scroll-container.scroll-container img")

            image_url = ""
            if image:
                image_url = image.get("data-lazy-sweet-spot-master-src", "").replace("_SIZE_", "480")

            title = element.select_one(".text-sm.text-sm-md.text-ellipsis.m-b-2")
            name = title.get_text(strip=True) if title else ""

            price_tag = element.select_one(
                "div.d-flex.justify-content-between.m-b-1 div.text-bold"
            )
            price = price_tag.get_text(strip=True) if price_tag else ""

            results.append({
                "url": link,
                "image": image_url,
                "name": name,
                "brand": brand,
                "group": group_str,
                "price": price,
                "source": "chrono24"
            })

        return results

    def fetch_multi_pages(self, brand: str, start_page: int = 1, end_page: int = 3,
                          group_str: str = "", page_size: int = 60) -> List[Dict[str, str]]:
        """Chrono24 여러 페이지 크롤링"""
        all_results: List[Dict[str, str]] = []
        for page in range(start_page, end_page + 1):
            print(f"🔎 Fetching page {page}...")
            try:
                page_results = self.fetch_page(brand, page, group_str, page_size)
                if not page_results:
                    print(f"⚠️ No results on page {page}, stopping early.")
                    break
                all_results.extend(page_results)
                time.sleep(random.uniform(3, 6))  # 페이지 간 간격
            except Exception as e:
                print(f"❌ Error on page {page}: {e}")
                break
        return all_results

    def close(self):
        self.driver.quit()


if __name__ == "__main__":
    scraper = Chrono24SeleniumScraper(headless=True)
    try:
        # 1~3 페이지 크롤링
        data = scraper.fetch_multi_pages("rolex", start_page=1, end_page=3, group_str="luxury", page_size=60)
        print(f"총 {len(data)}개 아이템 크롤링됨")
        for d in data[:5]:  # 처음 5개만 출력
            print(d)
    finally:
        scraper.close()