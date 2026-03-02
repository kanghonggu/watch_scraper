import os
import random
import re
import time
import urllib.parse as urlparse
from datetime import datetime, timezone, timedelta
from typing import List, Dict

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from pymongo import MongoClient
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class NaverCafeScraper:
    def __init__(self, headless: bool = False):
        options = uc.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-notifications")
        options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.popups": 1,
            "profile.managed_default_content_settings.popups": 1,
            "profile.default_content_setting_values.notifications": 2
        })

        # 프로젝트 내 chromedriver 사용
        driver_path = os.environ.get("CHROMEDRIVER_PATH") or os.path.join(os.path.dirname(__file__), "chromedriver")
        self.driver = uc.Chrome(options=options, driver_executable_path=driver_path)

    def login_with_cookies(self, cookie_path: str = "naver_cookies.pkl"):
        """S3에서 쿠키 다운로드 후 로그인"""
        import pickle
        import boto3
        print("🍪 S3에서 쿠키 다운로드 중...")

        # 로컬에 없으면 S3에서 다운로드
        if not os.path.exists(cookie_path):
            s3 = boto3.client("s3", region_name="ap-northeast-2")
            s3.download_file(
                "naver-pkl",  # ← 버킷 이름
                "naver_cookies.pkl",
                cookie_path
            )
            print("✅ S3 다운로드 완료")

        self.driver.get("https://www.naver.com")
        time.sleep(2)

        with open(cookie_path, "rb") as f:
            cookies = pickle.load(f)

        for cookie in cookies:
            try:
                self.driver.add_cookie(cookie)
            except Exception:
                pass

        self.driver.refresh()
        time.sleep(2)
        print("✅ 쿠키 로그인 완료")


    def _normalize_menu_url(self, menu_url: str) -> str:
        m = re.search(r"/cafes/(\d+)/menus/(\d+)", menu_url)
        if m:
            clubid, menuid = m.group(1), m.group(2)
            return f"https://cafe.naver.com/ArticleList.nhn?search.clubid={clubid}&search.menuid={menuid}&search.boardtype=L"
        return menu_url

    def _switch_into_cafe_iframe(self, timeout: int = 10) -> bool:
        self.driver.switch_to.default_content()
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "iframe#cafe_main"))
            )
            iframe = self.driver.find_element(By.CSS_SELECTOR, "iframe#cafe_main")
            self.driver.switch_to.frame(iframe)
            return True
        except Exception:
            return False

    def _is_notice(self, title: str, link: str) -> bool:
        title_lower = (title or "").lower()
        notice_keywords = [
            "거래파기방지", "사기방지", "필수사항", "글양식", "삭제됩니다", "로렉스 거래 규정", "성골 매칭", "공지"
        ]
        if any(k.lower() in title_lower for k in notice_keywords):
            return True

        known_notice_ids = {"1087451", "202977", "20347"}
        m = re.search(r"/sweetdressroom/(\d+)", link or "")
        if m and m.group(1) in known_notice_ids:
            return True

        return False

    def _build_paged_url(self, base_url: str, page: int, size: int) -> str:
        parsed = urlparse.urlparse(base_url)
        q = dict(urlparse.parse_qsl(parsed.query))
        q["page"] = str(page)
        q["size"] = str(size)
        new_query = urlparse.urlencode(q)
        return urlparse.urlunparse(parsed._replace(query=new_query))

    def _has_new_badge(self, a_tag) -> bool:
        badge_in_self = a_tag.select_one("em.BadgeNotificationNew_wrap__anNWw span.blind")
        if badge_in_self and "새 게시글 있음" in badge_in_self.get_text(strip=True):
            return True
        parent = a_tag.parent
        try:
            badge_in_parent = parent.select_one("em.BadgeNotificationNew_wrap__anNWw span.blind")
            if badge_in_parent and "새 게시글 있음" in badge_in_parent.get_text(strip=True):
                return True
        except Exception:
            pass
        return False

    def fetch_posts_page(self, menu_url: str, page: int = 1, size: int = 50, max_results: int = 100, date: str = '') -> List[Dict]:
        url = self._build_paged_url(menu_url, page=page, size=size)
        print(f"📄 카페 메뉴 접속: {url}")
        self.driver.get(url)

        _ = self._switch_into_cafe_iframe(timeout=15)

        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.article"))
            )
        except Exception:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

        time.sleep(random.uniform(2, 4))
        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        items = soup.select("a.article")

        new_items = [el for el in items if self._has_new_badge(el)]

        posts: List[Dict] = []

        for el in new_items[:max_results]:
            title = el.get_text(strip=True)
            href = el.get("href", "")
            link = "https://cafe.naver.com" + href if href.startswith("/") else href

            if self._is_notice(title, link):
                continue

            content = self.fetch_detail(link)

            posts.append({
                "title": title,
                "link": link,
                "content": content,
                "date": date
            })

        return posts

    def fetch_detail(self, post_url: str) -> str:
        print(f"🔎 상세 크롤링: {post_url}")
        self.driver.get(post_url)

        in_iframe = self._switch_into_cafe_iframe(timeout=15)
        if not in_iframe:
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        time.sleep(random.uniform(2, 4))
        soup = BeautifulSoup(self.driver.page_source, "html.parser")

        content_tag = soup.select_one("div.se-main-container") or soup.select_one("div#tbody")
        return content_tag.get_text("\n", strip=True) if content_tag else ""

    def fetch_posts_until_no_new(self, menu_url: str, start_page: int = 1, page_size: int = 50,
                                 per_page_limit: int = 200, hard_max_pages: int = 100) -> List[Dict]:
        all_posts: List[Dict] = []
        page = start_page

        kst = timezone(timedelta(hours=9))
        date = datetime.now(tz=kst).strftime("%Y-%m-%d")

        while page - start_page < hard_max_pages:
            print(f"🔎 페이지 {page} 수집 중...")
            page_posts = self.fetch_posts_page(menu_url, page=page, size=page_size, max_results=per_page_limit, date=date)
            if not page_posts:
                print(f"✅ 페이지 {page}에 새 게시글 배지가 없습니다. 수집 종료.")
                break
            all_posts.extend(page_posts)
            page += 1
            time.sleep(random.uniform(1.5, 3.0))

        return all_posts

    def close(self):
        self.driver.quit()


if __name__ == "__main__":
    MONGO_URI = "mongodb+srv://test:2RGdjwLiJyuzFwWn@super-mongo.zizsavi.mongodb.net?retryWrites=true&w=majority&appName=super-mongo"
    client = MongoClient(MONGO_URI)
    db = client["watchdb"]

    scraper = NaverCafeScraper(headless=True)
    try:
        scraper.login_with_cookies("naver_cookies.pkl")

        base_menu_url = "https://cafe.naver.com/f-e/cafes/18629593/menus/832?page=1&size=50&headId=1400"
        posts = scraper.fetch_posts_until_no_new(
            menu_url=base_menu_url,
            start_page=1,
            page_size=50
        )
        print(f"총 {len(posts)}개 게시글 수집됨")

        if posts:
            db["naver_cafe"].insert_many(posts)
            print("✅ MongoDB 저장 완료")

        for p in posts:
            print(p)

    finally:
        scraper.close()
        client.close()