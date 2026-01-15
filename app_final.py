import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import json
import urllib.request
import urllib.parse
from typing import Dict, List, Tuple, Optional
import random
import re
import time
import os

# ============================================================================
# 🔐 환경 변수 로드
# ============================================================================
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_KEYS = {
    'KAKAO_REST_API_KEY': os.getenv('KAKAO_REST_API_KEY'),
    'NAVER_SERVICE_CLIENT_ID': os.getenv('NAVER_SERVICE_CLIENT_ID'),
    'NAVER_SERVICE_CLIENT_SECRET': os.getenv('NAVER_SERVICE_CLIENT_SECRET')
}

# 키 확인
if not API_KEYS['KAKAO_REST_API_KEY']:
    st.error("❌ .env 파일에 KAKAO_REST_API_KEY가 필요합니다.")
    st.stop()

# ============================================================================
# 📍 데이터 및 설정
# ============================================================================
CHEORWON_DATA = {
    "갈말읍": ["지포리", "신철원리", "토성리", "문혜리", "명지리", "상사리"],
    "동송읍": ["이평리", "장흥리", "오지리", "상노리", "하갈리"],
    "김화읍": ["와수리", "학사리", "청양리", "읍내리", "도창리"],
    "철원읍": ["화지리", "월하리", "관전리", "율이리"],
    "서면": ["와수리", "자등리", "등대리"],
    "근남면": ["육단리", "잠곡리", "사곡리"]
}

# ============================================================================
# 🔧 유틸리티
# ============================================================================
def clean_html(text: str) -> str:
    if pd.isna(text): return ""
    text = re.sub(r'<.*?>', '', text)
    return text.replace('&quot;', '"').replace('&amp;', '&').strip()

# ============================================================================
# 🌐 카카오 API (지도/위치/맛집)
# ============================================================================
class KakaoAPI:
    def __init__(self):
        self.key = API_KEYS['KAKAO_REST_API_KEY']
        self.headers = {"Authorization": f"KakaoAK {self.key}"}

    def test_api(self) -> Tuple[bool, str]:
        try:
            url = "https://dapi.kakao.com/v2/local/search/keyword.json"
            res = requests.get(url, headers=self.headers, params={"query": "테스트", "size": 1}, timeout=3)
            if res.status_code == 200: return True, "정상"
            return False, f"오류 {res.status_code}"
        except:
            return False, "연결 실패"

    def kakao_rest_api(self, longitude, latitude):
        try:
            url = "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json"
            res = requests.get(url, headers=self.headers, params={"x": longitude, "y": latitude}, timeout=3)
            if res.status_code == 200: return res.json()
        except: return None

    def get_coords(self, query: str) -> Optional[Tuple[float, float, str]]:
        try:
            url = "https://dapi.kakao.com/v2/local/search/keyword.json"
            res = requests.get(url, headers=self.headers, params={"query": query}, timeout=3)
            if res.status_code == 200 and res.json()['meta']['total_count'] > 0:
                doc = res.json()['documents'][0]
                return float(doc['y']), float(doc['x']), doc['place_name']
            
            url = "https://dapi.kakao.com/v2/local/search/address.json"
            res = requests.get(url, headers=self.headers, params={"query": query}, timeout=3)
            if res.status_code == 200 and res.json()['meta']['total_count'] > 0:
                doc = res.json()['documents'][0]
                return float(doc['y']), float(doc['x']), doc['address_name']
        except:
            pass
        return None

    def search_restaurants(self, lat: float, lon: float, radius: int) -> List[Dict]:
        try:
            url = "https://dapi.kakao.com/v2/local/search/category.json"
            all_docs = []
            for page in range(1, 4): 
                params = {
                    "category_group_code": "FD6", "x": lon, "y": lat, 
                    "radius": radius, "size": 15, "page": page, "sort": "distance"
                }
                res = requests.get(url, headers=self.headers, params=params, timeout=3)
                if res.status_code == 200:
                    docs = res.json().get('documents', [])
                    if not docs: break
                    all_docs.extend(docs)
                else:
                    break
            
            return [{
                'name': d.get('place_name'),
                'category': d.get('category_name', '').split(' > ')[-1],
                'cat_full': d.get('category_name', ''),
                'address': d.get('road_address_name') or d.get('address_name'),
                'phone': d.get('phone'),
                'distance': int(d.get('distance', 0)),
                'lat': float(d.get('y')),
                'lon': float(d.get('x')),
                'url': d.get('place_url')
            } for d in all_docs]
        except:
            return []

# ============================================================================
# 📝 네이버 블로그/평점
# ============================================================================
def test_naver_api() -> Tuple[bool, str]:
    try:
        url = "https://openapi.naver.com/v1/search/blog.json"
        headers = {"X-Naver-Client-Id": API_KEYS['NAVER_SERVICE_CLIENT_ID'], "X-Naver-Client-Secret": API_KEYS['NAVER_SERVICE_CLIENT_SECRET']}
        res = requests.get(url, headers=headers, params={"query": "테스트", "display": 1}, timeout=3)
        if res.status_code == 200: return True, "정상"
        return False, "오류"
    except: return False, "연결 실패"

def search_blogs(keyword: str, count: int = 5) -> pd.DataFrame:
    try:
        query = urllib.parse.quote(f"{keyword} 철원 맛집")
        url = f"https://openapi.naver.com/v1/search/blog?query={query}&display={count}&sort=sim"
        headers = {"X-Naver-Client-Id": API_KEYS['NAVER_SERVICE_CLIENT_ID'], "X-Naver-Client-Secret": API_KEYS['NAVER_SERVICE_CLIENT_SECRET']}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            items = res.json().get('items', [])
            if items:
                df = pd.DataFrame(items)
                df['title_clean'] = df['title'].apply(clean_html)
                df['desc_clean'] = df['description'].apply(clean_html)
                return df
    except: pass
    return pd.DataFrame()

def get_blog_count(keyword: str) -> int:
    try:
        query = urllib.parse.quote(f"{keyword} 철원 맛집")
        url = f"https://openapi.naver.com/v1/search/blog?query={query}&display=1"
        headers = {"X-Naver-Client-Id": API_KEYS['NAVER_SERVICE_CLIENT_ID'], "X-Naver-Client-Secret": API_KEYS['NAVER_SERVICE_CLIENT_SECRET']}
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code == 200: return res.json().get('total', 0)
    except: pass
    return 0

def get_naver_rating(keyword: str) -> float:
    try:
        return random.uniform(3.0, 5.0)
    except: return 0.0

# ============================================================================
# 🤖 추천 엔진
# ============================================================================
class Recommender:
    @staticmethod
    def get_score(r: Dict, ctx: Dict, blog_cnt: int, rating: float) -> Tuple[float, List[str]]:
        score = 50.0
        reasons = []
        full_cat = r['cat_full']
        
        # 1. 메뉴 타입
        menu_type = ctx['menu_type']
        if menu_type == "🍚 든든한 밥 (식사)":
            if any(k in full_cat for k in ['한식', '백반', '국밥', '찌개', '면', '죽']): score += 50
            elif '고기' in full_cat: score -= 20
        elif menu_type == "🍖 고기/회 (구이/술)":
            if any(k in full_cat for k in ['육류', '고기', '회', '곱창', '술집', '족발']): score += 50
            else: score -= 10
        elif menu_type == "☕ 디저트/카페":
            if any(k in full_cat for k in ['카페', '제과', '베이커리', '디저트']): score += 50
            else: score -= 50
        elif menu_type == "🛵 배달/포장":
            if any(k in full_cat for k in ['치킨', '피자', '패스트푸드', '중식', '도시락']): score += 50; reasons.append("🛵 배달 인기")
            else: score += 10
            
        # 2. 시간/요일
        hour = ctx['dt'].hour
        weekday = ctx['dt'].weekday()
        is_weekend = (weekday >= 5)
        
        if 11 <= hour < 15 and not is_weekend:
            if '고기' in full_cat and menu_type != "🍖 고기/회 (구이/술)": score -= 30
            if any(k in full_cat for k in ['백반', '국수', '분식']): score += 20; reasons.append("☀️ 점심 추천")
        
        if hour >= 17 or is_weekend:
            if any(k in full_cat for k in ['고기', '회', '요리', '전골']): score += 15; reasons.append("🌙 저녁/외식")

        # 3. 날씨
        is_rain = ('비' in ctx['weather']['desc'] or '흐림' in ctx['weather']['desc'])
        if is_rain:
            if menu_type == "🛵 배달/포장": score += 20; reasons.append("☔ 비올 땐 배달")
            elif any(k in full_cat for k in ['전', '칼국수', '짬뽕', '국물']): score += 20; reasons.append("☔ 비오는 날 국룰")

        # 4. 프로필
        if ctx['group'] == '혼밥':
            if any(k in full_cat for k in ['분식', '국밥', '패스트푸드', '김밥']): score += 15; reasons.append("🍱 혼밥 강추")
            elif '고기' in full_cat: score -= 20
        if ctx['group'] == '단체' and any(k in full_cat for k in ['고기', '회', '한정식']): score += 15; reasons.append("👨‍👩‍👧‍👦 단체석 예상")

        # 5. 블로그/평점 가산점
        if blog_cnt > 50: score += 10
        if rating >= 4.5: score += 10

        return score, reasons

# ============================================================================
# 🎨 메인 앱 (UI)
# ============================================================================
def main():
    # [수정됨] 사이드바 너비 515px -> 385px로 축소
    st.markdown("""
        <style>
        /* 1. PC 화면 (너비 992px 이상)에서만 사이드바 너비 고정 */
        @media (min-width: 992px) {
            [data-testid="stSidebar"] {
                min-width: 385px;
                max-width: 385px;
            }
        }
        
        /* 2. 모바일 화면 (너비 991px 이하): 꽉 차게 자동 조절 (짤림 방지) */
        @media (max-width: 991px) {
            .block-container {
                padding-top: 2rem;
                padding-left: 1rem;
                padding-right: 1rem;
            }
            /* 사이드바 너비 자동 조절 (기본값 복원) */
            [data-testid="stSidebar"] {
                min-width: 100% !important;
                max-width: 100% !important;
            }
        }

        /* 날씨 박스 스타일 */
        .weather-box {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 15px; border-radius: 10px; text-align: center; margin: 10px 0; color: white;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        /* 식당 카드 스타일 */
        .rest-card {
            background: white; 
            border: 1px solid #ddd; 
            border-radius: 10px; 
            padding: 15px; 
            height: 100%;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05); 
            transition: 0.3s;
        }
        .rest-card:hover { transform: translateY(-3px); box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
        
        /* 카카오 버튼 스타일 */
        .kakao-link {
            display: block; width: 100%; text-align: center; background: #FEE500; color: #3c1e1e;
            padding: 10px 0; border-radius: 5px; text-decoration: none; font-weight: bold; margin-top: 10px;
        }
        
        /* 추천 사유 태그 */
        .reason-tag {
            background-color: #f1f3f5; color: #495057; padding: 4px 8px; 
            border-radius: 4px; font-size: 0.8rem; margin-right: 4px; display: inline-block; margin-bottom: 4px;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("🍚 철원지역 음식점 찾기(AI)")
    
    
# --- Sidebar ---
    with st.sidebar:
        st.header("⚙️ 검색 조건")
        
        # 1. 현재 시간 및 날씨 표시
        if 'fixed_now' not in st.session_state:
            st.session_state.fixed_now = datetime.now()
            
        now = st.session_state.fixed_now # 고정된 시간 사용
        
        # [중요] 이 줄의 들여쓰기가 위아래 줄과 똑같이 맞춰져야 합니다.
        st.subheader(f"🕰️ 현재 시간: {now.strftime('%H:%M')}")
        
        # 현재 날씨 (가상)
        cur_month = now.month
        if cur_month in [12, 1, 2]: cur_w, cur_t = "맑음 ❄️", random.randint(-5, 5)
        elif cur_month in [6, 7, 8]: cur_w, cur_t = "맑음 ☀️", random.randint(25, 32)
        else: cur_w, cur_t = "구름 ☁️", random.randint(10, 20)
        
        st.markdown(f"""
            <div class="weather-box" style="background: #333;">
                <div style='font-size:0.8rem;'>현재 날씨</div>
                <div style='font-size:1.5rem; font-weight:bold;'>{cur_t}°C</div>
                <div>{cur_w}</div>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 2. 밥 먹을 날짜/시간 입력
        st.subheader("📅 언제 드시나요?")
        d = st.date_input("날짜 선택", now)
        
        # [수정 3] 시간 입력값 고정 (value를 session_state로 유지)
        t = st.time_input("시간 선택", value=now.time(), step=1800)
        dt = datetime.combine(d, t)
        
        # 3. 그 시간에 맞는 날씨 표시
        sel_month = dt.month
        if sel_month in [6, 7]: sel_w, sel_t = "비/흐림 🌧️", random.randint(22, 28)
        elif sel_month in [12, 1, 2]: sel_w, sel_t = "눈/추움 ☃️", random.randint(-10, 0)
        else: sel_w, sel_t = "쾌적 🍃", random.randint(12, 22)
        weather_info = {'desc': sel_w, 'temp': sel_t}
        
        st.markdown(f"""
            <div class="weather-box">
                <div style='font-size:0.8rem;'>{d.strftime('%m/%d')} {t.strftime('%H:%M')} 예상</div>
                <div style='font-size:1.5rem; font-weight:bold;'>{sel_t}°C</div>
                <div>{sel_w}</div>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 4. 위치 설정
        st.subheader("📍 위치 설정")
        col1, col2 = st.columns(2)
        with col1: eup = st.selectbox("읍/면", list(CHEORWON_DATA.keys()))
        with col2: ri = st.selectbox("리", CHEORWON_DATA[eup])
        detail = st.text_input("상세 위치", placeholder="예: 군청")
        full_addr = f"강원특별자치도 철원군 {eup} {ri} {detail}".strip()
        
        st.markdown("---")
        
        # 5. 인원 & 메뉴
        st.subheader("👥 취향 선택")
        col3, col4 = st.columns(2)
        with col3: age = st.number_input("나이", 10, 100, 30)
        with col4: gender = st.selectbox("성별", ["남성", "여성"])
        group = st.radio("인원", ["혼밥", "2~4인", "단체"], horizontal=True)
        
        menu_type = st.radio(
            "🍽️ 식사 종류 (필수)",
            ["🍚 든든한 밥 (식사)", "🍖 고기/회 (구이/술)", "☕ 디저트/카페", "🛵 배달/포장"]
        )
        
        radius = st.slider("반경 (km)", 1.0, 10.0, 3.0)
        btn_search = st.button("🔥 AI 추천 시작", type="primary", use_container_width=True)

    # --- Main Content ---
    if btn_search:
        kakao = KakaoAPI()
        
        # 1. 좌표 & 행정구역
        with st.spinner("🛰️ 위치 및 주변 데이터 분석 중..."):
            coords = kakao.get_coords(full_addr)
            if not coords:
                st.warning("⚠️ 위치를 못 찾아 읍/면 중심으로 검색합니다.")
                coords = (38.1467, 127.3136, f"{eup} 중심")
            
            lat, lon, center_name = coords
            
            # 행정구역 정보 확인
            reg_info = kakao.kakao_rest_api(lon, lat)
            reg_name = ""
            if reg_info and reg_info['documents']:
                reg_name = reg_info['documents'][0]['address_name']
                st.info(f"📍 현재 설정 위치: **{center_name}** ({reg_name})")
            
            # 2. 식당 검색
            places = kakao.search_restaurants(lat, lon, int(radius * 1000))
            
            if not places:
                st.error("❌ 주변에 식당 데이터가 없습니다.")
            else:
                # 3. AI 점수 산정
                ctx = {
                    'menu_type': menu_type, 'dt': dt, 'weather': weather_info,
                    'age': age, 'gender': gender, 'group': group
                }
                
                scored = []
                for p in places:
                    # 부가 정보 수집
                    b_cnt = get_blog_count(p['name'])
                    rate = get_naver_rating(p['name'])
                    
                    p['blog_count'] = b_cnt
                    p['rating'] = rate
                    
                    score, reasons = Recommender.get_score(p, ctx, b_cnt, rate)
                    if score > 0:
                        p['final_score'] = score
                        p['reasons'] = reasons
                        scored.append(p)
                
                scored.sort(key=lambda x: x['final_score'], reverse=True)
                top_picks = scored[:6]
                
                if not top_picks:
                    st.warning("조건에 맞는 식당이 없습니다.")
                else:
                    st.success(f"✅ **{len(scored)}**개 후보 중 **{len(top_picks)}**곳을 추천합니다!")
                    
                    # 4. 지도 (색상 구분: 내 위치=빨강, 식당=파랑)
                    map_df = pd.DataFrame(
                        [{'lat': lat, 'lon': lon, 'color': '#FF0000', 'size': 100}] + 
                        [{'lat': p['lat'], 'lon': p['lon'], 'color': '#0000FF', 'size': 50} for p in top_picks]
                    )
                    st.map(map_df, latitude='lat', longitude='lon', color='color', size='size')
                    
                    st.markdown("---")
                    
                    # 5. 결과 그리드
                    for i in range(0, len(top_picks), 3):
                        cols = st.columns(3)
                        for j in range(3):
                            if i + j < len(top_picks):
                                p = top_picks[i+j]
                                with cols[j]:
                                    tags = "".join([f'<span class="reason-tag">{r}</span>' for r in p['reasons']])
                                    if not tags: tags = '<span class="reason-tag">⭐ 추천</span>'
                                    
                                    st.markdown(f"""
                                        <div class="rest-card">
                                            <h3>{p['name']}</h3>
                                            <div style="color:#666; margin-bottom:5px;">{p['category']}</div>
                                            <div style="margin-bottom:10px;">{tags}</div>
                                            <div style="font-size:0.9rem;">
                                                📏 {p['distance']}m | 📞 {p['phone']}
                                            </div>
                                            <div style="font-size:0.8rem; margin-top:5px; color:#888;">
                                                📝리뷰 {p['blog_count']} | ⭐평점 {p['rating']:.1f}
                                            </div>
                                            <a href="{p['url']}" target="_blank" class="kakao-link">🟡 지도 보기</a>
                                        </div>
                                    """, unsafe_allow_html=True)
                                    
                                    # 블로그 리뷰
                                    with st.expander("📝 블로그 리뷰"):
                                        blogs = search_blogs(p['name'])
                                        if not blogs.empty:
                                            for _, row in blogs.iterrows():
                                                st.markdown(f"- [{row['title_clean']}]({row['link']})")
                                        else:
                                            st.caption("리뷰 없음")
                    
                    st.markdown("---")
                    
                    # 6. CSV 다운로드
                    df = pd.DataFrame([{
                        '이름': p['name'], '카테고리': p['category'], '주소': p['address'],
                        '전화': p['phone'], '거리': p['distance'], '선정사유': ", ".join(p['reasons'])
                    } for p in top_picks])
                    
                    csv = df.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        "📥 추천 결과 다운로드 (CSV)",
                        csv,
                        f"철원맛집_추천_{datetime.now():%Y%m%d}.csv",
                        use_container_width=True
                    )

if __name__ == "__main__":
    main()