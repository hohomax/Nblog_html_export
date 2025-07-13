from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup, NavigableString, Comment
import time
import re
import json
import urllib.parse
import html
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def remove_ads(main_container):
    # 광고 및 체크인 버튼 등 불필요 요소 제거
    ad_classes = [
        ("div", {"class_": "ssp_adcontent__O8MGL"}),
        ("div", {"id": lambda x: x and x.startswith("ad-content-")}),
        ("iframe", {"title": "AD"}),
        ("div", {"class_": "ssp_adcontent_inner__fpl9U"}),
        ("div", {"id": lambda x: x and "ad-content" in x}),
        ("div", {"class_": "checkin_button_wrap"}),
    ]
    for tag, kwargs in ad_classes:
        for ad in main_container.find_all(tag, **kwargs):
            ad.decompose()
    for checkin_button in main_container.find_all("button", class_="checkin_button"):
        checkin_button.decompose()

def process_map_links(main_container, soup):
    for map_info in main_container.find_all("a", class_="se-map-info"):
        for marker in map_info.find_all("div", class_="se-map-marker"):
            marker.decompose()
        if map_info.has_attr("onclick"):
            del map_info["onclick"]
        linkdata = map_info.get("data-linkdata", "")
        lat, lng, name = None, None, None
        try:
            decoded = html.unescape(linkdata)
            data = json.loads(decoded)
            lat = data.get("latitude")
            lng = data.get("longitude")
            name = data.get("name")
        except Exception:
            pass
        if not lat or not lng or not name:
            lat_match = re.search(r'"latitude"\s*:\s*"([^"]+)"', linkdata)
            lng_match = re.search(r'"longitude"\s*:\s*"([^"]+)"', linkdata)
            name_match = re.search(r'"name"\s*:\s*"([^"]+)"', linkdata)
            if lat_match and lng_match and name_match:
                lat = lat or lat_match.group(1)
                lng = lng or lng_match.group(1)
                name = name or name_match.group(1)
        if lat and lng and name and len(name.strip()) > 0:
            name_decoded = html.unescape(name)
            name_encoded = urllib.parse.quote_plus(name_decoded)
            map_info["href"] = f"https://www.google.com/maps/search/{name_encoded}/@{lat},{lng},17z/"
            map_info["target"] = "_blank"
        elif lat and lng:
            map_info["href"] = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
            map_info["target"] = "_blank"
        svg_marker = soup.new_tag("span", **{"class": "se-map-marker"})
        svg_marker.append(BeautifulSoup('''<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" fill="#4285F4"/></svg>''', 'html.parser'))
        map_info.insert(0, svg_marker)

def wait_for_page_load(driver, timeout=10):
    """메인 컨테이너가 로드될 때까지 대기"""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".se-main-container"))
        )
    except Exception:
        time.sleep(3)  # fallback

def fix_lazy_images(main_container):
    """이미지 lazy loading 및 스티커 처리"""
    for img in main_container.find_all("img"):
        # data-lazy-src가 있으면 src로 교체
        if img.has_attr("data-lazy-src") and img["data-lazy-src"]:
            img["src"] = img["data-lazy-src"]
        elif img.has_attr("data-lazy-src") and not img["data-lazy-src"]:
            if not img.has_attr("src") or not img["src"]:
                img.decompose()
        elif "lazy-loading-target-image" in img.get("class", []):
            if img.has_attr("data-lazy-src") and img["data-lazy-src"]:
                img["src"] = img["data-lazy-src"]
            else:
                img.decompose()
        elif "se-sticker-image" in img.get("class", []):
            if img.has_attr("data-lazy-src") and img["data-lazy-src"]:
                img["src"] = img["data-lazy-src"]

def clean_scripts(main_container):
    """필요 없는 script 태그 제거"""
    for script in main_container.find_all("script"):
        if script.has_attr("class") and "__se_module_data" in script.get("class", []):
            continue
        script.decompose()

def extract_blog_html(url, options=None):
    # Selenium 설정
    if options is None:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    wait_for_page_load(driver)
    # 스크롤 다운 (최대 10회, 더 이상 내려가지 않으면 break)
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(10):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.7)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
    page_html = driver.execute_script("return document.documentElement.outerHTML")
    driver.quit()

    soup = BeautifulSoup(page_html, "html.parser")
    main_container = soup.find(class_="se-main-container")
    if not main_container:
        raise ValueError("본문 컨테이너를 찾을 수 없습니다.")

    # 1. 이미지 lazy loading 및 스티커 처리
    fix_lazy_images(main_container)
    # 2. 광고/불필요 요소 제거
    remove_ads(main_container)
    # 3. 지도 링크 처리
    process_map_links(main_container, soup)
    # 4. script 정리
    clean_scripts(main_container)

    # === 이미지 그리드 width 보정 및 strip/그룹(콜라주) 보정 ===
    for group in main_container.find_all(class_="se-image-resource_group"):
        for child in list(group.children):
            if isinstance(child, (NavigableString, Comment)) or (getattr(child, 'name', None) is None):
                child.extract()
            elif getattr(child, 'name', None) != 'div' or 'se-image-resource' not in child.get('class', []):
                child.extract()
        resources = group.find_all(class_="se-image-resource", recursive=False)
        n = len(resources)
        if n > 0:
            width = f"{100/n:.4f}%"
            for res in resources:
                old_style = res.get('style', '')
                res['style'] = (
                    f"width: {width}; min-width: {width}; max-width: {width}; "
                    f"flex-basis: {width}; display: flex; vertical-align: top; box-sizing: border-box; "
                    f"height: 200px; {old_style}"
                )
            # strip(가로 이미지 그리드) 처리 (width%를 실제 이미지 비율로)
        for strip in main_container.find_all(class_="se-imageStrip-container"):
            modules = [m for m in strip.find_all("div", class_="se-module se-module-image", recursive=False)]
            widths = []
            for mod in modules:
                img = mod.find("img", class_="se-image-resource")
                if img and img.has_attr("data-width"):
                    widths.append(int(img["data-width"]))
                else:
                    widths.append(1)
            total = sum(widths)
            for mod, w in zip(modules, widths):
                width_percent = w / total * 100
                # 기존 style에서 width 관련 속성 제거
                orig_style = mod.get('style', '')
                # width 관련 속성들을 제거
                orig_style = re.sub(r'(width|min-width|max-width|flex-basis)\s*:[^;]+;?', '', orig_style)
                # 새로운 width 설정 (height는 CSS에서 처리)
                mod['style'] = f"width: {width_percent:.8f}%; {orig_style}"
    # imageGroup/collage(콜라주) 처리 - 레이아웃에 따라 다르게 처리
    for group in main_container.find_all(class_="se-imageGroup-container"):
        # 이미지 그룹 컨테이너의 기존 스타일 정리
        group_style = group.get('style', '')
        # margin 관련 스타일 제거 (CSS에서 처리)
        group_style = re.sub(r'margin\s*:[^;]+;?', '', group_style)
        group_style = re.sub(r'margin-top\s*:[^;]+;?', '', group_style)
        group_style = re.sub(r'margin-bottom\s*:[^;]+;?', '', group_style)
        group_style = re.sub(r'margin-left\s*:[^;]+;?', '', group_style)
        group_style = re.sub(r'margin-right\s*:[^;]+;?', '', group_style)
        # 세미콜론으로 시작하는 스타일 정리
        group_style = re.sub(r'^\s*;\s*', '', group_style)
        group['style'] = group_style
        
        # 레이아웃 확인 (슬라이드 vs 콜라주)
        parent_section = group.find_parent(class_="se-section-imageGroup")
        is_slide = False
        is_collage = False
        
        if parent_section:
            if "se-l-slide" in parent_section.get("class", []):
                is_slide = True
            elif "se-l-collage" in parent_section.get("class", []):
                is_collage = True
        
        items = [item for item in group.find_all("div", class_="se-imageGroup-item", recursive=False)]
        n = len(items)
        if n > 0:
            for item in items:
                if is_slide:
                    # 슬라이드: 각 아이템을 50% 너비로 설정 (strip의 1개 이미지와 동일)
                    style = item.get('style', '')
                    style = re.sub(r'(width|min-width|max-width|flex-basis|flex-shrink|flex-grow)\s*:[^;]+;?', '', style)
                    item['style'] = f'flex: 0 0 50%; {style}'
                    # 내부 모듈은 100% 너비
                    modules = item.find_all('div', class_='se-module se-module-image', recursive=False)
                    for mod in modules:
                        mod_style = mod.get('style', '')
                        mod_style = re.sub(r'(width|min-width|max-width|flex-basis)\s*:[^;]+;?', '', mod_style)
                        mod['style'] = f'width: 100%; {mod_style}'
                
                elif is_collage:
                    # 콜라주: 각 아이템 내부의 여러 이미지를 strip처럼 비율 계산
                    style = item.get('style', '')
                    style = re.sub(r'(width|min-width|max-width|flex-basis|flex-shrink|flex-grow)\s*:[^;]+;?', '', style)
                    item['style'] = f'flex: 0 0 100%; {style}'  # 콜라주 아이템은 100% 너비
                    # 내부 여러 이미지를 strip처럼 비율 계산
                    modules = item.find_all('div', class_='se-module se-module-image', recursive=False)
                    widths = []
                    for mod in modules:
                        img = mod.find("img", class_="se-image-resource")
                        if img and img.has_attr("data-width"):
                            widths.append(int(img["data-width"]))
                        else:
                            widths.append(1)
                    total = sum(widths)
                    for mod, w in zip(modules, widths):
                        width_percent = w / total * 100
                        mod_style = mod.get('style', '')
                        mod_style = re.sub(r'(width|min-width|max-width|flex-basis)\s*:[^;]+;?', '', mod_style)
                        mod['style'] = f"width: {width_percent:.8f}%; {mod_style}"
                
                else:
                    # 기본 처리 (기존과 동일)
                    style = item.get('style', '')
                    style = re.sub(r'(width|min-width|max-width|flex-basis|flex-shrink|flex-grow)\s*:[^;]+;?', '', style)
                    item['style'] = f'flex: 0 0 50%; {style}'
                    modules = item.find_all('div', class_='se-module se-module-image', recursive=False)
                    for mod in modules:
                        mod_style = mod.get('style', '')
                        mod_style = re.sub(r'(width|min-width|max-width|flex-basis)\s*:[^;]+;?', '', mod_style)
                        mod['style'] = f'width: 100%; {mod_style}'

    # === 스티커 이미지 width/height 보정 ===
    for img in main_container.find_all("img", class_="se-sticker-image"):
        # width/height 속성 제거 (네이버 원본처럼)
        if "width" in img.attrs:
            del img["width"]
        if "height" in img.attrs:
            del img["height"]
        # lazy loading 보강: data-lazy-src가 있으면 src로 교체
        if img.has_attr("data-lazy-src") and img["data-lazy-src"]:
            img["src"] = img["data-lazy-src"]
        # 인라인 스타일로 중앙정렬 강제
        img["style"] = "display: block !important; margin-left: auto !important; margin-right: auto !important; max-width: 100px !important; height: auto !important;"

    # === 모든 이미지에 인라인 스타일로 중앙정렬 강제 ===
    for img in main_container.find_all("img"):
        # OG 링크 썸네일 이미지는 제외 (북마크 카드 레이아웃 유지)
        if "se-oglink-thumbnail-resource" in img.get("class", []):
            continue
        
        # 이미지 그리드 내부 이미지는 그리드에 맞는 스타일 적용
        if img.find_parent(class_="se-imageStrip-container") or img.find_parent(class_="se-imageGroup-container") or img.find_parent(class_="se-image-resource_group"):
            # 그리드 내부 이미지는 컨테이너에 맞게 설정
            img["style"] = "width: 100% !important; height: 100% !important; object-fit: cover !important; display: block !important; margin: 0 !important;"
            continue
        
        # 기존 스타일 가져오기
        current_style = img.get("style", "")
        # 중앙정렬 스타일 추가
        center_style = "display: block !important; margin-left: auto !important; margin-right: auto !important; max-width: 100% !important; height: auto !important;"
        img["style"] = center_style + " " + current_style

    # === OG 링크 썸네일 이미지 스타일 보정 ===
    for img in main_container.find_all("img", class_="se-oglink-thumbnail-resource"):
        # OG 링크 썸네일은 북마크 카드 레이아웃에 맞는 스타일 적용
        img["style"] = "max-width: 100% !important; max-height: 100% !important; object-fit: contain !important; padding: 8px !important;"

    # === 이미지 링크에 인라인 스타일로 중앙정렬 강제 ===
    for link in main_container.find_all("a", class_="se-module-image-link"):
        # 이미지 그리드 내부 링크는 그리드에 맞는 스타일 적용
        if link.find_parent(class_="se-imageStrip-container") or link.find_parent(class_="se-imageGroup-container") or link.find_parent(class_="se-image-resource_group"):
            # 그리드 내부 링크는 컨테이너에 맞게 설정
            link["style"] = "display: block !important; width: 100% !important; height: 100% !important; margin: 0 !important;"
            continue
        
        # 기존 스타일 가져오기
        current_style = link.get("style", "")
        # 중앙정렬 스타일 추가
        center_style = "display: block !important; text-align: center !important; margin-left: auto !important; margin-right: auto !important; width: fit-content !important;"
        link["style"] = center_style + " " + current_style

    # === 통합 이미지 스타일 및 간격 처리 ===
    # 모든 이미지 관련 요소들을 한 번에 찾아서 처리
    all_image_elements = []
    
    # 1. 모든 이미지 관련 요소들 수집
    for element in main_container.find_all():
        classes = element.get('class', [])
        if any(cls in classes for cls in ['se-component', 'se-section', 'se-module']) and any(cls in classes for cls in ['se-image', 'imageStrip', 'imageGroup', 'image-strip', 'image-resource_group']):
            all_image_elements.append(element)
        elif any(cls in classes for cls in ['se-imageStrip-container', 'se-imageGroup-container', 'se-image-strip', 'se-image-resource_group']):
            all_image_elements.append(element)
    
    # 2. DOM 순서대로 정렬
    all_image_elements.sort(key=lambda x: list(main_container.descendants).index(x))
    
    # 3. 각 요소의 레벨과 타입에 따라 스타일 적용
    for i, element in enumerate(all_image_elements):
        classes = element.get('class', [])
        current_style = element.get("style", "")
        
        # 기존 스타일 정리
        current_style = re.sub(r'margin\s*:[^;]+;?', '', current_style)
        current_style = re.sub(r'margin-top\s*:[^;]+;?', '', current_style)
        current_style = re.sub(r'margin-bottom\s*:[^;]+;?', '', current_style)
        current_style = re.sub(r'margin-left\s*:[^;]+;?', '', current_style)
        current_style = re.sub(r'margin-right\s*:[^;]+;?', '', current_style)
        
        # 요소 타입에 따른 스타일 적용
        if any(cls in classes for cls in ['se-imageStrip-container', 'se-imageGroup-container', 'se-image-strip', 'se-image-resource_group']):
            # 이미지 그리드 컨테이너
            if 'se-imageGroup-container' in classes:
                # 이미지 그룹은 CSS에서 margin 처리하므로 인라인 스타일 제거
                element["style"] = current_style
            else:
                # 다른 그리드 컨테이너들
                if i < len(all_image_elements) - 1:
                    element["style"] = f"{current_style}; margin: 0 0 4px 0 !important;"
                else:
                    element["style"] = f"{current_style}; margin: 0 !important;"
        elif any(cls in classes for cls in ['se-module-image', 'se-image-resource']):
            # 그리드 내부 요소 - 간격 추가
            # 같은 그리드 내에서의 순서 확인
            parent_grid = element.find_parent(class_=["se-imageStrip-container", "se-imageGroup-container", "se-image-strip", "se-image-resource_group"])
            if parent_grid:
                siblings = parent_grid.find_all(["div"], class_=["se-module-image", "se-image-resource"])
                sibling_index = list(siblings).index(element)
                if sibling_index < len(siblings) - 1:  # 마지막 요소가 아니면
                    element["style"] = f"{current_style}; margin: 0 4px 0 0 !important;"
                else:
                    element["style"] = f"{current_style}; margin: 0 !important;"
            else:
                element["style"] = f"{current_style}; margin: 0 !important;"
        else:
            # 일반 이미지 요소
            if i < len(all_image_elements) - 1:
                element["style"] = f"{current_style}; margin: 0 0 4px 0 !important;"
            else:
                element["style"] = f"{current_style}; margin: 0 !important;"

    # 1. 전체 soup에서 제목 추출
    title_div = soup.select_one("div.se-title-text")
    if title_div:
        blog_title = title_div.get_text(strip=True)
    else:
        # 2. 예비: 본문 내에서 가장 긴 span 텍스트 사용
        spans = main_container.find_all("span")
        blog_title = ""
        max_len = 0
        for span in spans:
            text = span.get_text(strip=True)
            if len(text) > max_len and len(text) > 5:
                blog_title = text
                max_len = len(text)
        if not blog_title:
            blog_title = "제목 없음"

    # 강제 스타일(가운데 정렬 등) 추가
    custom_style = """
<style>
/* === 반응형 기본 설정 === */
* {
    box-sizing: border-box !important;
}

body, .se-main-container {
    text-align: center !important;
    font-size: 16px !important;
    color: #141414 !important;
    background: #fff !important;
    max-width: 100% !important;
    margin: 0 auto !important;
    padding: 0 10px !important;
}

/* === 반응형 컨테이너 === */
.se-main-container {
    max-width: 800px !important;  /* 최대 너비 제한 */
    margin: 0 auto !important;
    padding: 0 15px !important;
}
.se-main-container * {
    text-align: inherit !important;
}
.se-text-paragraph-align-left, .se-text-paragraph-align-left * {
    text-align: left !important;
}
.se-text-paragraph-align-right, .se-text-paragraph-align-right * {
    text-align: right !important;
}
/* === 반응형 이미지 기본 스타일 === */
img {
    max-width: 100% !important;
    height: auto !important;
    display: block !important;
    margin-left: auto !important;
    margin-right: auto !important;
    width: auto !important;  /* 자동 너비로 설정 */
}
/* 이미지 섹션 중앙 정렬 강화 */
.se-section-image {
    text-align: center !important;
}
.se-module-image {
    text-align: center !important;
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
}
.se-sticker-image {
    max-width: 120px !important;   /* 반응형으로 조정 */
    width: auto !important;
    height: auto !important;
    display: block !important;
    margin-left: auto !important;
    margin-right: auto !important;
    margin-top: 0 !important;
    margin-bottom: 0 !important;
}
/* 스티커 섹션 중앙 정렬 및 flex 보강 */
.se-section-sticker {
    text-align: center !important;
    display: flex !important;
    flex-direction: row !important;
    justify-content: center !important;
    align-items: center !important;
}
.se-module-sticker {
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
}
a, blockquote, pre, code, div, span {
    text-align: inherit !important;
}

/* === 인용구 스타일 === */
.se-quotation-container {
    margin: 1em 0 !important;
    padding: 1em 1.5em !important;
    border-left: 4px solid #4285F4 !important;
    background: #f8f9fa !important;
    border-radius: 8px !important;
    position: relative !important;
    font-style: italic !important;
}

blockquote.se-quotation-container::before {
    content: "“";
    font-size: 2em;
    vertical-align: top;
    color: #888;
    margin-right: 0.2em;
    position: absolute !important;
    top: 0.2em !important;
    left: 0.5em !important;
}
blockquote.se-quotation-container::after {
    content: "”";
    font-size: 2em;
    vertical-align: bottom;
    color: #888;
    margin-left: 0.2em;
    position: absolute !important;
    bottom: 0.2em !important;
    right: 0.5em !important;
}

.se-quotation-container .se-module-text {
    margin: 0 !important;
    padding: 0 !important;
}

.se-quotation-container .se-text-paragraph {
    margin: 0 !important;
    font-weight: 500 !important;
    color: #333 !important;
}

hr.se-hr {
    width: 40%;
    margin: 2em auto;
    border: none;
    border-top: 2px solid #e0e0e0;
    height: 0;
    background: none;
}

/* === 지도 관련 스타일 === */
.se-placesMap {
    margin: 1em 0 !important;
    text-align: center !important;
}
.se-map-info {
    display: inline-block !important;
    text-decoration: none !important;
    color: inherit !important;
    padding: 1em !important;
    border: 1px solid #e0e0e0 !important;
    border-radius: 8px !important;
    background: #f9f9f9 !important;
    max-width: 100% !important;
    box-sizing: border-box !important;
}
.se-map-marker {
    display: inline-block !important;
    margin-right: 0.5em !important;
    vertical-align: middle !important;
}
.se-map-marker svg {
    width: 24px !important;
    height: 24px !important;
    display: block !important;
}
.se-map-title {
    display: block !important;
    font-weight: bold !important;
    margin-bottom: 0.5em !important;
    color: #333 !important;
}
.se-map-address {
    display: block !important;
    color: #666 !important;
    font-size: 14px !important;
    margin: 0 !important;
}
/* === 줄 간격/공백 최적화 === */
p.se-text-paragraph {
    margin: 0.7em 0 !important;
    line-height: 1.7 !important;
    font-size: 16px !important;
    color: #141414 !important;
}
p.se-text-paragraph:empty,
p.se-text-paragraph span:empty {
    min-height: 0.7em !important;
    margin: 0.2em 0 !important;
    display: block;
}
span.se-fs-:empty {
    min-width: 0.5em;
    display: inline-block;
}
span.se-fs-, span.se-ff- {
    font-size: 16px !important;
    color: #141414 !important;
}
/* === 반응형 이미지 그리드 스타일 === */
.se-imageStrip-container,
.se-imageGroup-container,
.se-image-strip,
.se-image-resource_group {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    gap: 4px !important;  /* 이미지 간 간격 */
    justify-content: center !important;
    align-items: stretch !important;
    overflow-x: auto !important;
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    min-height: 200px !important;  /* 최소 높이 설정 */
}

/* 이미지 그룹(슬라이드) 특별 처리 - 가로 스크롤 */
.se-imageGroup-container {
    min-height: 200px !important;  /* 최소 높이 설정 */
    max-height: 400px !important;  /* 최대 높이 제한 */
    height: 250px !important;  /* 기본 높이 - 다른 그리드와 동일 */
    margin: 0 0 4px 0 !important;  /* 다른 그리드와 동일한 간격 */
    overflow-x: auto !important;  /* 가로 스크롤 활성화 */
    overflow-y: hidden !important;  /* 세로 스크롤 비활성화 */
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    gap: 4px !important;  /* 다른 그리드와 동일한 간격 */
    justify-content: flex-start !important;  /* 왼쪽 정렬 */
    align-items: stretch !important;
    width: 100% !important;
    max-width: 100% !important;
    padding: 0 !important;
    scroll-behavior: smooth !important;  /* 부드러운 스크롤 */
    -webkit-overflow-scrolling: touch !important;  /* iOS 부드러운 스크롤 */
}

/* 이미지 그룹 아이템을 슬라이드로 설정 */
.se-imageGroup-item {
    display: flex !important;
    flex-direction: column !important;
    flex-wrap: nowrap !important;
    gap: 0 !important;
    justify-content: center !important;
    align-items: stretch !important;
    flex: 0 0 50% !important;  /* strip의 1개 이미지와 동일한 크기 */
    width: 50% !important;
    height: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    min-width: 50% !important;  /* 최소 너비 보장 */
}

/* 콜라주 아이템만 가로 배치로 설정 */
.se-imageGroup-item.se-imageGroup-col-2,
.se-imageGroup-item.se-imageGroup-col-3,
.se-imageGroup-item.se-imageGroup-col-4 {
    display: flex !important;
    flex-direction: row !important;  /* 가로 배치 */
    flex-wrap: nowrap !important;
    gap: 4px !important;
    justify-content: flex-start !important;
    align-items: stretch !important;
    flex: 0 0 100% !important;  /* 콜라주는 100% 너비 */
    width: 100% !important;
    min-width: 100% !important;
}

/* 이미지 그룹(슬라이드) 아이템 간 간격 strip/grid와 동일하게 */
.se-imageGroup-container > .se-imageGroup-item:not(:last-child) {
    margin-right: 4px !important;
}
.se-imageGroup-item > .se-module.se-module-image:not(:last-child) {
    margin-right: 4px !important;
}

/* 이미지 그리드 내부 요소들 사이 간격 강제 적용 */
.se-imageStrip-container > .se-module.se-module-image:not(:last-child),
.se-imageGroup-container > .se-module.se-module-image:not(:last-child),
.se-image-strip > .se-image-resource:not(:last-child),
.se-image-resource_group > .se-image-resource:not(:last-child) {
    margin-right: 4px !important;
}

.se-imageStrip-container .se-module.se-module-image,
.se-imageGroup-container .se-module.se-module-image,
.se-image-strip .se-image-resource,
.se-image-resource_group .se-image-resource {
    display: flex !important;
    flex-direction: column !important;
    align-items: stretch !important;
    box-sizing: border-box !important;
    margin: 0 !important;
    padding: 0 !important;
    min-height: 200px !important;  /* 최소 높이 설정 */
    max-height: 400px !important;  /* 최대 높이 제한 */
    height: 250px !important;  /* 고정 높이로 일관성 유지 */
}

/* 이미지 그룹 내부 요소들 - 다른 그리드와 동일한 높이 */
.se-imageGroup-container .se-module.se-module-image {
    min-height: 200px !important;  /* 최소 높이 설정 */
    max-height: 400px !important;  /* 최대 높이 제한 */
    height: 250px !important;  /* 기본 높이 - 다른 그리드와 동일 */
    display: flex !important;
    flex-direction: column !important;
    align-items: stretch !important;
    box-sizing: border-box !important;
    margin: 0 !important;
    padding: 0 !important;
}



.se-imageStrip-container img.se-image-resource,
.se-imageGroup-container img.se-image-resource,
.se-image-strip img,
.se-image-resource_group img {
    width: 100% !important;
    height: 100% !important;
    object-fit: cover !important;
    display: block !important;
    margin: 0 !important;
    padding: 0 !important;
    max-width: 100% !important;
    border-radius: 4px !important;  /* 모서리 둥글게 */
}

/* 이미지 그리드 내부 링크도 동일하게 처리 */
.se-imageStrip-container .se-module-image-link,
.se-imageGroup-container .se-module-image-link,
.se-image-strip .se-module-image-link,
.se-image-resource_group .se-module-image-link {
    display: block !important;
    width: 100% !important;
    height: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
}

/* 이미지 그리드 간격도 Python 코드에서 처리 */

/* === OG 링크(북마크 카드) 스타일 === */
.se-oglink {
    margin: 1em 0 !important;
    border: 1px solid #e0e0e0 !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    background: #fff !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
    transition: all 0.2s ease !important;
    max-width: 400px !important;  /* 최대 너비 제한 */
    margin-left: auto !important;
    margin-right: auto !important;
}
.se-oglink:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.15) !important;
    transform: translateY(-2px) !important;
}
.se-module-oglink {
    display: flex !important;
    align-items: stretch !important;
    text-decoration: none !important;
    color: inherit !important;
    min-height: 80px !important;  /* 최소 높이 설정 */
}
.se-oglink-thumbnail {
    flex: 0 0 80px !important;  /* 썸네일 크기 축소 */
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    background: #f8f9fa !important;
    border-right: 1px solid #e0e0e0 !important;
}
.se-oglink-thumbnail img {
    max-width: 100% !important;
    max-height: 100% !important;
    object-fit: contain !important;
    padding: 8px !important;  /* 패딩 축소 */
}
.se-oglink-info {
    flex: 1 !important;
    padding: 12px !important;  /* 패딩 축소 */
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
    text-decoration: none !important;
    color: inherit !important;
}
.se-oglink-title {
    font-size: 14px !important;  /* 폰트 크기 축소 */
    font-weight: bold !important;
    color: #333 !important;
    margin: 0 0 6px 0 !important;  /* 마진 축소 */
    line-height: 1.3 !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
}
.se-oglink-summary {
    font-size: 12px !important;  /* 폰트 크기 축소 */
    color: #666 !important;
    margin: 0 0 6px 0 !important;  /* 마진 축소 */
    line-height: 1.3 !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
}
.se-oglink-url {
    font-size: 11px !important;  /* 폰트 크기 축소 */
    color: #999 !important;
    margin: 0 !important;
    font-family: monospace !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
}
/* === 반응형 일반 이미지 중앙정렬 (그리드 제외) === */
/* 이미지 부모 요소들 중앙정렬 */
.se-component.se-image,
.se-section-image,
.se-module-image {
    text-align: center !important;
    display: block !important;
    max-width: 100% !important;
    margin: 0 auto !important;
}

/* === 통합 이미지 간격 관리 === */
/* 모든 이미지 관련 요소의 기본 간격 (Python 코드에서 인라인 스타일로 처리) */
/* CSS는 백업용으로만 유지 */

/* 이미지 그리드 내부 요소들은 마진 완전 제거 (gap으로 간격 처리) */
.se-imageStrip-container .se-module.se-module-image,
.se-imageGroup-container .se-module.se-module-image,
.se-image-strip .se-image-resource,
.se-image-resource_group .se-image-resource,
.se-imageStrip-container .se-section-image,
.se-imageGroup-container .se-section-image,
.se-image-strip .se-section-image,
.se-image-resource_group .se-section-image,
.se-imageStrip-container .se-component.se-image,
.se-imageGroup-container .se-component.se-image,
.se-image-strip .se-component.se-image,
.se-image-resource_group .se-component.se-image {
    margin: 0 !important;
    padding: 0 !important;
}

/* 일반 이미지 중앙정렬 */
img:not(.se-image-resource):not(.se-sticker-image) {
    display: block !important;
    margin-left: auto !important;
    margin-right: auto !important;
    max-width: 100% !important;
    height: auto !important;
    width: auto !important;  /* 자동 너비 */
}

/* 일반 이미지 링크 중앙정렬 */
.se-module-image-link:not(.se-imageStrip-container .se-module-image-link):not(.se-imageGroup-container .se-module-image-link) {
    display: block !important;
    text-align: center !important;
    margin-left: auto !important;
    margin-right: auto !important;
    width: fit-content !important;
    max-width: 100% !important;
}

/* === 반응형 미디어 쿼리 === */
@media (min-width: 768px) {
    .se-main-container {
        max-width: 900px !important;
        padding: 0 20px !important;
    }
    
    .se-sticker-image {
        max-width: 150px !important;
    }
    
    /* 이미지 그리드 간격 고정 */
    .se-imageStrip-container,
    .se-imageGroup-container,
    .se-image-strip,
    .se-image-resource_group {
        gap: 0 !important;  /* gap 제거하고 margin으로 간격 제어 */
    }
    
    /* 이미지 그리드 내부 요소들 사이 간격 강제 적용 */
    .se-imageStrip-container > .se-module.se-module-image:not(:last-child),
    .se-imageGroup-container > .se-module.se-module-image:not(:last-child),
    .se-image-strip > .se-image-resource:not(:last-child),
    .se-image-resource_group > .se-image-resource:not(:last-child) {
        margin-right: 4px !important;
        margin-bottom: 4px !important;  /* 세로 간격도 고정 */
    }
    
    .se-imageStrip-container .se-module.se-module-image,
    .se-imageGroup-container .se-module.se-module-image,
    .se-image-strip .se-image-resource,
    .se-image-resource_group .se-image-resource {
        min-height: 250px !important;
        max-height: 500px !important;
        height: 300px !important;  /* 태블릿에서 더 큰 높이 */
    }
    
    /* 이미지 그룹 - 태블릿에서도 슬라이드 형태 */
    .se-imageGroup-container {
        min-height: 250px !important;  /* 최소 높이 설정 */
        max-height: 500px !important;  /* 최대 높이 제한 */
        height: 300px !important;  /* 기본 높이 - 다른 그리드와 동일 */
        margin: 0 0 4px 0 !important;  /* 다른 그리드와 동일한 간격 */
        overflow-x: auto !important;  /* 가로 스크롤 활성화 */
        overflow-y: hidden !important;  /* 세로 스크롤 비활성화 */
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        gap: 4px !important;  /* 다른 그리드와 동일한 간격 */
        justify-content: flex-start !important;  /* 왼쪽 정렬 */
        align-items: stretch !important;
        width: 100% !important;
        max-width: 100% !important;
        padding: 0 !important;
        scroll-behavior: smooth !important;  /* 부드러운 스크롤 */
        -webkit-overflow-scrolling: touch !important;  /* iOS 부드러운 스크롤 */
    }
    
    .se-imageGroup-item {
        display: flex !important;
        flex-direction: column !important;
        flex-wrap: nowrap !important;
        gap: 0 !important;
        justify-content: center !important;
        align-items: stretch !important;
        flex: 0 0 50% !important;  /* strip의 1개 이미지와 동일한 크기 */
        width: 50% !important;
        height: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
        min-width: 50% !important;  /* 최소 너비 보장 */
    }
    .se-imageGroup-container .se-module.se-module-image {
        min-height: 250px !important;  /* 최소 높이 설정 */
        max-height: 500px !important;  /* 최대 높이 제한 */
        height: 300px !important;  /* 기본 높이 - 다른 그리드와 동일 */
        display: flex !important;
        flex-direction: column !important;
        align-items: stretch !important;
        box-sizing: border-box !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    

}

@media (min-width: 1024px) {
    .se-main-container {
        max-width: 1000px !important;
        padding: 0 30px !important;
    }
    
    .se-sticker-image {
        max-width: 180px !important;
    }
    
    /* 이미지 그리드 간격 고정 */
    .se-imageStrip-container,
    .se-imageGroup-container,
    .se-image-strip,
    .se-image-resource_group {
        gap: 0 !important;  /* gap 제거하고 margin으로 간격 제어 */
    }
    
    /* 이미지 그리드 내부 요소들 사이 간격 강제 적용 */
    .se-imageStrip-container > .se-module.se-module-image:not(:last-child),
    .se-imageGroup-container > .se-module.se-module-image:not(:last-child),
    .se-image-strip > .se-image-resource:not(:last-child),
    .se-image-resource_group > .se-image-resource:not(:last-child) {
        margin-right: 4px !important;
        margin-bottom: 4px !important;  /* 세로 간격도 고정 */
    }
    
    .se-imageStrip-container .se-module.se-module-image,
    .se-imageGroup-container .se-module.se-module-image,
    .se-image-strip .se-image-resource,
    .se-image-resource_group .se-image-resource {
        min-height: 300px !important;
        max-height: 600px !important;
        height: 350px !important;  /* 데스크톱에서 더 큰 높이 */
    }
    
    /* 이미지 그룹 - 데스크톱에서도 슬라이드 형태 */
    .se-imageGroup-container {
        min-height: 300px !important;  /* 최소 높이 설정 */
        max-height: 600px !important;  /* 최대 높이 제한 */
        height: 350px !important;  /* 기본 높이 - 다른 그리드와 동일 */
        margin: 0 0 4px 0 !important;  /* 다른 그리드와 동일한 간격 */
        overflow-x: auto !important;  /* 가로 스크롤 활성화 */
        overflow-y: hidden !important;  /* 세로 스크롤 비활성화 */
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        gap: 4px !important;  /* 다른 그리드와 동일한 간격 */
        justify-content: flex-start !important;  /* 왼쪽 정렬 */
        align-items: stretch !important;
        width: 100% !important;
        max-width: 100% !important;
        padding: 0 !important;
        scroll-behavior: smooth !important;  /* 부드러운 스크롤 */
        -webkit-overflow-scrolling: touch !important;  /* iOS 부드러운 스크롤 */
    }
    
    .se-imageGroup-item {
        display: flex !important;
        flex-direction: column !important;
        flex-wrap: nowrap !important;
        gap: 0 !important;
        justify-content: center !important;
        align-items: stretch !important;
        flex: 0 0 50% !important;  /* strip의 1개 이미지와 동일한 크기 */
        width: 50% !important;
        height: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
        min-width: 50% !important;  /* 최소 너비 보장 */
    }
    .se-imageGroup-container .se-module.se-module-image {
        min-height: 300px !important;  /* 최소 높이 설정 */
        max-height: 600px !important;  /* 최대 높이 제한 */
        height: 350px !important;  /* 기본 높이 - 다른 그리드와 동일 */
        display: flex !important;
        flex-direction: column !important;
        align-items: stretch !important;
        box-sizing: border-box !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    

}

/* oEmbed(유튜브 등) 반응형 동영상 */
.se-module-oembed {
    position: relative !important;
    width: 100% !important;
    padding-top: 56.25% !important; /* 16:9 비율 */
    height: 0 !important;
    margin: 0 auto !important;
    background: #000 !important;
}
.se-module-oembed iframe {
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
    width: 100% !important;
    height: 100% !important;
    border: 0 !important;
    background: #000 !important;
}
</style>
"""

    # 새 HTML로 저장 (본문+스타일만)
    new_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
{custom_style}
</head>
<body>
{str(main_container)}
</body>
</html>
"""
    return new_html, blog_title

# 아래는 예시 실행 코드(삭제 가능)
if __name__ == "__main__":
    blog_id = "monkey_dream"
    log_no = "223816008103"
    url = f"https://m.blog.naver.com/{blog_id}/{log_no}"
    html, title = extract_blog_html(url)
    with open("blog_body_only.html", "w", encoding="utf-8") as f:
        f.write(html)