import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


def crawl_and_save_blog_post(blog_id: str, post_num: str) -> str:
    """
    네이버 블로그 ID와 게시물 번호를 받아 HTML과 CSS를 결합하여 파일로 저장합니다.

    Args:
        blog_id (str): 크롤링할 네이버 블로그 ID
        post_num (str): 크롤링할 게시물 번호

    Returns:
        str: 저장된 파일의 경로 또는 에러 메시지
    """
    # 1. URL 생성 및 HTML 가져오기
    # 네이버 블로그는 모바일 버전 페이지가 구조가 더 간단하고 CSS 처리가 용이합니다.
    target_url = f"https://m.blog.naver.com/{blog_id}/{post_num}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.get(target_url, headers=headers)
        response.raise_for_status()  # HTTP 에러 발생 시 예외 처리
    except requests.exceptions.RequestException as e:
        return f"❌ 오류: 페이지를 가져올 수 없습니다. URL을 확인하세요. ({e})"

    # 2. BeautifulSoup으로 HTML 파싱
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 3. 필요한 요소만 추출 (se-main-container 기준으로 필터링)
    main_container = soup.find(class_='se-main-container')
    if main_container:
        # 새로운 HTML 문서 생성
        new_soup = BeautifulSoup('<!DOCTYPE html><html><head></head><body></body></html>', 'html.parser')
        new_soup.body.append(main_container.extract())
        soup = new_soup
    
    # 4. 불필요한 요소들 제거
    for unwanted in soup.find_all(class_=['blog_fe_feed', 'section_t1']):
        unwanted.decompose()
    
    # 5. 이미지 품질 개선 및 스타일 적용
    # 모든 이미지의 src를 고해상도로 변경하고 필요한 스타일 추가
    for img in soup.find_all('img', class_='se-image-resource'):
        # 저해상도 블러 이미지를 고해상도로 변경
        if img.get('src') and 'type=w80_blur' in img['src']:
            img['src'] = img['src'].replace('type=w80_blur', 'type=w800')
        
        # data-lazy-src가 있으면 src로 설정
        if img.get('data-lazy-src'):
            img['src'] = img['data-lazy-src']
            
        # 이미지에 기본 스타일 적용
        img['style'] = 'display: block !important; margin-left: auto !important; margin-right: auto !important; max-width: 100% !important; height: auto !important;'
    
    # 이미지 링크에도 스타일 적용
    for link in soup.find_all('a', class_='se-module-image-link'):
        link['style'] = 'display: block !important; text-align: center !important; margin-left: auto !important; margin-right: auto !important; width: fit-content !important;'

    # 6. CSS 추출 및 통합
    # 모든 <link rel="stylesheet"> 태그와 <style> 태그 찾기
    css_tags = soup.find_all(['link', 'style'])

    combined_css = ""
    for tag in css_tags:
        if tag.name == 'style':
            # <style> 태그 안의 CSS 코드 직접 추가
            combined_css += tag.get_text() + "\n"
        elif tag.name == 'link' and tag.get('rel') == ['stylesheet'] and 'href' in tag.attrs:
            # <link> 태그의 href 속성에서 CSS 파일 URL 가져오기
            css_url = urljoin(target_url, tag['href'])
            try:
                css_response = requests.get(css_url, headers=headers)
                if css_response.status_code == 200:
                    combined_css += css_response.text + "\n"
            except requests.exceptions.RequestException:
                # CSS 파일 로드 실패 시 무시하고 계속 진행
                pass

        # 원본 <link>와 <style> 태그는 삭제하여 중복 방지
        tag.decompose()

    # 7. 기본 스타일 CSS 추가
    try:
        with open("style.css", "r", encoding="utf-8") as f:
            base_css = f.read()
            # <style> 태그가 있다면 제거하고 내용만 추출
            if base_css.strip().startswith('<style>') and base_css.strip().endswith('</style>'):
                base_css = base_css.strip()[7:-8]  # <style>과 </style> 제거
    except FileNotFoundError:
        base_css = ""

    # 8. 통합된 CSS를 새로운 <style> 태그로 만들어 <head>에 추가
    # 기본 스타일을 먼저 추가하고, 그 다음에 페이지의 CSS 추가
    final_css = base_css + "\n" + combined_css if base_css else combined_css
    
    if final_css:
        new_style_tag = soup.new_tag('style')
        new_style_tag.string = final_css

        # 불필요한 스크립트 태그 제거 (선택 사항, 로딩 속도 개선)
        for script in soup.find_all('script'):
            script.decompose()

        soup.head.append(new_style_tag)

    # 9. 완성된 HTML을 파일로 저장
    output_filename = f"crawled_{blog_id}_{post_num}.html"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(str(soup))

    return f"✅ 성공! '{output_filename}' 파일로 저장되었습니다."


# --- Streamlit UI 부분 ---
st.set_page_config(page_title="Naver Blog Crawler", page_icon="📝")

st.title("📝 네이버 블로그 크롤러")
st.markdown("블로그 ID와 게시물 번호를 입력하면, 해당 포스트의 HTML과 CSS를 합쳐 단일 파일로 저장합니다.")

st.info(
    "💡 **참고 URL**: `https://blog.naver.com/monkey_dream/223816008103`\n - **블로그 ID**: `monkey_dream`\n - **게시물 번호**: `223816008103`",
    icon="ℹ️")

# 사용자 입력
blog_id_input = st.text_input("블로그 ID (Blog ID)", placeholder="예: monkey_dream")
post_num_input = st.text_input("게시물 번호 (Post Number)", placeholder="예: 223816008103")


if st.button("🚀 크롤링 시작!"):
    st.markdown("---")
    if blog_id_input and post_num_input:
        with st.spinner("블로그 포스트를 크롤링하고 있습니다... 잠시만 기다려주세요."):
            result_message = crawl_and_save_blog_post(blog_id_input, post_num_input)

        if "성공" in result_message:
            st.success(result_message)
            
            # 원본 블로그 링크 생성 및 표시
            original_url = f"https://blog.naver.com/{blog_id_input}/{post_num_input}"
            st.info(f"🔗 **원본 블로그 링크**: [{original_url}]({original_url})")
            
            # 다운로드 버튼 제공 (선택 사항)
            output_filename = f"crawled_{blog_id_input}_{post_num_input}.html"
            with open(output_filename, "r", encoding="utf-8") as f:
                st.download_button(
                    label=f"📄 {output_filename} 다운로드",
                    data=f.read(),
                    file_name=output_filename,
                    mime='text/html'
                )
        else:
            st.error(result_message)
    else:
        st.warning("블로그 ID와 게시물 번호를 모두 입력해주세요.")