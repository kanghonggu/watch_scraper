import random
import time
from typing import Optional

import undetected_chromedriver as uc
from pymongo import MongoClient
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from crawl_viver import _detect_chrome_major_version, _kst_today_iso
from viver_detail import parse_detail

MONGO_URI = "mongodb+srv://test:2RGdjwLiJyuzFwWn@super-mongo.zizsavi.mongodb.net?retryWrites=true&w=majority&appName=super-mongo"


def create_driver(headless: bool = False) -> uc.Chrome:
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ko-KR")
    major = _detect_chrome_major_version()
    try:
        return uc.Chrome(options=options, version_main=major) if major else uc.Chrome(options=options)
    except Exception as e:
        print(f"[Driver] 재시도: {e}")
        return uc.Chrome(options=options)


def refetch_url(driver: uc.Chrome, url: str) -> Optional[dict]:
    try:
        print(f"  🔗 방문: {url}")
        driver.get(url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        WebDriverWait(driver, 15).until(lambda d: d.execute_script("return document.readyState") == "complete")
        time.sleep(random.uniform(2, 3))

        item = parse_detail(driver.page_source, fallback_base_url=url)
        item["url"] = driver.current_url or url
        item["date"] = _kst_today_iso()
        return item
    except Exception as e:
        print(f"  ❌ 실패: {url} → {e}")
        return None


if __name__ == "__main__":
    client = MongoClient(MONGO_URI)
    collection = client["watchdb"]["viver"]

    # ✅ name이 잘못된 것만 타겟
    filter_query = {"name": "믿을 수 있는 시계 거래의 시작 | VIVER"}

    docs = list(collection.find(filter_query, {"_id": 1, "url": 1}))
    total = len(docs)
    print(f"📋 수정 대상: {total}개")

    if total == 0:
        print("대상 없음, 종료")
        client.close()
        exit()

    driver = create_driver(headless=False)
    success = fail = 0

    try:
        for i, doc in enumerate(docs):
            url = doc.get("url", "")
            doc_id = doc["_id"]
            print(f"\n[{i+1}/{total}] _id={doc_id}")

            if not url:
                print("  ⚠️ URL 없음, 스킵")
                fail += 1
                continue

            item = refetch_url(driver, url)

            if item:
                # name이 여전히 잘못 파싱되면 스킵
                if item.get("name") == "믿을 수 있는 시계 거래의 시작 | VIVER":
                    print(f"  ⚠️ 재파싱 후에도 name 동일, 스킵")
                    fail += 1
                    continue

                item.pop("_id", None)
                collection.update_one({"_id": doc_id}, {"$set": item})
                print(f"  ✅ 업데이트: {item.get('name', '')[:50]}")
                success += 1
            else:
                fail += 1

            time.sleep(random.uniform(1.5, 3))

    finally:
        driver.quit()
        client.close()
        print(f"\n🎉 완료! 성공: {success}개 / 실패: {fail}개")