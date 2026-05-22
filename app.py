import streamlit as st
import pandas as pd
import requests
import re
import datetime
import time
import xml.etree.ElementTree as ET

st.set_page_config(layout="wide", page_title="통합 지휘소 V8 (보안금고)")

# --- [상태 관리 시스템] ---
if 'dw_buy_fired' not in st.session_state: st.session_state.dw_buy_fired = False
if 'dw_sell_fired' not in st.session_state: st.session_state.dw_sell_fired = False
if 'space_buy_fired' not in st.session_state: st.session_state.space_buy_fired = False
if 'space_sell_fired' not in st.session_state: st.session_state.space_sell_fired = False

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

# 🏠 국토교통부 실거래가 API 저격 엔진
def get_real_estate_api(service_key, lawd_cd, deal_ymd):
    url = "http://openapi.molit.go.kr:8081/OpenAPI_ToolInstallPackage/service/rest/RTMSOBJSvc/getRTMSObjSeachOrines"
    params = {'serviceKey': service_key, 'LAWD_CD': lawd_cd, 'DEAL_YMD': deal_ymd}
    
    try:
        res = requests.get(url, params=params)
        if res.status_code == 200:
            root = ET.fromstring(res.text)
            items = root.findall('.//item')
            data = []
            for item in items:
                try:
                    data.append({
                        '아파트명': item.find('아파트').text.strip(),
                        '거래금액(만원)': int(item.find('거래금액').text.strip().replace(',', '')),
                        '전용면적(㎡)': float(item.find('전용면적').text.strip()),
                        '층': int(item.find('층').text.strip()),
                        '거래일': f"{item.find('월').text.strip()}월 {item.find('일').text.strip()}일"
                    })
                except: continue
            return pd.DataFrame(data)
    except: pass
    return pd.DataFrame()

# 금고(Secrets)에서 보안 키 호출
try:
    API_KEY = st.secrets["api_key"]
    TG_TOKEN = st.secrets["tg_token"]
    TG_CHAT_ID = st.secrets["tg_chat_id"]
except:
    st.error("🚨 보안 금고(Secrets)가 설정되지 않았습니다. 클라우드 세팅을 확인하십시오.")
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
st.title("🏢 전동수 회장님 전용 무인 감시 지휘소 (V8 보안금고)")

tab1, tab2 = st.tabs(["🏠 국토부 실거래가 자동 수집판", "📈 공방형 주가 무인 감시망"])

with tab1:
    st.subheader("🛰️ 공공데이터포털 실시간 실거래가 매핑")
    
    col_req1, col_req2 = st.columns(2)
    with col_req1:
        target_region = st.selectbox("타격 대상 지역 선택", 
                                     options=["41171", "41210", "11500"], 
                                     format_func=lambda x: "안양시 만안구" if x=="41171" else "광명시" if x=="41210" else "서울 강서구")
    with col_req2:
        target_month = st.text_input("조회 년월 (YYYYMM)", value=datetime.datetime.now().strftime("%Y%m"))
        
    if st.button("🔍 국토교통부 실거래가 레이더 가동"):
        with st.spinner("국토부 서버에서 최신 실거래 내역을 격추하는 중..."):
            df_property = get_real_estate_api(API_KEY, target_region, target_month)
            if not df_property.empty:
                st.success(f"📊 {target_month[:4]}년 {target_month[4:]}월 실제 신고 완료된 매매 내역입니다.")
                st.dataframe(df_property, use_container_width=True)
            else:
                st.warning("⚠️해당 년월에 신고된 거래 데이터가 없거나 인증키 동기화 대기 중입니다.")

with tab2:
    st.subheader("🛰️ 실시간 주가 감시 및 목표가 설정")
    col1, col2 = st.columns(2)
    with col1: dw_code = st.text_input("대우건설 종목코드", value="047040")
    with col2: space_code = st.text_input("우주테크 ETF 종목코드", value="0183J0")
    
    dw_price = get_naver_price(dw_code)
    space_price = get_naver_price(space_code)
    
    st.metric("📊 현재 시장가", f"대우: {dw_price:,}원 / 우주테크: {space_price:,}원")
    
    st.markdown("---")
    st.subheader("🚨 매수(하락) 및 매도(상승) 경보 설정")
    buy_target = st.number_input("📉 매수 목표가 (이하)", value=3500)
    sell_target = st.number_input("📈 매도 목표가 (이상)", value=4500)

    if st.checkbox("🔄 무인 자동 감시 엔진 점화"):
        if dw_price <= buy_target and not st.session_state.buy_fired:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": f"📉 [매수 알림] 대우건설 목표가 도래: {dw_price:,}원"})
            st.session_state.buy_fired = True
        elif dw_price > buy_target: st.session_state.buy_fired = False

        if dw_price >= sell_target and not st.session_state.sell_fired:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": f"📈 [매도 알림] 대우건설 목표가 도래: {dw_price:,}원"})
            st.session_state.sell_fired = True
        elif dw_price < sell_target: st.session_state.sell_fired = False
        
        time.sleep(60)
        st.rerun()