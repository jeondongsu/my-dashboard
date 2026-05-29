import urllib.parse
import streamlit as st
import pandas as pd
import requests
import re
import datetime
import time
import xml.etree.ElementTree as ET
from streamlit_autorefresh import st_autorefresh

st.set_page_config(layout="wide", page_title="통합 지휘소 V9.1 (API 복구)")

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

# 🏠 국토교통부 실거래가 API 저격 엔진 (V9.1 진짜 주소로 복구 완료)
# 🏠 국토교통부 실거래가 API 저격 엔진 (수정본)
def get_real_estate_api(service_key, lawd_cd, deal_ymd):
    # 최신 신형 서버 주소
    url = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
    
    # 💡 핵심: 인증키가 이중 인코딩 되지 않도록 URL을 직접 조립합니다.
    full_url = f"{url}?serviceKey={service_key}&LAWD_CD={lawd_cd}&DEAL_YMD={deal_ymd}&numOfRows=100"
    
    try:
        res = requests.get(full_url, timeout=10) # 타임아웃을 10초로 넉넉하게
        
        if res.status_code == 200:
            root = ET.fromstring(res.text)
            
            # API 에러 메시지가 반환되었는지 확인용 (터미널 출력)
            result_code = root.find('.//resultCode')
            if result_code is not None and result_code.text != "00":
                print(f"API 오류 발생: {root.find('.//resultMsg').text}")
                return pd.DataFrame()

            items = root.findall('.//item')
            data = []
            for item in items:
                # 데이터가 없는 항목이 있을 수 있으니 안전하게 추출
                try:
                    apt_name = item.find('아파트').text.strip() if item.find('아파트') is not None else "이름없음"
                    price_str = item.find('거래금액').text.strip().replace(',', '') if item.find('거래금액') is not None else "0"
                    size = float(item.find('전용면적').text.strip()) if item.find('전용면적') is not None else 0.0
                    floor = int(item.find('층').text.strip()) if item.find('층') is not None else 0
                    month = item.find('월').text.strip() if item.find('월') is not None else ""
                    day = item.find('일').text.strip() if item.find('일') is not None else ""
                    
                    data.append({
                        '아파트명': apt_name,
                        '거래금액(만원)': int(price_str),
                        '전용면적(㎡)': size,
                        '층': floor,
                        '거래일': f"{month}월 {day}일"
                    })
                except Exception as e:
                    print(f"데이터 파싱 오류: {e}") 
                    continue # 한 항목에서 에러나도 다음 아파트는 계속 수집
                    
            if data: 
                return pd.DataFrame(data)
    except Exception as e:
        print(f"서버 접속 오류: {e}")
        
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
st.title("🏢 SD 전용 무인 감시 지휘소 (V9.1)")

tab1, tab2 = st.tabs(["🏠 국토부 실거래가 자동 수집판", "📈 통합 자산 무인 감시망"])

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
                st.warning("⚠️해당 년월에 신고된 거래 데이터가 없거나 인증키 오류입니다.")

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
        # 1분(60,000ms)마다 Streamlit이 안전하게 화면을 새로고침합니다.
        st_autorefresh(interval=60000, limit=None, key="auto_refresh")
        
        now = datetime.datetime.now()
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
        
        #time.sleep(60)
        #st.rerun()