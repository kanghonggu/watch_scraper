import os
import random
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Set, Tuple

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

        # 프로젝트 내 chromedriver 사용
        driver_path = os.environ.get("CHROMEDRIVER_PATH") or os.path.join(os.path.dirname(__file__), "chromedriver")
        self.driver = uc.Chrome(options=options, driver_executable_path=driver_path)

    def _wait_for_detail_ready(self, timeout: int = 25, min_stable_time: float = 0.8):
        WebDriverWait(self.driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
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

    def _extract_detail_from_current_page(self, fallback_base_url: str) -> Dict:
        WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        self._wait_for_detail_ready(timeout=25, min_stable_time=0.8)

        html = self.driver.page_source
        item = parse_detail(html, fallback_base_url=fallback_base_url)
        item["url"] = self.driver.current_url or fallback_base_url
        return item

    def _wait_and_collect_targets(self, timeout: int = 10):
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

        filtered_elements = []
        for el in elements:
            try:
                txt = (el.text or "").strip()
                visible = False
                try:
                    visible = el.is_displayed()
                except Exception:
                    visible = True
            except Exception:
                txt = ""
                visible = False
            if txt and visible:
                filtered_elements.append(el)

        print(f"[DEBUG] .css-g5y9jx.r-1loqt21.r-1otgn73 (text-present) count: {len(filtered_elements)}")
        return filtered_elements

    def _get_href_from_element(self, el):
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
        return el

    def _is_today_card(self, el) -> bool:
        try:
            card = self._get_card_ancestor(el)
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
            try:
                badges = card.find_elements(By.XPATH, ".//*[contains(normalize-space(.), '오늘 등록')]")
                if badges:
                    return True
            except Exception:
                pass
            return False
        except Exception:
            return False

    def fetch_list(self,
                   start_url: str = "https://www.viver.co.kr/shop",
                   max_pages: int = 50,
                   only_today: bool = True,
                   sleep_range: Tuple[float, float] = (1.0, 2.0)) -> List[Dict]:
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

            time.sleep(random.uniform(*sleep_range))
            print("🔄 Scrolling to load more items...")

            targets = self._wait_and_collect_targets(timeout=10)

            idx = 0
            extracted = 0
            while True:
                try:
                    current_targets = self._wait_and_collect_targets(timeout=5)
                except Exception:
                    current_targets = []
                if idx >= len(current_targets):
                    break

                el = current_targets[idx]
                idx += 1

                if only_today and not self._is_today_card(el):
                    continue

                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                except Exception:
                    pass

                try:
                    href = ""
                    try:
                        href = self._get_href_from_element(el)
                    except Exception:
                        href = ""

                    prev_url = self.driver.current_url
                    try:
                        WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(el))
                        el.click()
                    except Exception:
                        try:
                            self.driver.execute_script("arguments[0].click();", el)
                        except Exception:
                            pass

                    navigated = False
                    try:
                        WebDriverWait(self.driver, 8).until(lambda d: d.current_url != prev_url)
                        navigated = True
                    except Exception:
                        navigated = False

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
                        print("    ⚠️ Navigation did not occur; skipping this element.")
                        try:
                            self.driver.get(current_url)
                            WebDriverWait(self.driver, 10).until(
                                EC.presence_of_element_located((By.TAG_NAME, "body"))
                            )
                        except Exception:
                            pass
                        continue

                    try:
                        item = self._extract_detail_from_current_page(current_url)
                        if item:
                            item["date"] = today
                            results.append(item)
                            extracted += 1
                    except Exception as e:
                        print(f"    ⚠️ Detail extraction error: {e}")

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
            print("✅ Infinite-scroll mode: no pagination. Stopping after current page.")
            break

        return results

    def close(self):
        try:
            driver = getattr(self, "driver", None)
            if driver:
                driver.quit()
        finally:
            try:
                setattr(self, "driver", None)
            except Exception:
                pass


if __name__ == "__main__":
    MONGO_URI = "mongodb+srv://test:2RGdjwLiJyuzFwWn@super-mongo.zizsavi.mongodb.net?retryWrites=true&w=majority&appName=super-mongo"

    scraper = ViverSeleniumScraper(headless=True)
    try:
        data = scraper.fetch_list(
            "https://www.viver.co.kr/shop",
            max_pages=30,
            only_today=True
        )
        print(f"총 {len(data)}개 상품 수집")
        for it in data[:10]:
            print(it)
        saved = save_to_mongo(
            data,
            mongo_uri=MONGO_URI,
            db_name="watchdb",
            collection_name="viver"
        )
        print(f"✅ MongoDB 저장 완료: {saved}개 문서")
    finally:
        scraper.close()
