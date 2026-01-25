# 상세 페이지 파싱 전용 모듈

import re
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

def _text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""

def _clean_spaces(s: str) -> str:
    s = (s or "").replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", s)

def _normalize_price(text: str) -> Optional[int]:
    if not text:
        return None
    nums = re.sub(r"[^\d]", "", text)
    if not nums:
        return None
    try:
        return int(nums)
    except Exception:
        return None

KOREAN_LABELS = {
    "brand": ["브랜드", "메이커", "브랜드명", "Brand"],
    "model": ["모델", "모델명", "Model"],
    "reference": ["레퍼런스", "참조번호", "Reference", "Ref", "레퍼런스 넘버"],
    "year": ["연식", "구매연도", "제조연도", "Year"],
    "condition": ["상태", "컨디션", "Condition"],
    "accessories": ["구성품", "구성", "풀세트", "Accessories", "Set"],
    "movement": ["무브먼트", "무브", "Movement"],
    "caliber": ["칼리버", "Caliber"],
    "case": ["케이스", "Case", "소재", "Material"],
    "dial": ["다이얼", "Dial"],
    "size": ["사이즈", "크기", "직경", "Size", "Diameter"],
    "water_resistance": ["방수", "방수기능", "Water Resistance"],
    "warranty": ["보증서", "보증", "보증기간", "Warranty", "보증카드"],
    "seller": ["판매자", "딜러", "Seller"],
    "location": ["지역", "위치", "Location"],
    "registered_at": ["등록일", "업로드일", "등록", "Posted", "Date"],
    "price": ["가격", "판매가", "Price", "금액"],
}

def _find_first(soup: BeautifulSoup, selectors: List[str]):
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            return el
    return None

def _extract_title(soup: BeautifulSoup) -> str:
    og = soup.select_one("meta[property='og:title']")
    if og and og.get("content"):
        return _clean_spaces(og.get("content"))
    h1 = _find_first(soup, ["h1", ".product-title", ".prd-name", ".title"])
    if h1:
        return _clean_spaces(_text(h1))
    if soup.title and soup.title.string:
        return _clean_spaces(soup.title.string)
    return ""

def _extract_images(soup: BeautifulSoup) -> List[str]:
    urls = []
    for m in soup.select("meta[property='og:image']"):
        c = (m.get("content") or "").strip()
        if c:
            urls.append(c)
    for img in soup.select(".xans-product-detail img, .product-detail img, .detailArea img, article img, img"):
        for attr in ("data-src", "data-original", "src"):
            v = (img.get(attr) or "").strip()
            if v:
                urls.append(v)
                break
    seen = set()
    uniq = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq

def _label_match(label: str, target_list: List[str]) -> bool:
    lab = _clean_spaces(label).lower()
    for t in target_list:
        if t.lower() in lab:
            return True
    return False

def _extract_table_like_info(soup: BeautifulSoup) -> Dict[str, str]:
    info: Dict[str, str] = {}

    def set_if_empty(key: str, val: str):
        val = _clean_spaces(val)
        if not val:
            return
        if key not in info or not info[key]:
            info[key] = val

    # 1) dl/dt/dd
    for dl in soup.select("dl"):
        for dt in dl.select("dt"):
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            key_text = _text(dt)
            val_text = _text(dd)
            for field, labels in KOREAN_LABELS.items():
                if _label_match(key_text, labels):
                    set_if_empty(field, val_text)

    # 2) table tr(th/td 또는 td/td)
    for tr in soup.select("table tr"):
        th = tr.find("th")
        td = tr.find("td")
        if th and td:
            th_text, td_text = _text(th), _text(td)
        else:
            tds = tr.find_all("td")
            if len(tds) >= 2:
                th_text, td_text = _text(tds[0]), _text(tds[1])
            else:
                continue
        for field, labels in KOREAN_LABELS.items():
            if _label_match(th_text, labels):
                set_if_empty(field, td_text)

    # 3) '라벨: 값'
    for node in soup.select("div, li, p"):
        txt = _clean_spaces(_text(node))
        if not txt:
            continue
        m = re.match(r"^([^:：]+)\s*[:：]\s*(.+)$", txt)
        if not m:
            continue
        key_text, val_text = m.group(1), m.group(2)
        for field, labels in KOREAN_LABELS.items():
            if _label_match(key_text, labels):
                set_if_empty(field, val_text)

    return info

def _extract_price_advanced(soup: BeautifulSoup) -> Tuple[str, Optional[int]]:
    meta = soup.select_one("meta[property='product:price:amount'], meta[itemprop='price'], meta[name='price']")
    if meta and meta.get("content"):
        ptxt = _clean_spaces(meta.get("content"))
        return ptxt, _normalize_price(ptxt)

    for el in soup.select(".xans-product-detail .price, .price .sale, .price .value, .price, .product-price, .prd-price, [class*='price']"):
        txt = _clean_spaces(_text(el))
        if re.search(r"(₩|원|KRW|\d[\d,.\s]{2,})", txt):
            return txt, _normalize_price(txt)

    for script in soup.select("script[type='application/ld+json']"):
        try:
            import json
            data = json.loads(script.get_text(strip=True))
            objs = data if isinstance(data, list) else [data]
            for obj in objs:
                if isinstance(obj, dict) and obj.get("@type") in ("Product", "Offer"):
                    offers = obj.get("offers")
                    if isinstance(offers, dict) and "price" in offers:
                        p = str(offers["price"])
                        return p, _normalize_price(p)
                    if "price" in obj:
                        p = str(obj["price"])
                        return p, _normalize_price(p)
        except Exception:
            pass

    body_text = _clean_spaces(soup.get_text(" ", strip=True))
    m = re.search(r"(₩\s*[\d,.\s]+|\d[\d,.\s]{2,}\s*원)", body_text)
    if m:
        txt = _clean_spaces(m.group(0))
        return txt, _normalize_price(txt)
    return "", None

def _extract_description(soup: BeautifulSoup) -> str:
    candidates = soup.select(
        ".xans-product-detail .cont, .product-description, .detailArea, .prd-desc, .description, .sc-empnci, .sc-jlZhew"
    )
    if not candidates:
        return _clean_spaces(soup.get_text(" ", strip=True))[:2000]
    best = max(candidates, key=lambda el: len(_text(el) or ""))
    return _clean_spaces(_text(best))[:5000]

def _extract_registered_date(soup: BeautifulSoup) -> str:
    text = _clean_spaces(soup.get_text(" ", strip=True))
    m = re.search(r"(등록일|업로드일|게시일)\s*[:：]?\s*([0-9]{4}[.\-][0-9]{1,2}[.\-][0-9]{1,2})", text)
    if m:
        return m.group(2)
    m2 = re.search(r"([0-9]{4}[.\-][0-9]{1,2}[.\-][0-9]{1,2})", text)
    if m2 and re.search(r"(등록|업로드|게시)", text):
        return m2.group(1)
    return ""

def _extract_viver_specific(soup: BeautifulSoup) -> Dict[str, str]:
    data: Dict[str, str] = {}

    name_el = soup.select_one("h4.sc-aXZVg.sc-cDltVh.kBNPNG.bMwTGV")
    if name_el:
        data["name"] = _clean_spaces(_text(name_el))

    brand_el = soup.select_one("span.sc-aXZVg.bRlkgB")
    if brand_el:
        data["brand"] = _clean_spaces(_text(brand_el))

    wear_el = soup.select_one("div.sc-cepbVR span.sc-aXZVg.sc-etKGGb")
    if wear_el:
        data["wear_status"] = _clean_spaces(_text(wear_el))

    for block in soup.select("div.sc-fHCFno"):
        label_el = block.select_one("strong")
        value_el = block.select_one("span")
        if not label_el or not value_el:
            continue
        label = _clean_spaces(_text(label_el))
        value = _clean_spaces(_text(value_el))
        if not label or not value:
            continue
        if "보증서" in label:
            data["warranty"] = value
        elif "스탬핑" in label:
            data["stamping_year"] = value
        elif "정품 박스" in label:
            data["has_box"] = value
        elif "특이사항" in label:
            data["special_note"] = value

    spec_header = None
    for el in soup.select("div.css-146c3p1"):
        if _clean_spaces(_text(el)) == "상세 스펙":
            spec_header = el
            break
    if spec_header:
        parent = spec_header.find_parent("div")
        if parent:
            rows = parent.select("div.css-g5y9jx[style*='flex-direction: row']")
            for row in rows:
                cells = row.select("div.css-146c3p1")
                if len(cells) < 2:
                    continue
                key = _clean_spaces(_text(cells[0]))
                val = _clean_spaces(_text(cells[1]))
                if not key or not val:
                    continue
                if key == "다이얼 색상":
                    data["dial_color"] = val
                elif key == "케이스 소재":
                    data["case_material"] = val
                elif key == "브레이슬릿 소재":
                    data["bracelet_material"] = val
                elif key == "글라스":
                    data["glass"] = val
                elif key == "케이스 직경":
                    data["case_diameter"] = val
                elif key == "케이스 두께":
                    data["case_thickness"] = val
                elif key == "방수":
                    data["water_resistance"] = val
                elif key == "베젤 소재":
                    data["bezel_material"] = val
                elif key == "베젤 종류":
                    data["bezel_type"] = val
                elif key == "무브먼트":
                    data["movement"] = val
                elif key == "칼리버":
                    data["caliber"] = val
                elif key == "진동수":
                    data["frequency"] = val
                elif key == "파워리저브":
                    data["power_reserve"] = val

    return data

def parse_detail(html: str, fallback_base_url: str) -> Dict:
    """
    상세 페이지 HTML을 입력받아 파싱 결과 dict를 반환
    """
    soup = BeautifulSoup(html, "html.parser")

    title = _extract_title(soup)
    price_text, price = _extract_price_advanced(soup)
    images = _extract_images(soup)
    description = _extract_description(soup)
    info = _extract_table_like_info(soup)
    viver_info = _extract_viver_specific(soup)

    merged = {
        "name": viver_info.get("name", "") or title,
        "brand": viver_info.get("brand") or info.get("brand", ""),
        "movement": viver_info.get("movement") or info.get("movement", ""),
        "caliber": viver_info.get("caliber") or info.get("caliber", ""),
        "water_resistance": viver_info.get("water_resistance") or info.get("water_resistance", ""),
        "warranty": viver_info.get("warranty") or info.get("warranty", ""),
        "price_text": price_text,
        "price": price,
        "images": images,
        "description": description,
        "registered_at": info.get("registered_at", "") or _extract_registered_date(soup),
        "url": fallback_base_url,  # 호출 측에서 실제 current_url로 덮어씌우길 권장
        "source": "viver",
    }

    for k_src in [
        "wear_status", "stamping_year", "has_box", "special_note",
        "dial_color", "case_material", "bracelet_material", "glass",
        "case_diameter", "case_thickness", "bezel_material", "bezel_type",
        "frequency", "power_reserve"
    ]:
        v = viver_info.get(k_src)
        if v:
            merged[k_src] = v

    return merged