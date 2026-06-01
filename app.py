import urllib.parse
import streamlit as st
import pandas as pd
import requests
import re
import datetime
import xml.etree.ElementTree as ET
from streamlit_autorefresh import st_autorefresh

st.set_page_config(layout="wide", page_title="통합 지휘소 V9.4")

# --- [상태 관리 시스템: 6대 알림망 독립 제어] ---
if 'dw_buy_fired' not in st.session_state: st.session_state.dw_buy_fired = False
if 'dw_sell_fired' not in st.session_state: st.session_state.dw_sell_fired = False
if 'space_buy_fired' not in st.session_state: st.session_state.space_buy_fired = False
if 'space_sell_fired' not in st.session_state: st.session_state.space_sell_fired = False
if 'eth_buy_fired' not in st.session_state: st.session_state.eth_buy_fired = False
if 'eth_sell_fired' not in st.session_state: st.session_state.eth_sell_fired = False

# 🛰️ 주가 수집 엔진
def get_naver_price(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        match = re.search(r'<p class="no_today">.*?<span class="blind">([\d,]+)</span>', res.text, re.DOTALL)
        if match: return int(match.group(1).replace(',', ''))
        return 0
    except: return 0

# 🛰️ 가상자산 수집 엔진
def get_upbit_price(ticker="KRW-ETH"):
    try:
        url = f"https://api.upbit.com/v1/ticker?markets={ticker}"
        headers = {"accept": "application/json"}
        res = requests.get(url, headers=headers)
        data = res.json()
        return int(data[0]['trade_price'])
    except: return 0

# 🏠 국토교통부 실거래가 API 저격 엔진
def get_real_estate_api(service_key, lawd_cd, deal_ymd, prop_type="아파트", deal_type="매매"):
    if prop_type == "아파트" and deal_type == "매매":
        url = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
        name_tag = "aptNm"
    elif prop_type == "아파트" and deal_type == "전/월세":
        url = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"
        name_tag = "aptNm"
    elif prop_type == "빌라(연립/다세대)" and deal_type == "매매":
        url = "https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade"
        name_tag = "mhouseNm"
    else: 
        url = "https://apis.data.go.kr/1613000/RTMSDataSvcRHRent/getRTMSDataSvcRHRent"
        name_tag = "mhouseNm"

    full_url = f"{url}?serviceKey={service_key}&LAWD_CD={lawd_cd}&DEAL_YMD={deal_ymd}&numOfRows=100"
    
    try:
        res = requests.get(full_url, timeout=10)
        
        if res.status_code == 200:
            root = ET.fromstring(res.text)
            items = root.findall('.//item')
            data = []
            for item in items:
                try:
                    name_node = item.find(name_tag)
                    prop_name = name_node.text.strip() if name_node is not None else "이름없음"
                    
                    size = float(item.find('excluUseAr').text.strip()) if item.find('excluUseAr') is not None else 0.0
                    pyeong = round(size * 0.3025, 1) # 평수 계산
                    
                    floor_node = item.find('floor')
                    floor = int(floor_node.text.strip()) if floor_node is not None else 0
                    month = item.find('dealMonth').text.strip() if item.find('dealMonth') is not None else "0"
                    day = item.find('dealDay').text.strip() if item.find('dealDay') is not None else "0"
                    
                    if deal_type == "매매":
                        price_str = item.find('dealAmount').text.strip().replace(',', '') if item.find('dealAmount') is not None else "0"
                        data.append({
                            '건물명': prop_name,
                            '거래금액(만원)': int(price_str),
                            '전용면적(㎡)': size,
                            '전용면적(평)': pyeong,
                            '층': floor,
                            '계약일': f"{month.zfill(2)}월 {day.zfill(2)}일"
                        })
                    else: 
                        deposit_str = item.find('deposit').text.strip().replace(',', '') if item.find('deposit') is not None else "0"
                        monthly_str = item.find('monthlyRent').text.strip().replace(',', '') if item.find('monthlyRent') is not None else "0"
                        data.append({
                            '건물명': prop_name,
                            '보증금(만원)': int(deposit_str),
                            '월세(만원)': int(monthly_str),
                            '전용면적(㎡)': size,
                            '전용면적(평)': pyeong,
                            '층': floor,
                            '계약일': f"{month.zfill(2)}월 {day.zfill(2)}일"
                        })
                except Exception:
                    continue
                    
            if data: 
                return pd.DataFrame(data)
    except Exception:
        pass
        
    return pd.DataFrame()

# 🔐 금고(Secrets)에서 보안 키 호출
try:
    API_KEY = st.secrets["api_key"]
    TG_TOKEN = st.secrets["tg_token"]
    TG_CHAT_ID = st.secrets["tg_chat_id"]
except:
    st.error("🚨 보안 금고(Secrets)가 설정되지 않았습니다.")
    st.stop()

# --- [좌측 조종실] 부동산 대출 방어선 ---
st.sidebar.header("🏠 디딤돌 대출 조종석")
house_price = st.sidebar.number_input("목표 주택 가격 (만 원)", value=55000, step=1000)
ltv_ratio = st.sidebar.slider("대출 비율 (LTV %)", 10, 80, 70)
loan_amount = int(house_price * (ltv_ratio / 100))
st.sidebar.info(f"💵 예상 대출 자금: {loan_amount:,} 만 원")

interest_rate = st.sidebar.number_input("연 이자율 (%)", value=2.5, step=0.1)
loan_years = st.sidebar.selectbox("대출 기간 (년)", [10, 15, 20, 30], index=3) 

if interest_rate > 0:
    r = (interest_rate / 100) / 12
    n = loan_years * 12
    monthly_payment = int((loan_amount * 10000) * (r * (1 + r)**n) / ((1 + r)**n - 1))
else:
    monthly_payment = int((loan_amount * 10000) / (loan_years * 12))

st.sidebar.metric("📅 예상 월 상환액", f"{monthly_payment:,} 원")
st.sidebar.markdown("---")

annual_income = st.sidebar.number_input("합산 연소득 (만 원)", value=7000, step=500)
other_loan = st.sidebar.number_input("기존 연 상환액 (만 원)", value=0, step=100)
dsr = (((monthly_payment * 12 // 10000) + other_loan) / annual_income) * 100
st.sidebar.write(f"**현재 예상 DSR:** {dsr:.1f}%")
if dsr <= 40: st.sidebar.success("✅ 대출 안전권")
else: st.sidebar.error("🚨 한도 초과 위험!")

# --- [메인 화면] 작전 제어판 ---
st.title("🏢 SD 전용 무인 감시 지휘소 (V9.4)")

tab1, tab2 = st.tabs(["🏠 국토부 실거래가 자동 수집판", "📈 통합 자산 무인 감시망"])

with tab1:
    st.subheader("🛰️ 공공데이터포털 실시간 실거래가 매핑")
    
    # 💡 [핵심] 서울/경기/인천 수도권 주요 타격 지역 코드 사전
    region_codes = {
        # --- 서울 ---
        "11000": "서울특별시",
        "11110": "서울특별시 종로구",
        "11140": "서울특별시 중구",
        "11170": "서울특별시 용산구",
        "11200": "서울특별시 성동구",
        "11215": "서울특별시 광진구",
        "11230": "서울특별시 동대문구",
        "11260": "서울특별시 중랑구",
        "11290": "서울특별시 성북구",
        "11305": "서울특별시 강북구",
        "11320": "서울특별시 도봉구",
        "11350": "서울특별시 노원구",
        "11380": "서울특별시 은평구",
        "11410": "서울특별시 서대문구",
        "11440": "서울특별시 마포구",
        "11470": "서울특별시 양천구",
        "11500": "서울특별시 강서구",
        "11530": "서울특별시 구로구",
        "11545": "서울특별시 금천구",
        "11560": "서울특별시 영등포구",
        "11590": "서울특별시 동작구",
        "11620": "서울특별시 관악구",
        "11650": "서울특별시 서초구",
        "11680": "서울특별시 강남구",
        "11710": "서울특별시 송파구",
        "11740": "서울특별시 강동구",
        # --- 경기도 ---
        "41000": "경기도",
        "41110": "경기도 수원시",
        "41111": "경기도 수원시 장안구",
        "41113": "경기도 수원시 권선구",
        "41115": "경기도 수원시 팔달구",
        "41117": "경기도 수원시 영통구",
        "41130": "경기도 성남시",
        "41131": "경기도 성남시 수정구",
        "41133": "경기도 성남시 중원구",
        "41135": "경기도 성남시 분당구",
        "41150": "경기도 의정부시",
        "41170": "경기도 안양시",
        "41171": "경기도 안양시 만안구",
        "41173": "경기도 안양시 동안구",
        "41190": "경기도 부천시",
        "41210": "경기도 광명시",
        "41220": "경기도 평택시",
        "41250": "경기도 동두천시",
        "41270": "경기도 안산시",
        "41271": "경기도 안산시 상록구",
        "41273": "경기도 안산시 단원구",
        "41280": "경기도 고양시",
        "41281": "경기도 고양시 덕양구",
        "41285": "경기도 고양시 일산동구",
        "41287": "경기도 고양시 일산서구",
        "41290": "경기도 과천시",
        "41310": "경기도 구리시",
        "41360": "경기도 남양주시",
        "41370": "경기도 오산시",
        "41390": "경기도 시흥시",
        "41410": "경기도 군포시",
        "41430": "경기도 의왕시",
        "41450": "경기도 하남시",
        "41460": "경기도 용인시",
        "41461": "경기도 용인시 처인구",
        "41463": "경기도 용인시 기흥구",
        "41465": "경기도 용인시 수지구",
        "41480": "경기도 파주시",
        "41500": "경기도 이천시",
        "41550": "경기도 안성시",
        "41570": "경기도 김포시",
        "41590": "경기도 화성시",
        "41610": "경기도 광주시",
        "41630": "경기도 양주시",
        "41650": "경기도 포천시",
        "41670": "경기도 여주시",
        "41800": "경기도 연천군",
        "41820": "경기도 가평군",
        "41830": "경기도 양평군",
        # --- 인천 ---
        "28000": "인천광역시",
        "28110": "인천광역시 중구",
        "28140": "인천광역시 동구",
        "28177": "인천광역시 미추홀구",
        "28185": "인천광역시 연수구(송도)",
        "28200": "인천광역시 남동구",
        "28237": "인천광역시 부평구",
        "28245": "인천광역시 계양구",
        "28260": "인천광역시 서구(청라)",
        "28710": "인천광역시 강화군",
        "28720": "인천광역시 옹진군",
        # --- 세종시 ---
        "36110": "세종특별자치시",
        # --- 강원도 ---
        "42000": "강원도",
        "42110": "강원도 춘천시",
        "42130": "강원도 원주시",
        "42150": "강원도 강릉시",
        "42170": "강원도 동해시",
        "42190": "강원도 태백시",
        "42210": "강원도 속초시",
        "42230": "강원도 삼척시",
        "42720": "강원도 홍천군",
        "42730": "강원도 횡성군",
        "42750": "강원도 영월군",
        "42760": "강원도 평창군",
        "42770": "강원도 정선군",
        "42780": "강원도 철원군",
        "42790": "강원도 화천군",
        "42800": "강원도 양구군",
        "42810": "강원도 인제군",
        "42820": "강원도 고성군",
        "42830": "강원도 양양군",
        # --- 충청북도 ---
        "43000": "충청북도",
        "43110": "충청북도 청주시",
        "43111": "충청북도 청주시 상당구",
        "43112": "충청북도 청주시 서원구",
        "43113": "충청북도 청주시 흥덕구",
        "43114": "충청북도 청주시 청원구",
        "43130": "충청북도 충주시",
        "43150": "충청북도 제천시",
        "43720": "충청북도 보은군",
        "43730": "충청북도 옥천군",
        "43740": "충청북도 영동군",
        "43745": "충청북도 증평군",
        "43750": "충청북도 진천군",
        "43760": "충청북도 괴산군",
        "43770": "충청북도 음성군",
        "43800": "충청북도 단양군",
        # --- 충청남도 ---
        "44000": "충청남도",
        "44130": "충청남도 천안시",
        "44131": "충청남도 천안시 동남구",
        "44133": "충청남도 천안시 서북구",
        "44150": "충청남도 공주시",
        "44180": "충청남도 보령시",
        "44200": "충청남도 아산시",
        "44210": "충청남도 서산시",
        "44230": "충청남도 논산시",
        "44250": "충청남도 계룡시",
        "44270": "충청남도 당진시",
        "44710": "충청남도 금산군",
        "44760": "충청남도 부여군",
        "44770": "충청남도 서천군",
        "44790": "충청남도 청양군",
        "44800": "충청남도 홍성군",
        "44810": "충청남도 예산군",
        "44825": "충청남도 태안군",
        # --- 대전 ---
        "30000": "대전광역시",
        "30110": "대전광역시 동구",
        "30140": "대전광역시 중구",
        "30170": "대전광역시 서구",
        "30200": "대전광역시 유성구",
        "30230": "대전광역시 대덕구",
        # --- 전라북도 ---
        "45000": "전라북도",
        "45110": "전라북도 전주시",
        "45111": "전라북도 전주시 완산구",
        "45113": "전라북도 전주시 덕진구",
        "45130": "전라북도 군산시",
        "45140": "전라북도 익산시",
        "45180": "전라북도 정읍시",
        "45190": "전라북도 남원시",
        "45210": "전라북도 김제시",
        "45710": "전라북도 완주군",
        "45720": "전라북도 진안군",
        "45730": "전라북도 무주군",
        "45740": "전라북도 장수군",
        "45750": "전라북도 임실군",
        "45770": "전라북도 순창군",
        "45790": "전라북도 고창군",
        "45800": "전라북도 부안군",
        # --- 전라남도 ---
        "46000": "전라남도",
        "46110": "전라남도 목포시",
        "46130": "전라남도 여수시",
        "46150": "전라남도 순천시",
        "46170": "전라남도 나주시",
        "46230": "전라남도 광양시",
        "46710": "전라남도 담양군",
        "46720": "전라남도 곡성군",
        "46730": "전라남도 구례군",
        "46770": "전라남도 고흥군",
        "46780": "전라남도 보성군",
        "46790": "전라남도 화순군",
        "46800": "전라남도 장흥군",
        "46810": "전라남도 강진군",
        "46820": "전라남도 해남군",
        "46830": "전라남도 영암군",
        "46840": "전라남도 무안군",
        "46860": "전라남도 함평군",
        "46870": "전라남도 영광군",
        "46880": "전라남도 장성군",
        "46890": "전라남도 완도군",
        "46900": "전라남도 진도군",
        "46910": "전라남도 신안군",
        # --- 광주 ---
        "29000": "광주광역시",
        "29110": "광주광역시 동구",
        "29140": "광주광역시 서구",
        "29155": "광주광역시 남구",
        "29170": "광주광역시 북구",
        "29200": "광주광역시 광산구",
        # --- 경상북도 ---
        "47000": "경상북도",
        "47110": "경상북도 포항시",
        "47111": "경상북도 포항시 남구",
        "47113": "경상북도 포항시 북구",
        "47130": "경상북도 경주시",
        "47150": "경상북도 김천시",
        "47170": "경상북도 안동시",
        "47190": "경상북도 구미시",
        "47210": "경상북도 영주시",
        "47230": "경상북도 영천시",
        "47250": "경상북도 상주시",
        "47280": "경상북도 문경시",
        "47290": "경상북도 경산시",
        "47720": "경상북도 군위군",
        "47730": "경상북도 의성군",
        "47750": "경상북도 청송군",
        "47760": "경상북도 영양군",
        "47770": "경상북도 영덕군",
        "47820": "경상북도 청도군",
        "47830": "경상북도 고령군",
        "47840": "경상북도 성주군",
        "47850": "경상북도 칠곡군",
        "47900": "경상북도 예천군",
        "47920": "경상북도 봉화군",
        "47930": "경상북도 울진군",
        "47940": "경상북도 울릉군",
        # --- 대구 ---
        "27000": "대구광역시",
        "27110": "대구광역시 중구",
        "27140": "대구광역시 동구",
        "27170": "대구광역시 서구",
        "27200": "대구광역시 남구",
        "27230": "대구광역시 북구",
        "27260": "대구광역시 수성구",
        "27290": "대구광역시 달서구",
        "27710": "대구광역시 달성군",
        # --- 울산 ---
        "31000": "울산광역시",
        "31110": "울산광역시 중구",
        "31140": "울산광역시 남구",
        "31170": "울산광역시 동구",
        "31200": "울산광역시 북구",
        "31710": "울산광역시 울주군",
        # --- 경상남도 ---
        "48000": "경상남도",
        "48120": "경상남도 창원시",
        "48121": "경상남도 창원시 의창구",
        "48123": "경상남도 창원시 성산구",
        "48125": "경상남도 창원시 마산합포구",
        "48127": "경상남도 창원시 마산회원구",
        "48129": "경상남도 창원시 진해구",
        "48170": "경상남도 진주시",
        "48220": "경상남도 통영시",
        "48240": "경상남도 사천시",
        "48250": "경상남도 김해시",
        "48270": "경상남도 밀양시",
        "48310": "경상남도 거제시",
        "48330": "경상남도 양산시",
        "48720": "경상남도 의령군",
        "48730": "경상남도 함안군",
        "48740": "경상남도 창녕군",
        "48820": "경상남도 고성군",
        "48840": "경상남도 남해군",
        "48850": "경상남도 하동군",
        "48860": "경상남도 산청군",
        "48870": "경상남도 함양군",
        "48880": "경상남도 거창군",
        "48890": "경상남도 합천군",
        # --- 부산 ---
        "26000": "부산광역시",
        "26110": "부산광역시 중구",
        "26140": "부산광역시 서구",
        "26170": "부산광역시 동구",
        "26200": "부산광역시 영도구",
        "26230": "부산광역시 부산진구",
        "26260": "부산광역시 동래구",
        "26290": "부산광역시 남구",
        "26320": "부산광역시 북구",
        "26350": "부산광역시 해운대구",
        "26380": "부산광역시 사하구",
        "26410": "부산광역시 금정구",
        "26440": "부산광역시 강서구",
        "26470": "부산광역시 연제구",
        "26500": "부산광역시 수영구",
        "26530": "부산광역시 사상구",
        "26710": "부산광역시 기장군",
        # --- 제주 ---
        "50000": "제주특별자치도",
        "50110": "제주특별자치도 제주시",
        "50130": "제주특별자치도 서귀포시"
    }
    
    col_req1, col_req2 = st.columns(2)
    with col_req1:
        # 사전에서 자동으로 지역명 목록을 끌어옵니다.
        target_region = st.selectbox("타격 대상 지역 선택", 
                                     options=list(region_codes.keys()), 
                                     format_func=lambda x: region_codes[x])
    with col_req2:
        target_month = st.text_input("조회 년월 (YYYYMM)", value="202604")
        
    col_req3, col_req4 = st.columns(2)
    with col_req3:
        prop_type = st.radio("수집 매물 종류", ["아파트", "빌라(연립/다세대)"], horizontal=True)
    with col_req4:
        deal_type = st.radio("거래 유형", ["매매", "전/월세"], horizontal=True)
        
    if 'real_estate_data' not in st.session_state:
        st.session_state.real_estate_data = None
        
    if st.button("🔍 국토교통부 실거래가 레이더 가동"):
        with st.spinner(f"국토부 서버에서 최신 [{prop_type} - {deal_type}] 내역을 수집하는 중..."):
            df_property = get_real_estate_api(API_KEY, target_region, target_month, prop_type, deal_type)
            
            if not df_property.empty:
                sort_col = '거래금액(만원)' if deal_type == "매매" else '보증금(만원)'
                df_property = df_property.sort_values(by=sort_col, ascending=True)
                df_property = df_property.reset_index(drop=True)
                df_property.index = df_property.index + 1 
                st.session_state.real_estate_data = df_property
            else:
                st.warning("⚠️ 해당 년월에 신고된 거래 데이터가 없거나 서버 응답이 지연되고 있습니다.")
                st.session_state.real_estate_data = None

    if st.session_state.real_estate_data is not None:
        st.success(f"📊 {target_month[:4]}년 {target_month[4:]}월 신고된 [{prop_type} - {deal_type}] 내역입니다.")
        st.dataframe(st.session_state.real_estate_data, use_container_width=True)

with tab2:
    st.subheader("🛰️ 실시간 주식 및 가상자산 감시판")
    
    dw_price = get_naver_price("047040")
    space_price = get_naver_price("0183J0")
    eth_price = get_upbit_price("KRW-ETH")
    
    colA, colB, colC = st.columns(3)
    with colA: st.metric("🏢 대우건설", f"{dw_price:,} 원")
    with colB: st.metric("🚀 TIGER 미국우주테크 ETF", f"{space_price:,} 원")
    with colC: st.metric("💎 이더리움 (ETH)", f"{eth_price:,} 원")
    
    st.markdown("---")
    st.subheader("🚨 공방(攻防)형 자동 경보 시스템 설정")
    
    col_tgt1, col_tgt2, col_tgt3 = st.columns(3)
    with col_tgt1:
        st.markdown("#### 🏢 대우건설")
        dw_buy_target = st.number_input("매수 단가 (이하)", value=28000, step=50, key="dw_buy")
        dw_sell_target = st.number_input("매도 단가 (이상)", value=30000, step=50, key="dw_sell")
    with col_tgt2:
        st.markdown("#### 🚀 TIGER 미국우주테크 ETF")
        space_buy_target = st.number_input("매수 단가 (이하)", value=14000, step=50, key="sp_buy")
        space_sell_target = st.number_input("매도 단가 (이상)", value=16000, step=50, key="sp_sell")
    with col_tgt3:
        st.markdown("#### 💎 이더리움(ETH)")
        eth_buy_target = st.number_input("매수 단가 (이하)", value=3100000, step=100000, key="eth_buy")
        eth_sell_target = st.number_input("매도 단가 (이상)", value=3500000, step=100000, key="eth_sell")

    st.markdown("---")
    if st.checkbox("🔄 24시간 무인 자동 감시 작동 - 1분마다"):
        st_autorefresh(interval=60000, limit=None, key="auto_refresh")
        
        kst = datetime.timezone(datetime.timedelta(hours=9))
        now = datetime.datetime.now(kst)
        is_weekday = True
        start_time = datetime.time(0, 1)
        end_time = datetime.time(23, 59)
        is_market_hours = start_time <= now.time() <= end_time
        
        if is_weekday and is_market_hours:
            st.info(f"🛰️ 현재 시각 {now.strftime('%H:%M:%S')} : 24시간 무인 감시망 가동 중 (1분 주기)")
            
            if dw_price > 0 and dw_price <= dw_buy_target and not st.session_state.dw_buy_fired:
                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": f"📉 [대우건설 매수 경보] 목표가 진입: {dw_price:,}원"})
                st.session_state.dw_buy_fired = True
            if dw_price > dw_buy_target: st.session_state.dw_buy_fired = False

            if dw_price > 0 and dw_price >= dw_sell_target and not st.session_state.dw_sell_fired:
                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": f"📈 [대우건설 매도 경보] 목표가 돌파: {dw_price:,}원"})
                st.session_state.dw_sell_fired = True
            if dw_price < dw_sell_target: st.session_state.dw_sell_fired = False
            
            if space_price > 0 and space_price <= space_buy_target and not st.session_state.space_buy_fired:
                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": f"📉 [우주테크 ETF 매수 경보] 목표가 진입: {space_price:,}원"})
                st.session_state.space_buy_fired = True
            if space_price > space_buy_target: st.session_state.space_buy_fired = False

            if space_price > 0 and space_price >= space_sell_target and not st.session_state.space_sell_fired:
                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": f"📈 [우주테크 ETF 매도 경보] 목표가 돌파: {space_price:,}원"})
                st.session_state.space_sell_fired = True
            if space_price < space_sell_target: st.session_state.space_sell_fired = False
            
            if eth_price > 0 and eth_price <= eth_buy_target and not st.session_state.eth_buy_fired:
                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": f"💎📉 [이더리움 매수 경보] 목표가 진입: {eth_price:,}원"})
                st.session_state.eth_buy_fired = True
            if eth_price > eth_buy_target: st.session_state.eth_buy_fired = False

            if eth_price > 0 and eth_price >= eth_sell_target and not st.session_state.eth_sell_fired:
                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": f"💎📈 [이더리움 매도 경보] 목표가 돌파: {eth_price:,}원"})
                st.session_state.eth_sell_fired = True
            if eth_price < eth_sell_target: st.session_state.eth_sell_fired = False

        else:
            st.warning("💤 시스템 재정비 시간입니다.")