import os
import random
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Set, Tuple

import undetected_chromedriver as uc
from pymongo import MongoClient
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# 상세 파싱 외부 모듈
from viver_detail import parse_detail


def _kst_today_iso() -> str:
    kst = timezone(timedelta(hours=9))
    return datetime.now(tz=kst).strftime("%Y-%m-%d")

def _dedup_by_url(items: List[Dict]) -> List[Dict]:
    seen: Set[str] = set()
    out: List[Dict] = []
    for it in items:
        u = it.get("url", "")
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(it)
    return out


def save_to_mongo(items: List[Dict],
                  mongo_uri: str = "mongodb://localhost:27017",
                  db_name: str = "watchdb",
                  collection_name: str = "viver") -> int:
    if not items:
        return 0
    client = MongoClient(mongo_uri)
    db = client[db_name]
    coll = db[collection_name]
    docs = _dedup_by_url(items)
    if not docs:
        return 0
    res = coll.insert_many(docs)
    return len(res.inserted_ids)


def _detect_chrome_major_version() -> Optional[int]:
    """
    로컬 Chrome 실행 파일의 메이저 버전을 감지하여 반환
    """
    candidates = []

    env_path = os.environ.get("CHROME_PATH") or os.environ.get("GOOGLE_CHROME_BIN")
    if env_path:
        candidates.append(env_path)

    # macOS
    candidates.extend([
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta",
        "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    ])

    # PATH 내 바이너리
    for name in ["google-chrome", "chrome", "chromium", "chromium-browser", "chrome.exe", "GoogleChromePortable.exe"]:
        p = shutil.which(name)
        if p:
            candidates.append(p)

    seen = set()
    uniq = [c for c in candidates if c and os.path.exists(c) and (c not in seen and not seen.add(c))]

    for bin_path in uniq:
        try:
            out = subprocess.check_output([bin_path, "--version"], stderr=subprocess.STDOUT, text=True, timeout=5)
            m = re.search(r"(\d+)\.\d+\.\d+\.\d+", out)
            if m:
                return int(m.group(1))
        except Exception:
            continue
    return None






class ViverSeleniumScraper:
    def __init__(self, headless: bool = True):
        options = uc.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-notifications")

        major = _detect_chrome_major_version()
        try:
            if major:
                print(f"[Driver] Detected Chrome major version: {major}. Pinning ChromeDriver.")
                self.driver = uc.Chrome(options=options, version_main=major)
            else:
                print("[Driver] Could not detect Chrome version. Initializing default undetected_chromedriver.")
                self.driver = uc.Chrome(options=options)
        except Exception as e:
            print(f"[Driver] Init with version pinning failed: {e}. Retrying without version_main...")
            self.driver = uc.Chrome(options=options)

    # 상세 페이지가 완전히 렌더링될 때까지 대기
    def _wait_for_detail_ready(self, timeout: int = 25, min_stable_time: float = 0.8):
        # 1) 문서 준비완료
        WebDriverWait(self.driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        # 2) 핵심 요소(제목/가격/상품명) 등장 대기
        key_selectors = [
            "h1, .product-title, .prd-name, .title, h4.sc-aXZVg.sc-cDltVh.kBNPNG.bMwTGV",
            ".xans-product-detail .price, .product-price, .prd-price, [class*='price']",
            "meta[property='og:title'], meta[property='product:price:amount']",
        ]
        try:
            WebDriverWait(self.driver, max(5, timeout // 2)).until(
                lambda d: any(d.find_elements(By.CSS_SELECTOR, sel) for sel in key_selectors)
            )
        except TimeoutException:
            pass
        # 3) DOM 안정화(HTML 길이 유지)
        start = time.time()
        last_len = -1
        stable_start = None
        while time.time() - start < timeout:
            try:
                cur_len = len(self.driver.execute_script("return document.body.innerHTML || ''"))
            except Exception:
                cur_len = 0
            if cur_len == last_len:
                if stable_start is None:
                    stable_start = time.time()
                elif time.time() - stable_start >= min_stable_time:
                    return
            else:
                stable_start = None
                last_len = cur_len
            time.sleep(0.1)



    # ---------- 상세 페이지 추출 ----------
    def _extract_detail_from_current_page(self, fallback_base_url: str) -> Dict:
        WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        self._wait_for_detail_ready(timeout=25, min_stable_time=0.8)

        html = self.driver.page_source
        item = parse_detail(html, fallback_base_url=fallback_base_url)
        # 실제 URL로 덮어쓰기
        item["url"] = self.driver.current_url or fallback_base_url
        return item

    # ---------- 목록 내 타겟 요소 탐색(강화된 로케이터) ----------
    def _wait_and_collect_targets(self, timeout: int = 10):
        """
        css-g5y9jx r-1loqt21 r-1otgn73 조합을 다양한 로케이터로 탐색
        반환: 요소 리스트(중복 제거)
        """
        locators = [
            (By.CSS_SELECTOR, ".css-g5y9jx.r-1loqt21.r-1otgn73"),
            (By.CSS_SELECTOR, "[class*='css-g5y9jx'][class*='r-1loqt21'][class*='r-1otgn73']"),
        ]
        elements = []
        seen_ids = set()
        for by, sel in locators:
            try:
                found = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_all_elements_located((by, sel))
                )
                for el in found:
                    key = getattr(el, "id", id(el))
                    if key not in seen_ids:
                        seen_ids.add(key)
                        elements.append(el)
            except TimeoutException:
                continue
        if not elements:
            try:
                found = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_all_elements_located((
                        By.XPATH,
                        "//*[contains(@class,'css-g5y9jx') and contains(@class,'r-1loqt21') and contains(@class,'r-1otgn73')]"
                    ))
                )
                for el in found:
                    key = getattr(el, "id", id(el))
                    if key not in seen_ids:
                        seen_ids.add(key)
                        elements.append(el)
            except TimeoutException:
                pass

        # 내부 텍스트가 있는 요소만 필터링 (보이는 요소 우선)
        filtered_elements = []
        for el in elements:
            try:
                txt = (el.text or "").strip()
                visible = False
                try:
                    visible = el.is_displayed()
                except Exception:
                    visible = True  # 표시 여부 판단 실패 시 텍스트만으로 필터
            except Exception:
                txt = ""
                visible = False
            if txt and visible:
                filtered_elements.append(el)

        # 디버그 로그: 텍스트가 있는 요소만 출력
        try:
            print(f"[DEBUG] .css-g5y9jx.r-1loqt21.r-1otgn73 (text-present) count: {len(filtered_elements)}")
            for idx, el in enumerate(filtered_elements):
                try:
                    cls = el.get_attribute("class") or ""
                except Exception:
                    cls = ""
                try:
                    txt = (el.text or "").strip()
                except Exception:
                    txt = ""
                if len(txt) > 80:
                    txt = txt[:77] + "..."
                try:
                    href = self._get_href_from_element(el)
                except Exception:
                    href = ""
                print(f"  [DEBUG] [{idx}] class='{cls}' | text='{txt}' | href='{href}'")
        except Exception:
            print("[DEBUG] Failed to log elements with text for .css-g5y9jx.r-1loqt21.r-1otgn73")

        return filtered_elements


    def _get_href_from_element(self, el):
        # 가장 가까운 a 조상 혹은 자신/자식의 a를 탐색하여 href 확보
        try:
            a = el.find_element(By.XPATH, "./ancestor-or-self::a[1]")
            href = a.get_attribute("href") or ""
            if href:
                return href
        except Exception:
            pass
        try:
            a2 = el.find_element(By.CSS_SELECTOR, "a[href]")
            href = a2.get_attribute("href") or ""
            if href:
                return href
        except Exception:
            pass
        try:
            card = self._get_card_ancestor(el)
            a3 = card.find_element(By.CSS_SELECTOR, "a[href]")
            href = a3.get_attribute("href") or ""
            if href:
                return href
        except Exception:
            pass
        return ""

    def _get_card_ancestor(self, el):
        """
        클릭 대상 요소에서 카드 래퍼를 추정(오늘 등록 배지 검사용)
        """
        xpaths = [
            "./ancestor::li[contains(@class,'item') or contains(@class,'prd')][1]",
            "./ancestor::article[1]",
            "./ancestor::div[contains(@class,'item') or contains(@class,'product')][1]",
            "./ancestor::*[self::li or self::article or self::div][1]",
        ]
        for xp in xpaths:
            try:
                return el.find_element(By.XPATH, xp)
            except Exception:
                continue
        return el  # 실패 시 자기 자신

    def _is_today_card(self, el) -> bool:
        """
        정확한 '오늘 등록' 배지 감지:
        <div class="css-146c3p1 r-159m18f r-10x49cs r-16dba41 r-1vglu5a">오늘 등록</div>
        """
        try:
            card = self._get_card_ancestor(el)
            # 정확한 클래스 조합으로 "오늘 등록" 텍스트 확인
            try:
                badge_el = card.find_element(By.CSS_SELECTOR, "div.css-146c3p1.r-159m18f.r-10x49cs.r-16dba41.r-1vglu5a")
                badge_text = (badge_el.text or "").strip()
                if "오늘 등록" in badge_text:
                    return True
            except Exception:
                pass

            try:
                if "오늘 등록" in (card.text or ""):
                    return True
            except Exception:
                pass
                # 보조: 어떤 요소든 텍스트 매칭
            try:
                badges = card.find_elements(By.XPATH, ".//*[contains(normalize-space(.), '오늘 등록')]")
                if badges:
                    return True
            except Exception:
                pass
            return False
        except Exception:
            return False

    # ---------- 메인 플로우 ----------
    def fetch_list(self,
                   start_url: str = "https://www.viver.co.kr/shop",
                   max_pages: int = 50,
                   only_today: bool = True,
                   sleep_range: Tuple[float, float] = (1.0, 2.0)) -> List[Dict]:
        """
        리스트의 각 요소를 '클릭 → 상세 파싱 → 뒤로' 방식으로 처리
        only_today=True면 '오늘 등록'이 표시된 카드만 대상으로 클릭
        """
        seen_urls: Set[str] = set()
        results: List[Dict] = []
        current_url = start_url
        pages_crawled = 0
        today = _kst_today_iso()

        while current_url and pages_crawled < max_pages:
            if current_url in seen_urls:
                break
            seen_urls.add(current_url)

            print(f"📄 [Viver] Opening {current_url}")
            self.driver.get(current_url)
            try:
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except Exception:
                print("⚠️ body 대기 타임아웃, 계속 진행합니다.")

            # 충분히 스크롤하여 더 많은 항목 로드
            time.sleep(random.uniform(*sleep_range))
            print("🔄 Scrolling to load more items...")

            # 대상 요소 수집(재조회 전제)
            targets = self._wait_and_collect_targets(timeout=10)
            print(f"  - Found {len(targets)} candidate clickable elements (.css-g5y9jx.r-1loqt21.r-1otgn73)")

            idx = 0
            extracted = 0
            while True:
                # 매 루프마다 재조회하여 Stale 방지
                try:
                    current_targets = self._wait_and_collect_targets(timeout=5)
                except Exception:
                    current_targets = []
                if idx >= len(current_targets):
                    break

                el = current_targets[idx]
                idx += 1

                # 오늘 등록 필터
                if only_today and not self._is_today_card(el):
                    continue

                # 스크롤 중앙 정렬
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                except Exception:
                    pass

                # 클릭/네비게이션 시도 (URL 변경 보장)
                try:
                    href = ""
                    try:
                        href = self._get_href_from_element(el)
                    except Exception:
                        href = ""

                    prev_url = self.driver.current_url
                    # 1) 기본 클릭
                    try:
                        WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(el))
                        el.click()
                    except Exception:
                        try:
                            self.driver.execute_script("arguments[0].click();", el)
                        except Exception:
                            pass

                    # 2) URL 변경 대기
                    navigated = False
                    try:
                        WebDriverWait(self.driver, 8).until(lambda d: d.current_url != prev_url)
                        navigated = True
                    except Exception:
                        navigated = False

                    # 3) 실패 시 href로 강제 이동
                    if not navigated and href:
                        self.driver.get(href)
                        try:
                            WebDriverWait(self.driver, 10).until(
                                EC.presence_of_element_located((By.TAG_NAME, "body"))
                            )
                            navigated = self.driver.current_url != prev_url
                        except Exception:
                            pass

                    if not navigated:
                        # 목록으로 복구하고 다음 대상으로 진행
                        print("    ⚠️ Navigation did not occur; skipping this element.")
                        try:
                            self.driver.get(current_url)
                            WebDriverWait(self.driver, 10).until(
                                EC.presence_of_element_located((By.TAG_NAME, "body"))
                            )
                        except Exception:
                            pass
                        continue

                    # 상세 파싱 (안정화 대기 포함)
                    try:
                        item = self._extract_detail_from_current_page(current_url)
                        if item:
                            item["date"] = today
                            results.append(item)
                            extracted += 1
                    except Exception as e:
                        print(f"    ⚠️ Detail extraction error: {e}")

                    # 뒤로가기 및 안정화
                    try:
                        self.driver.back()
                        WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                        try:
                            self.driver.execute_script("window.scrollBy(0, 200);")
                        except Exception:
                            pass
                        time.sleep(random.uniform(*sleep_range))
                    except Exception as e:
                        print(f"    ⚠️ Back navigation failed: {e}")
                        try:
                            self.driver.get(current_url)
                            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                            time.sleep(random.uniform(*sleep_range))
                        except Exception:
                            pass

                except Exception as e:
                    print(f"    ⚠️ Click navigation failed: {e}")
                    try:
                        self.driver.get(current_url)
                        WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                    except Exception:
                        pass
                    continue

            print(f"  - Extracted {extracted} items on this page")

            # 무한 스크롤 모드: 추가 페이징 없음
            print("✅ Infinite-scroll mode: no pagination. Stopping after current page.")
            break

        return results

    def close(self):
        """브라우저 드라이버를 안전하게 종료합니다."""
        try:
            driver = getattr(self, "driver", None)
            if driver:
                driver.quit()
        finally:
            # 드라이버 참조 해제 (가비지 컬렉션 및 재사용 혼동 방지)
            try:
                setattr(self, "driver", None)
            except Exception:
                pass


if __name__ == "__main__":
    scraper = ViverSeleniumScraper(headless=False)
    try:
        data = scraper.fetch_list(
            "https://www.viver.co.kr/shop",
            max_pages=30,
            only_today=True  # '오늘 등록'만 클릭/크롤링
        )
        print(f"총 {len(data)}개 상품 수집")
        for it in data[:10]:
            print(it)
        saved = save_to_mongo(
            data,
            mongo_uri="mongodb://localhost:27017",
            db_name="watchdb",
            collection_name="viver"
        )
        print(f"✅ MongoDB 저장 완료: {saved}개 문서")
    finally:
        scraper.close()
