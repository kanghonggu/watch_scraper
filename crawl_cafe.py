import time, random
from typing import List, Dict
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pymongo import MongoClient
import re
import urllib.parse as urlparse
from datetime import datetime, timezone, timedelta


class NaverCafeScraper:
    def __init__(self, headless: bool = False):
        options = uc.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-popup-blocking")  # 팝업 차단 해제
        options.add_argument("--disable-notifications")  # 알림 비활성화
        # 팝업 및 권한 프롬프트 허용
        options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.popups": 1,
            "profile.managed_default_content_settings.popups": 1,
            "profile.default_content_setting_values.notifications": 2
        })

        # version_main 고정 해제(크롬 버전 불일치 이슈 방지)
        self.driver = uc.Chrome(options=options, version_main=142)

    def login(self, user_id: str, user_pw: str):
        """네이버 로그인"""
        print("🔑 네이버 로그인 중...")
        self.driver.get("https://nid.naver.com/nidlogin.login")

        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.ID, "id"))
        )
        self.driver.execute_script("document.getElementById('id').value = arguments[0]", user_id)
        self.driver.execute_script("document.getElementById('pw').value = arguments[0]", user_pw)

        self.driver.find_element(By.ID, "log.login").click()
        time.sleep(5)  # OTP, 보안문자 있을 경우 수동 처리 필요

    def _normalize_menu_url(self, menu_url: str) -> str:
        """
        새 UI URL(/cafes/{clubid}/menus/{menuid})을 구형 ArticleList로 변환.
        iframe(cafe_main) 일관성 확보.
        """
        m = re.search(r"/cafes/(\d+)/menus/(\d+)", menu_url)
        if m:
            clubid, menuid = m.group(1), m.group(2)
            return f"https://cafe.naver.com/ArticleList.nhn?search.clubid={clubid}&search.menuid={menuid}&search.boardtype=L"
        return menu_url

    def _switch_into_cafe_iframe(self, timeout: int = 10) -> bool:
        """
        iframe#cafe_main이 있으면 전환. 없으면 False 반환.
        """
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
        """
        공지/안내성 글을 제목 키워드 및 알려진 URL로 필터링
        """
        title_lower = (title or "").lower()
        notice_keywords = [
            "거래파기방지", "사기방지", "필수사항", "글양식", "삭제됩니다", "로렉스 거래 규정", "성골 매칭", "공지"
        ]
        if any(k.lower() in title_lower for k in notice_keywords):
            return True

        # 알려진 공지 URL(게시글 ID)
        known_notice_ids = {"1087451", "202977", "20347"}
        m = re.search(r"/sweetdressroom/(\d+)", link or "")
        if m and m.group(1) in known_notice_ids:
            return True

        return False



    def _build_paged_url(self, base_url: str, page: int, size: int) -> str:
        """
        modern 메뉴 URL(/cafes/{clubid}/menus/{menuid})를 그대로 사용하면서 page/size 쿼리를 갱신
        """
        parsed = urlparse.urlparse(base_url)
        q = dict(urlparse.parse_qsl(parsed.query))
        q["page"] = str(page)
        q["size"] = str(size)
        new_query = urlparse.urlencode(q)
        return urlparse.urlunparse(parsed._replace(query=new_query))

    def _has_new_badge(self, a_tag) -> bool:
        """
        a.article 요소에 '새 게시글 있음' 배지가 있는지 확인
        """
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
        """
        특정 page에서 '새 게시글 있음' 배지가 붙은 게시글만 수집
        """
        url = self._build_paged_url(menu_url, page=page, size=size)
        print(f"📄 카페 메뉴 접속: {url}")
        self.driver.get(url)

        # (구형) iframe일 수 있으므로 안전하게 전환 시도
        _ = self._switch_into_cafe_iframe(timeout=15)

        # 리스트 로드 대기
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

        # 새 게시글 배지 있는 항목만 필터
        new_items = [el for el in items if self._has_new_badge(el)]

        posts: List[Dict] = []

        for el in new_items[:max_results]:
            title = el.get_text(strip=True)
            href = el.get("href", "")
            link = "https://cafe.naver.com" + href if href.startswith("/") else href

            # 공지/안내 글 제외
            if self._is_notice(title, link):
                continue

            content = self.fetch_detail(link)

            posts.append({
                "title": title,
                "link": link,
                "content": content,
                "date" : date
            })

        return posts



    def fetch_detail(self, post_url: str) -> str:
        """게시글 상세 본문 크롤링"""
        print(f"🔎 상세 크롤링: {post_url}")
        self.driver.get(post_url)

        # 상세도 (구형) iframe 구조를 우선 시도
        in_iframe = self._switch_into_cafe_iframe(timeout=15)
        if not in_iframe:
            # iframe이 없을 수도 있으니 body 로드까지만 대기
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        time.sleep(random.uniform(2, 4))
        soup = BeautifulSoup(self.driver.page_source, "html.parser")

        # 스마트에디터 or 구에디터 처리
        content_tag = soup.select_one("div.se-main-container") or soup.select_one("div#tbody")
        return content_tag.get_text("\n", strip=True) if content_tag else ""

    def close(self):
        self.driver.quit()


    def fetch_posts_until_no_new(self, menu_url: str, start_page: int = 1, page_size: int = 50,
                                 per_page_limit: int = 200, hard_max_pages: int = 100) -> List[Dict]:
        """
        start_page부터 시작해서 '새 게시글 있음' 배지가 더 이상 나오지 않는 페이지를 만날 때까지 순회 수집
        - per_page_limit: 페이지당 최대 수집 수(보호용)
        - hard_max_pages: 무한 루프 방지 하드 상한
        """
        all_posts: List[Dict] = []
        page = start_page

        kst = timezone(timedelta(hours=9))
        date =  datetime.now(tz=kst).strftime("%Y-%m-%d")
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



# ... existing code ...
if __name__ == "__main__":
    client = MongoClient("mongodb://localhost:27017")
    db = client["watchdb"]

    scraper = NaverCafeScraper(headless=False)
    try:
        NAVER_ID = ""
        NAVER_PW = ""

        scraper.login(NAVER_ID, NAVER_PW)

        # page=1부터 시작해서 '새 게시글 있음'이 더 이상 없을 때까지 크롤링
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
