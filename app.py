import urllib.parse
import streamlit as st
import pandas as pd
import requests
import re
import datetime
import xml.etree.ElementTree as ET
from streamlit_autorefresh import st_autorefresh

st.set_page_config(layout="wide", page_title="통합 지휘소 V12.0")

# --- 💡 [핵심] 통합 자산 라인업 사전 정의 (주식 7종 / 코인 3종) ---
ASSETS = [
    # 주식/ETF 라인업
    {"name": "TIGER 미국S&P500", "code": "360750", "type": "stock", "key": "sp500", "p_step": 100.0, "q_step": 1.0},
    {"name": "KODEX 나스닥100", "code": "133690", "type": "stock", "key": "ndx", "p_step": 100.0, "q_step": 1.0},
    {"name": "TIGER 미국배당다우존스", "code": "458730", "type": "stock", "key": "dow", "p_step": 50.0, "q_step": 1.0},
    {"name": "TIGER 미국우주테크", "code": "0183J0", "type": "stock", "key": "space", "p_step": 50.0, "q_step": 1.0},
    {"name": "삼성전자", "code": "005930", "type": "stock", "key": "ss", "p_step": 100.0, "q_step": 1.0},
    {"name": "대우건설", "code": "047040", "type": "stock", "key": "dw", "p_step": 10.0, "q_step": 1.0},
    {"name": "SK네트웍스", "code": "001740", "type": "stock", "key": "sk", "p_step": 10.0, "q_step": 1.0},
    # 가상자산 라인업
    {"name": "이더리움 (ETH)", "code": "KRW-ETH", "type": "coin", "key": "eth", "p_step": 10000.0, "q_step": 0.01},
    {"name": "제로지 (0G)", "code": "KRW-0G", "type": "coin", "key": "zg", "p_step": 10.0, "q_step": 10.0},
    {"name": "썬더코어 (TT)", "code": "KRW-TT", "type": "coin", "key": "tt", "p_step": 0.1, "q_step": 100.0},
]

# --- [상태 관리 시스템: 경보 발송 여부 기록용] ---
for a in ASSETS:
    if f"{a['key']}_buy_fired" not in st.session_state: st.session_state[f"{a['key']}_buy_fired"] = False
    if f"{a['key']}_sell_fired" not in st.session_state: st.session_state[f"{a['key']}_sell_fired"] = False

if 'alert_logs' not in st.session_state: st.session_state.alert_logs = []

# 🛰️ 주가 수집 엔진 (소수점 지원)
def get_naver_price(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        match = re.search(r'<p class="no_today">.*?<span class="blind">([\d,\.]+)</span>', res.text, re.DOTALL)
        if match: return float(match.group(1).replace(',', ''))
        return 0.0
    except: return 0.0

# 🛰️ 가상자산 수집 엔진 (소수점 지원)
def get_upbit_price(ticker="KRW-ETH"):
    try:
        url = f"https://api.upbit.com/v1/ticker?markets={ticker}"
        headers = {"accept": "application/json"}
        res = requests.get(url, headers=headers)
        data = res.json()
        return float(data[0]['trade_price'])
    except: return 0.0

# 🏠 국토교통부 실거래가 API 저격 엔진
def get_real_estate_api(service_key, lawd_cd, deal_ymd, region_name, prop_type="아파트", deal_type="매매"):
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
                    pyeong = round(size * 0.3025, 1)
                    
                    floor_node = item.find('floor')
                    floor = int(floor_node.text.strip()) if floor_node is not None else 0
                    month = item.find('dealMonth').text.strip() if item.find('dealMonth') is not None else "0"
                    day = item.find('dealDay').text.strip() if item.find('dealDay') is not None else "0"
                    
                    umd_node = item.find('umdNm')
                    umd_name = umd_node.text.strip() if umd_node is not None else ""
                    jibun_node = item.find('jibun')
                    jibun_name = jibun_node.text.strip() if jibun_node is not None else ""
                    
                    display_address = f"{umd_name} {jibun_name}".strip()
                    
                    search_query = f"{region_name} {umd_name} {jibun_name} {prop_name}"
                    encoded_query = urllib.parse.quote(search_query)
                    map_url = f"https://map.naver.com/v5/search/{encoded_query}"
                    
                    if deal_type == "매매":
                        price_str = item.find('dealAmount').text.strip().replace(',', '') if item.find('dealAmount') is not None else "0"
                        price_int = int(price_str)
                        pyeong_price = int(price_int / pyeong) if pyeong > 0 else 0
                        
                        data.append({
                            '건물명': prop_name,
                            '주소': display_address,
                            '🗺️ 지도 보기': map_url,
                            '거래금액(만원)': price_int,
                            '평당가(만원)': pyeong_price,
                            '전용면적(평)': pyeong,
                            '전용면적(㎡)': size,
                            '층': floor,
                            '계약일': f"{month.zfill(2)}월 {day.zfill(2)}일"
                        })
                    else: 
                        deposit_str = item.find('deposit').text.strip().replace(',', '') if item.find('deposit') is not None else "0"
                        monthly_str = item.find('monthlyRent').text.strip().replace(',', '') if item.find('monthlyRent') is not None else "0"
                        deposit_int = int(deposit_str)
                        monthly_int = int(monthly_str)
                        pyeong_deposit = int(deposit_int / pyeong) if pyeong > 0 else 0
                        
                        data.append({
                            '건물명': prop_name,
                            '주소': display_address,
                            '🗺️ 지도 보기': map_url,
                            '보증금(만원)': deposit_int,
                            '월세(만원)': monthly_int,
                            '보증금 평당가(만원)': pyeong_deposit,
                            '전용면적(평)': pyeong,
                            '전용면적(㎡)': size,
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

# --- [UI 랜더링 전용 함수: 깔끔한 그리드 생성] ---
def render_portfolio_row(asset_info, current_price):
    col1, col2, col3, col4, col5 = st.columns([2, 1.5, 1.5, 1.5, 1.5])
    key_prefix = asset_info["key"]
    p_step = asset_info["p_step"]
    q_step = asset_info["q_step"]
    
    with col2: avg_p = st.number_input("평단가", min_value=0.0, step=p_step, key=f"{key_prefix}_avg", label_visibility="collapsed")
    with col3: qty = st.number_input("수량", min_value=0.0, step=q_step, key=f"{key_prefix}_qty", label_visibility="collapsed")
    with col4: buy_t = st.number_input("매수가", min_value=0.0, step=p_step, key=f"{key_prefix}_buy", label_visibility="collapsed")
    with col5: sell_t = st.number_input("매도가", min_value=0.0, step=p_step, key=f"{key_prefix}_sell", label_visibility="collapsed")

    with col1:
        if avg_p > 0 and qty > 0:
            eval_val = current_price * qty
            ret = (current_price - avg_p) / avg_p * 100
            color = "#ef4444" if ret > 0 else "#3b82f6" if ret < 0 else "gray"
            sign = "+" if ret > 0 else ""
            st.markdown(f"**{asset_info['name']}** <span style='font-size:13px; color:gray'>({current_price:,.2f}원)</span><br><span style='font-size:15px'>평가액: **{eval_val:,.0f}원** (<span style='color:{color}; font-weight:bold;'>{sign}{ret:.2f}%</span>)</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"**{asset_info['name']}** <span style='font-size:13px; color:gray'>({current_price:,.2f}원)</span><br><span style='color:gray;font-size:13px;'>포트폴리오 정보 미입력</span>", unsafe_allow_html=True)


# =======================================================
# 🌐 데이터 사전 수집 (실시간 가격 일괄 스캔)
# =======================================================
current_prices = {}
for a in ASSETS:
    if a["type"] == "stock":
        current_prices[a["key"]] = get_naver_price(a["code"])
    else:
        current_prices[a["key"]] = get_upbit_price(a["code"])

# 💰 총 포트폴리오 자산 계산
total_invest = 0.0
total_eval = 0.0
for a in ASSETS:
    avg_p = st.session_state.get(f"{a['key']}_avg", 0.0)
    qty = st.session_state.get(f"{a['key']}_qty", 0.0)
    if avg_p > 0 and qty > 0:
        total_invest += (avg_p * qty)
        total_eval += (current_prices[a["key"]] * qty)


# --- [좌측 조종실] ---
st.sidebar.header("🏠 디딤돌 대출 방어선")
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

# --- [메인 화면] ---
st.title("🏢 SD 전용 무인 감시 지휘소 (V12.0)")

# 💡 실시간 총 자산 전광판
st.markdown("### 💰 총 포트폴리오 평가액 (주식 + 코인)")
if total_invest > 0:
    tot_ret = (total_eval - total_invest) / total_invest * 100
    color = "normal" if tot_ret >= 0 else "inverse"
    st.metric("실시간 합산 자산", f"{total_eval:,.0f} 원", f"{total_eval - total_invest:,.0f} 원 ({tot_ret:.2f}%)", delta_color=color)
else:
    st.info("💡 각 탭에서 보유 종목의 평단가와 수량을 입력하시면 총 자산이 자동 계산됩니다.")
st.markdown("<br>", unsafe_allow_html=True)

# --- 탭 구성 분리 ---
tab1, tab2, tab3 = st.tabs(["🏠 부동산 실거래가 수집망", "📈 주식/ETF 자산 포트폴리오", "💎 가상자산 포트폴리오"])

with tab1:
    st.subheader("🛰️ 공공데이터포털 실시간 실거래가 매핑")
    # (오리지널 전국구 코드 생략 없이 100% 포함 - 생략 방지를 위해 간략화 없이 전부 기입)
    region_codes = {
        "11110": "서울특별시 종로구", "11140": "서울특별시 중구", "11170": "서울특별시 용산구", "11200": "서울특별시 성동구", "11215": "서울특별시 광진구", "11230": "서울특별시 동대문구", "11260": "서울특별시 중랑구", "11290": "서울특별시 성북구", "11305": "서울특별시 강북구", "11320": "서울특별시 도봉구", "11350": "서울특별시 노원구", "11380": "서울특별시 은평구", "11410": "서울특별시 서대문구", "11440": "서울특별시 마포구", "11470": "서울특별시 양천구", "11500": "서울특별시 강서구", "11530": "서울특별시 구로구", "11545": "서울특별시 금천구", "11560": "서울특별시 영등포구", "11590": "서울특별시 동작구", "11620": "서울특별시 관악구", "11650": "서울특별시 서초구", "11680": "서울특별시 강남구", "11710": "서울특별시 송파구", "11740": "서울특별시 강동구",
        "41110": "경기도 수원시", "41111": "경기도 수원시 장안구", "41113": "경기도 수원시 권선구", "41115": "경기도 수원시 팔달구", "41117": "경기도 수원시 영통구", "41130": "경기도 성남시", "41131": "경기도 성남시 수정구", "41133": "경기도 성남시 중원구", "41135": "경기도 성남시 분당구", "41150": "경기도 의정부시", "41170": "경기도 안양시", "41171": "경기도 안양시 만안구", "41173": "경기도 안양시 동안구", "41190": "경기도 부천시", "41210": "경기도 광명시", "41220": "경기도 평택시", "41250": "경기도 동두천시", "41270": "경기도 안산시", "41271": "경기도 안산시 상록구", "41273": "경기도 안산시 단원구", "41280": "경기도 고양시", "41281": "경기도 고양시 덕양구", "41285": "경기도 고양시 일산동구", "41287": "경기도 고양시 일산서구", "41290": "경기도 과천시", "41310": "경기도 구리시", "41360": "경기도 남양주시", "41370": "경기도 오산시", "41390": "경기도 시흥시", "41410": "경기도 군포시", "41430": "경기도 의왕시", "41450": "경기도 하남시", "41460": "경기도 용인시", "41461": "경기도 용인시 처인구", "41463": "경기도 용인시 기흥구", "41465": "경기도 용인시 수지구", "41480": "경기도 파주시", "41500": "경기도 이천시", "41550": "경기도 안성시", "41570": "경기도 김포시", "41590": "경기도 화성시", "41610": "경기도 광주시", "41630": "경기도 양주시", "41650": "경기도 포천시", "41670": "경기도 여주시", "41800": "경기도 연천군", "41820": "경기도 가평군", "41830": "경기도 양평군",
        "28110": "인천광역시 중구", "28140": "인천광역시 동구", "28177": "인천광역시 미추홀구", "28185": "인천광역시 연수구(송도)", "28200": "인천광역시 남동구", "28237": "인천광역시 부평구", "28245": "인천광역시 계양구", "28260": "인천광역시 서구(청라)", "28710": "인천광역시 강화군", "28720": "인천광역시 옹진군", "36110": "세종특별자치시",
        "42110": "강원도 춘천시", "42130": "강원도 원주시", "42150": "강원도 강릉시", "42170": "강원도 동해시", "42190": "강원도 태백시", "42210": "강원도 속초시", "42230": "강원도 삼척시", "42720": "강원도 홍천군", "42730": "강원도 횡성군", "42750": "강원도 영월군", "42760": "강원도 평창군", "42770": "강원도 정선군", "42780": "강원도 철원군", "42790": "강원도 화천군", "42800": "강원도 양구군", "42810": "강원도 인제군", "42820": "강원도 고성군", "42830": "강원도 양양군",
        "43110": "충청북도 청주시", "43111": "충청북도 청주시 상당구", "43112": "충청북도 청주시 서원구", "43113": "충청북도 청주시 흥덕구", "43114": "충청북도 청주시 청원구", "43130": "충청북도 충주시", "43150": "충청북도 제천시", "43720": "충청북도 보은군", "43730": "충청북도 옥천군", "43740": "충청북도 영동군", "43745": "충청북도 증평군", "43750": "충청북도 진천군", "43760": "충청북도 괴산군", "43770": "충청북도 음성군", "43800": "충청북도 단양군",
        "44130": "충청남도 천안시", "44131": "충청남도 천안시 동남구", "44133": "충청남도 천안시 서북구", "44150": "충청남도 공주시", "44180": "충청남도 보령시", "44200": "충청남도 아산시", "44210": "충청남도 서산시", "44230": "충청남도 논산시", "44250": "충청남도 계룡시", "44270": "충청남도 당진시", "44710": "충청남도 금산군", "44760": "충청남도 부여군", "44770": "충청남도 서천군", "44790": "충청남도 청양군", "44800": "충청남도 홍성군", "44810": "충청남도 예산군", "44825": "충청남도 태안군",
        "30110": "대전광역시 동구", "30140": "대전광역시 중구", "30170": "대전광역시 서구", "30200": "대전광역시 유성구", "30230": "대전광역시 대덕구",
        "45110": "전라북도 전주시", "45111": "전라북도 전주시 완산구", "45113": "전라북도 전주시 덕진구", "45130": "전라북도 군산시", "45140": "전라북도 익산시", "45180": "전라북도 정읍시", "45190": "전라북도 남원시", "45210": "전라북도 김제시", "45710": "전라북도 완주군", "45720": "전라북도 진안군", "45730": "전라북도 무주군", "45740": "전라북도 장수군", "45750": "전라북도 임실군", "45770": "전라북도 순창군", "45790": "전라북도 고창군", "45800": "전라북도 부안군",
        "46110": "전라남도 목포시", "46130": "전라남도 여수시", "46150": "전라남도 순천시", "46170": "전라남도 나주시", "46230": "전라남도 광양시", "46710": "전라남도 담양군", "46720": "전라남도 곡성군", "46730": "전라남도 구례군", "46770": "전라남도 고흥군", "46780": "전라남도 보성군", "46790": "전라남도 화순군", "46800": "전라남도 장흥군", "46810": "전라남도 강진군", "46820": "전라남도 해남군", "46830": "전라남도 영암군", "46840": "전라남도 무안군", "46860": "전라남도 함평군", "46870": "전라남도 영광군", "46880": "전라남도 장성군", "46890": "전라남도 완도군", "46900": "전라남도 진도군", "46910": "전라남도 신안군",
        "29110": "광주광역시 동구", "29140": "광주광역시 서구", "29155": "광주광역시 남구", "29170": "광주광역시 북구", "29200": "광주광역시 광산구",
        "47110": "경상북도 포항시", "47111": "경상북도 포항시 남구", "47113": "경상북도 포항시 북구", "47130": "경상북도 경주시", "47150": "경상북도 김천시", "47170": "경상북도 안동시", "47190": "경상북도 구미시", "47210": "경상북도 영주시", "47230": "경상북도 영천시", "47250": "경상북도 상주시", "47280": "경상북도 문경시", "47290": "경상북도 경산시", "47720": "경상북도 군위군", "47730": "경상북도 의성군", "47750": "경상북도 청송군", "47760": "경상북도 영양군", "47770": "경상북도 영덕군", "47820": "경상북도 청도군", "47830": "경상북도 고령군", "47840": "경상북도 성주군", "47850": "경상북도 칠곡군", "47900": "경상북도 예천군", "47920": "경상북도 봉화군", "47930": "경상북도 울진군", "47940": "경상북도 울릉군",
        "27110": "대구광역시 중구", "27140": "대구광역시 동구", "27170": "대구광역시 서구", "27200": "대구광역시 남구", "27230": "대구광역시 북구", "27260": "대구광역시 수성구", "27290": "대구광역시 달서구", "27710": "대구광역시 달성군",
        "31110": "울산광역시 중구", "31140": "울산광역시 남구", "31170": "울산광역시 동구", "31200": "울산광역시 북구", "31710": "울산광역시 울주군",
        "48120": "경상남도 창원시", "48121": "경상남도 창원시 의창구", "48123": "경상남도 창원시 성산구", "48125": "경상남도 창원시 마산합포구", "48127": "경상남도 창원시 마산회원구", "48129": "경상남도 창원시 진해구", "48170": "경상남도 진주시", "48220": "경상남도 통영시", "48240": "경상남도 사천시", "48250": "경상남도 김해시", "48270": "경상남도 밀양시", "48310": "경상남도 거제시", "48330": "경상남도 양산시", "48720": "경상남도 의령군", "48730": "경상남도 함안군", "48740": "경상남도 창녕군", "48820": "경상남도 고성군", "48840": "경상남도 남해군", "48850": "경상남도 하동군", "48860": "경상남도 산청군", "48870": "경상남도 함양군", "48880": "경상남도 거창군", "48890": "경상남도 합천군",
        "26110": "부산광역시 중구", "26140": "부산광역시 서구", "26170": "부산광역시 동구", "26200": "부산광역시 영도구", "26230": "부산광역시 부산진구", "26260": "부산광역시 동래구", "26290": "부산광역시 남구", "26320": "부산광역시 북구", "26350": "부산광역시 해운대구", "26380": "부산광역시 사하구", "26410": "부산광역시 금정구", "26440": "부산광역시 강서구", "26470": "부산광역시 연제구", "26500": "부산광역시 수영구", "26530": "부산광역시 사상구", "26710": "부산광역시 기장군",
        "50110": "제주특별자치도 제주시", "50130": "제주특별자치도 서귀포시"
    }
    
    col_req1, col_req2 = st.columns(2)
    with col_req1:
        target_region = st.selectbox("타격 대상 지역 선택", options=list(region_codes.keys()), format_func=lambda x: region_codes[x])
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
            df_property = get_real_estate_api(API_KEY, target_region, target_month, region_codes[target_region], prop_type, deal_type)
            
            if not df_property.empty:
                sort_col = '평당가(만원)' if deal_type == "매매" else '보증금 평당가(만원)'
                df_property = df_property.sort_values(by=sort_col, ascending=True)
                df_property = df_property.reset_index(drop=True)
                df_property.index = df_property.index + 1 
                st.session_state.real_estate_data = df_property
            else:
                st.warning("⚠️ 해당 년월에 신고된 거래 데이터가 없거나 서버 응답이 지연되고 있습니다.")
                st.session_state.real_estate_data = None

    if st.session_state.real_estate_data is not None:
        df_display = st.session_state.real_estate_data.copy()
        available_dongs = sorted(list(df_display['주소'].str.split().str[0].unique()))
        selected_dong = st.selectbox("🎯 정밀 타격 '동' 선택", ["전체 보기"] + available_dongs)
        
        if selected_dong != "전체 보기":
            df_display = df_display[df_display['주소'].str.startswith(selected_dong)]
            df_display = df_display.reset_index(drop=True)
            df_display.index = df_display.index + 1

        st.success(f"📊 {target_month[:4]}년 {target_month[4:]}월 신고된 [{prop_type} - {deal_type} ({selected_dong})] 내역입니다.")
        st.dataframe(df_display, use_container_width=True, column_config={"🗺️ 지도 보기": st.column_config.LinkColumn("🗺️ 지도 보기", display_text="지도 보기")})

# --- 주식/ETF 탭 ---
with tab2:
    st.markdown("#### 🏢 주식 및 ETF 포트폴리오 관리판")
    
    # 헤더 렌더링
    col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([2, 1.5, 1.5, 1.5, 1.5])
    col_h1.markdown("**📈 종목명 (현재가) 및 평가액**")
    col_h2.markdown("**💵 내 평단가**")
    col_h3.markdown("**📦 보유수량**")
    col_h4.markdown("**👇 매수 알림가**")
    col_h5.markdown("**👆 매도 알림가**")
    st.markdown("<hr style='margin:0px; padding:0px'>", unsafe_allow_html=True)
    
    # 주식 종목만 필터링하여 출력
    for a in ASSETS:
        if a["type"] == "stock":
            render_portfolio_row(a, current_prices[a["key"]])
            st.markdown("<hr style='margin:5px 0px; border-color:#e2e8f0'>", unsafe_allow_html=True)

# --- 가상자산 탭 ---
with tab3:
    st.markdown("#### 💎 가상자산 포트폴리오 관리판")
    
    # 헤더 렌더링
    col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([2, 1.5, 1.5, 1.5, 1.5])
    col_h1.markdown("**💎 종목명 (현재가) 및 평가액**")
    col_h2.markdown("**💵 내 평단가**")
    col_h3.markdown("**📦 보유수량**")
    col_h4.markdown("**👇 매수 알림가**")
    col_h5.markdown("**👆 매도 알림가**")
    st.markdown("<hr style='margin:0px; padding:0px'>", unsafe_allow_html=True)
    
    # 코인 종목만 필터링하여 출력
    for a in ASSETS:
        if a["type"] == "coin":
            render_portfolio_row(a, current_prices[a["key"]])
            st.markdown("<hr style='margin:5px 0px; border-color:#e2e8f0'>", unsafe_allow_html=True)

# --- [통합 알림 시스템 및 블랙박스] ---
st.markdown("---")

kst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
current_run_time = kst_now.strftime('%Y-%m-%d %H:%M:%S')

col_opt1, col_opt2 = st.columns([1, 3])
with col_opt1:
    is_auto = st.checkbox("🔄 24시간 감시망 켜기 (1분)")

if is_auto:
    st_autorefresh(interval=60000, limit=None, key="auto_refresh")
    log_time = current_run_time
    st.info(f"🛰️ 24시간 무인 감시망 가동 중 (스캔 시각: {kst_now.strftime('%H:%M:%S')})")
    
    # 💡 10개 종목 일괄 알림 스캔 루프
    for a in ASSETS:
        price = current_prices[a["key"]]
        buy_target = st.session_state.get(f"{a['key']}_buy", 0.0)
        sell_target = st.session_state.get(f"{a['key']}_sell", 0.0)
        
        icon = "📈" if a["type"] == "stock" else "💎"
        
        # 1. 매수 알림 확인
        if price > 0 and buy_target > 0 and price <= buy_target and not st.session_state[f"{a['key']}_buy_fired"]:
            msg = f"{icon}📉 [{a['name']} 매수 경보] 목표가 진입: {price:,.2f}원"
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": msg})
            st.session_state[f"{a['key']}_buy_fired"] = True
            st.session_state.alert_logs.insert(0, f"[{log_time}] {msg}")
        elif price > buy_target:
            st.session_state[f"{a['key']}_buy_fired"] = False

        # 2. 매도 알림 확인
        if price > 0 and sell_target > 0 and price >= sell_target and not st.session_state[f"{a['key']}_sell_fired"]:
            msg = f"{icon}📈 [{a['name']} 매도 경보] 목표가 돌파: {price:,.2f}원"
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": msg})
            st.session_state[f"{a['key']}_sell_fired"] = True
            st.session_state.alert_logs.insert(0, f"[{log_time}] {msg}")
        elif price < sell_target:
            st.session_state[f"{a['key']}_sell_fired"] = False

st.subheader("📝 실시간 경보 발송 블랙박스")
log_title = f"최근 텔레그램 발송 내역 (하트비트 마지막 스캔: {current_run_time})"

if not st.session_state.alert_logs:
    st.text_area(log_title, value="대기 중... (아직 발송된 경보가 없습니다)", height=150, disabled=True)
else:
    st.text_area(log_title, value="\n".join(st.session_state.alert_logs), height=150, disabled=True)