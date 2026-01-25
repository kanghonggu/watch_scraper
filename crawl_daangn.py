import time, random
from typing import List, Dict
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pymongo import MongoClient


class DaangnScraper:
    def __init__(self, headless: bool = True):
        options = uc.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")

        self.driver = uc.Chrome(options=options)

    def fetch(self, region_in: str, search: str, max_results: int = 20) -> List[Dict]:
        """
        당근마켓 매물 크롤링
        :param region_in: 지역 코드 (예: 청담동-386)
        :param search: 검색어 (예: 명품시계)
        :param max_results: 가져올 최대 개수
        """
        url = f"https://www.daangn.com/kr/buy-sell/?in={region_in}&only_on_sale=true&search={search}"
        print(f"📄 Opening {url}")
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

            title = title_tag.get_text(strip=True)
            price = price_tag.get_text(strip=True)
            link = "https://www.daangn.com" + el.get("href", "")
            img_tag = el.select_one("img")
            img = img_tag["src"] if img_tag else ""

            results.append({
                "title": title,
                "price": price,
                "link": link,
                "image": img,
                "source": "daangn",
                "region": region_in,
                "keyword": search
            })

            if len(results) >= max_results:
                break

        return results

    def close(self):
        self.driver.quit()


if __name__ == "__main__":
    # MongoDB 연결
    client = MongoClient("mongodb://localhost:27017")
    db = client["watchdb"]

    scraper = DaangnScraper(headless=False)  # 서버에서는 True 권장
    try:
        data = scraper.fetch(region_in="청담동-386", search="명품시계", max_results=10)
        print(f"총 {len(data)}개 아이템 크롤링됨")

        if data:
            db["daangn"].insert_many(data)
            print(f"MongoDB에 {len(data)}개 저장 완료")

        # 샘플 출력
        for d in data[:5]:
            print(d)

    finally:
        scraper.close()
