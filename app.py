import urllib.parse
import streamlit as st
import pandas as pd
import requests
import re
import datetime
import xml.etree.ElementTree as ET
from streamlit_autorefresh import st_autorefresh

st.set_page_config(layout="wide", page_title="통합 지휘소 V9.3")

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

# 🏠 국토교통부 실거래가 API 저격 엔진 (평수 계산 추가 완료)
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
                    # 💡 [핵심 추가] 평수 계산 (소수점 첫째 자리까지 반올림)
                    pyeong = round(size * 0.3025, 1)
                    
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
                            '전용면적(평)': pyeong,  # 💡 전용면적 옆에 안착
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
                            '전용면적(평)': pyeong,  # 💡 전용면적 옆에 안착
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
st.title("🏢 SPECIAL-DONG 전용 무인 감시 지휘소 (V9.3) - 수정일 26년 5월 29일 (금)")

tab1, tab2 = st.tabs(["🏠 국토부 실거래가 자동 수집판", "📈 통합 자산 무인 감시망"])

with tab1:
    st.subheader("🛰️ 공공데이터포털 실시간 실거래가 매핑")
    
    col_req1, col_req2 = st.columns(2)
    with col_req1:
        target_region = st.selectbox("타격 대상 지역 선택", 
                                     options=["41171", "41210", "11500"], 
                                     format_func=lambda x: "안양시 만안구" if x=="41171" else "광명시" if x=="41210" else "서울 강서구")
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
        
        # 💡 대한민국 시간(KST) 적용 완료
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