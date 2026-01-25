import argparse
from pymongo import MongoClient
from scraper import Chrono24SeleniumScraper


def main(brand: str, start_page: int, end_page: int, group: str, page_size: int):
    # MongoDB 연결
    client = MongoClient("mongodb://localhost:27017")
    db = client["watchdb"]

    scraper = Chrono24SeleniumScraper(headless=False)  # headless=True로 하면 브라우저 창 안 뜸
    try:
        # 크롤링 실행
        data = scraper.fetch_multi_pages(
            brand=brand,
            start_page=start_page,
            end_page=end_page,
            group_str=group,
            page_size=page_size
        )

        print(f"총 {len(data)}개 아이템 크롤링 완료")

        if data:
            # MongoDB 저장
            db["chrono24"].insert_many(data)
            print(f"MongoDB에 {len(data)}개 저장 완료")

        # 처음 5개만 미리보기 출력
        for d in data[:5]:
            print(d)

    finally:
        scraper.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chrono24 Rolex 크롤러")
    parser.add_argument("--brand", type=str, default="rolex", help="브랜드 이름 (예: rolex, omega)")
    parser.add_argument("--start", type=int, default=1, help="시작 페이지 번호")
    parser.add_argument("--end", type=int, default=1, help="끝 페이지 번호")
    parser.add_argument("--group", type=str, default="luxury", help="그룹명 태그")
    parser.add_argument("--page-size", type=int, default=120, help="페이지당 아이템 개수")

    args = parser.parse_args()

    main(args.brand, args.start, args.end, args.group, args.page_size)
