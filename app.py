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

# Streamlit 메뉴 및 툴바 숨기기 (프로덕션 환경용)
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
.stDeployButton {display:none;}
footer {visibility: hidden;}
#stDecoration {display:none;}
header {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.title("📝 네이버 블로그 크롤러")
st.markdown("블로그 ID와 게시물 번호를 입력하면, 해당 포스트의 HTML과 CSS를 합쳐 단일 파일로 저장합니다.")

st.info(
    "💡 **참고 URL**: `https://blog.naver.com/monkey_dream/223816008103`\n - **블로그 ID**: `monkey_dream`\n - **게시물 번호**: `223816008103`",
    icon="ℹ️")

# 세션 상태 초기화
if 'extraction_completed' not in st.session_state:
    st.session_state.extraction_completed = False
if 'extraction_data' not in st.session_state:
    st.session_state.extraction_data = {}
if 'download_completed' not in st.session_state:
    st.session_state.download_completed = False

# 사용자 입력 - 세션 상태에서 기본값 가져오기
blog_id_input = st.text_input(
    "블로그 ID (Blog ID)", 
    value=st.session_state.extraction_data.get('blog_id', ''),
    placeholder="예: monkey_dream"
)
post_num_input = st.text_input(
    "게시물 번호 (Post Number)", 
    value=st.session_state.extraction_data.get('post_num', ''),
    placeholder="예: 223816008103"
)

if st.button("🚀 추출 시작!"):
    st.markdown("---")
    if blog_id_input and post_num_input:
        with st.spinner("블로그 포스트를 크롤링하고 있습니다... 잠시만 기다려주세요."):
            result_message = crawl_and_save_blog_post(blog_id_input, post_num_input)

        if "성공" in result_message:
            # 세션 상태에 결과 저장
            output_filename = f"crawled_{blog_id_input}_{post_num_input}.html"
            with open(output_filename, "r", encoding="utf-8") as f:
                html_content = f.read()
            
            st.session_state.extraction_completed = True
            st.session_state.extraction_data = {
                'blog_id': blog_id_input,
                'post_num': post_num_input,
                'html_content': html_content,
                'output_filename': output_filename,
                'original_url': f"https://blog.naver.com/{blog_id_input}/{post_num_input}",
                'result_message': result_message
            }
            st.session_state.download_completed = False
            
            st.success(result_message)
        else:
            st.error(result_message)
            st.session_state.extraction_completed = False
    else:
        st.warning("블로그 ID와 게시물 번호를 모두 입력해주세요.")
        st.session_state.extraction_completed = False

# 추출 완료된 경우 결과 표시
if st.session_state.extraction_completed:
    st.markdown("---")
    
    data = st.session_state.extraction_data
    
    # 다운로드 완료 메시지 표시
    if st.session_state.download_completed:
        st.success("✅ 다운로드가 완료되었습니다!")
    
    # 원본 블로그 링크 표시
    st.info(f"🔗 **원본 블로그 링크**: [{data['original_url']}]({data['original_url']})")
    
    # HTML 미리보기 및 복사 기능
    col1, col2 = st.columns(2)
    
    with col1:
        # 다운로드 버튼 클릭 시 세션 상태 업데이트
        if st.download_button(
            label=f"📄 {data['output_filename']} 다운로드",
            data=data['html_content'],
            file_name=data['output_filename'],
            mime='text/html',
            key="download_btn"
        ):
            st.session_state.download_completed = True
            st.rerun()  # 페이지 새로고침하여 다운로드 완료 메시지 표시
    
    with col2:
        # JavaScript 기반 클립보드 복사 기능
        copy_button_html = f"""
        <style>
        .copy-button {{
            background-color: #ff4b4b;
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 0.5rem;
            cursor: pointer;
            font-size: 14px;
            margin: 10px 0;
        }}
        .copy-button:hover {{
            background-color: #ff6b6b;
        }}
        #html-content {{
            position: absolute;
            left: -9999px;
        }}
        </style>
        <textarea id="html-content" readonly>{data['html_content']}</textarea>
        <button class="copy-button" onclick="copyToClipboard()">📋 HTML 클립보드에 복사</button>
        <div id="copy-message" style="color: green; font-size: 12px; margin-top: 5px;"></div>
        
        <script>
        function copyToClipboard() {{
            const textArea = document.getElementById('html-content');
            textArea.select();
            textArea.setSelectionRange(0, 99999);
            
            try {{
                document.execCommand('copy');
                document.getElementById('copy-message').innerHTML = '✅ HTML이 클립보드에 복사되었습니다!';
                setTimeout(() => {{
                    document.getElementById('copy-message').innerHTML = '';
                }}, 3000);
            }} catch (err) {{
                navigator.clipboard.writeText(textArea.value).then(() => {{
                    document.getElementById('copy-message').innerHTML = '✅ HTML이 클립보드에 복사되었습니다!';
                    setTimeout(() => {{
                        document.getElementById('copy-message').innerHTML = '';
                    }}, 3000);
                }}).catch(() => {{
                    document.getElementById('copy-message').innerHTML = '❌ 복사 실패. 수동으로 복사해주세요.';
                }});
            }}
        }}
        </script>
        """
        st.components.v1.html(copy_button_html, height=100)
    
    # HTML 실제 렌더링 미리보기
    if st.checkbox("🔍 HTML 미리보기", key="html_preview_checkbox"):
        st.subheader("📄 추출된 블로그 내용 미리보기")
        
        # HTML 내용에서 body 부분만 추출하여 표시 (흰색 배경 적용)
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(data['html_content'], 'html.parser')
            body_content = soup.body
            if body_content:
                # body 내용을 흰색 배경 div로 감싸기
                preview_html = f"""
                <div style="background-color: white; padding: 20px; min-height: 100%; margin: 0;">
                    {str(body_content)}
                </div>
                """
                st.components.v1.html(preview_html, height=600, scrolling=True)
            else:
                # body가 없으면 전체 HTML을 흰색 배경 div로 감싸기
                preview_html = f"""
                <div style="background-color: white; padding: 20px; min-height: 100%; margin: 0;">
                    {data['html_content']}
                </div>
                """
                st.components.v1.html(preview_html, height=600, scrolling=True)
        except:
            # 파싱 실패 시 전체 HTML을 흰색 배경 div로 감싸기
            preview_html = f"""
            <div style="background-color: white; padding: 20px; min-height: 100%; margin: 0;">
                {data['html_content']}
            </div>
            """
            st.components.v1.html(preview_html, height=600, scrolling=True)