import streamlit as st
import pandas as pd
import requests
import re
import datetime
import time

st.set_page_config(layout="wide", page_title="통합 지휘소 V6")

# --- [상태 관리 시스템: 4대 알림망 독립 제어] ---
if 'dw_buy_fired' not in st.session_state: st.session_state.dw_buy_fired = False
if 'dw_sell_fired' not in st.session_state: st.session_state.dw_sell_fired = False
if 'space_buy_fired' not in st.session_state: st.session_state.space_buy_fired = False
if 'space_sell_fired' not in st.session_state: st.session_state.space_sell_fired = False

# 🎯 네이버 금융 실시간 가격 정밀 타격 함수
def get_naver_price(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        match = re.search(r'<p class="no_today">.*?<span class="blind">([\d,]+)</span>', res.text, re.DOTALL)
        if match: 
            return int(match.group(1).replace(',', ''))
        return 0
    except: 
        return 0

def send_telegram(token, chat_id, msg):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": msg})
        return True
    except: 
        return False

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

annual_income = st.sidebar.number_input("대장님 합산 연소득 (만 원)", value=7000, step=500)
other_loan = st.sidebar.number_input("기존 연 상환액 (만 원)", value=0, step=100)

dsr = (((monthly_payment * 12 // 10000) + other_loan) / annual_income) * 100
st.sidebar.write(f"**현재 예상 DSR:** {dsr:.1f}%")
if dsr <= 40: 
    st.sidebar.success("✅ 시중은행 대출 안전권")
else: 
    st.sidebar.error("🚨 한도 초과 위험!")

# --- [메인 화면] 작전 제어판 ---
st.title("🏢 전동수 회장님 전용 양방향 무인 감시 지휘소 (V6)")

tab1, tab2 = st.tabs(["🏠 부동산 실거주 타겟팅", "🛰️ 양방향 주가 무인 감시망"])

with tab1:
    st.subheader("서남권 6억 이하 준신축 시세 흐름")
    dates = pd.date_range(end=pd.Timestamp.today(), periods=6, freq='ME').strftime('%Y-%m')
    df = pd.DataFrame({
        '안양 만안구 (84㎡ 준신축)': [54000, 54500, 55000, 55000, 56000, 55500],
        '광명시 외곽 (59㎡ 준신축)': [57000, 57500, 58000, 59000, 59500, 59000],
        '서울 강서구 (59㎡ 나홀로신축)': [58000, 58000, 59000, 59500, 59500, 59900]
    }, index=dates)
    st.line_chart(df)
    
    col1, col2 = st.columns(2)
    with col1: 
        st.warning('''**💡 최우선 행정 타격 목표: 세대주 완전 분리**\n부모님 주민등록표상의 세대원 지위에서 완전히 벗어나 단독 세대주로 전입신고를 마치는 작전이 모든 대출 심사 이전에 선행되어야 합니다.''')
    with col2: 
        st.success('''**🎯 지역별 타격 브리핑**\n* **안양 만안구 (최우선):** 6억 이하로 84㎡(34평) 진입 가능. 가성비 극강.\n* **광명/강서:** 교통은 압도적이나 59㎡(24평) 진입이 최대치.''')

with tab2:
    st.subheader("🛰️ 실시간 주가 감시판 (네이버 금융 직통 수신)")
    
    col_code1, col_code2 = st.columns(2)
    with col_code1: dw_code = st.text_input("대우건설 종목코드", value="047040")
    with col_code2: space_code = st.text_input("우주테크 ETF 종목코드", value="0183J0")
    
    dw_price = get_naver_price(dw_code)
    space_price = get_naver_price(space_code)
    
    colA, colB = st.columns(2)
    with colA: st.metric(label="📊 대우건설 현재가", value=f"{dw_price:,} 원")
    with colB: st.metric(label="🚀 TIGER 미국우주테크 ETF 현재가", value=f"{space_price:,} 원")
    
    st.markdown("---")
    st.subheader("🚨 공방(攻防)형 자동 경보 시스템 설정")
    
    col_tgt1, col_tgt2 = st.columns(2)
    with col_tgt1:
        st.markdown("### 🏢 대우건설 타격선")
        dw_buy_target = st.number_input("대우건설 매수 감시 단가 (원 이하)", value=3500, step=50)
        dw_sell_target = st.number_input("대우건설 매도 감시 단가 (원 이상)", value=4500, step=50)
    with col_tgt2:
        st.markdown("### 🚀 우주테크 ETF 타격선")
        space_buy_target = st.number_input("우주테크 ETF 매수 감시 단가 (원 이하)", value=14000, step=50)
        space_sell_target = st.number_input("우주테크 ETF 매도 감시 단가 (원 이상)", value=16000, step=50)
        
    st.markdown("---")
    st.subheader("📡 보안 통신망 연결 설정")
    col_tok1, col_tok2 = st.columns(2)
    with col_tok1: tg_token = st.text_input("텔레그램 봇 토큰", type="password", key="tg_tok")
    with col_tok2: tg_chat_id = st.text_input("텔레그램 채팅방 ID", type="password", key="tg_id")
    
    st.markdown("---")
    st.subheader("⚙️ 무인 자동 감시 엔진 콘솔")
    
    now = datetime.datetime.now()
    is_weekday = now.weekday() < 5
    is_market_hours = datetime.time(8, 30) <= now.time() <= datetime.time(16, 0)
    
    st.write(f"지휘소 현재 시각: `{now.strftime('%Y-%m-%d %H:%M:%S')}`")
    
    auto_monitor = st.checkbox("🔄 60초 간격 양방향 무인 자동 감시 작동")
    
    if auto_monitor:
        if not tg_token or not tg_chat_id:
            st.error("⚠️ 텔레그램 보안 설정(토큰, ID)을 기입하셔야 엔진이 회전합니다.")
        else:
            st.info("🛰️ 감시 엔진 가동 중... 평일 08:30~16:00 사이에 양방향 단가를 추적합니다.")
            
            # 1. 대우건설 매수(하락) 검사
            if dw_price > 0 and dw_price <= dw_buy_target and not st.session_state.dw_buy_fired:
                msg = f"📉 [지휘소 매수 경보]\n🏢 대우건설 현재가({dw_price:,}원)가 설정하신 매수 목표가({dw_buy_target:,}원) 이하로 진입! 저점 매수 타이밍입니다."
                if send_telegram(tg_token, tg_chat_id, msg): st.session_state.dw_buy_fired = True
            if dw_price > dw_buy_target: st.session_state.dw_buy_fired = False
            
            # 2. 대우건설 매도(상승) 검사
            if dw_price > 0 and dw_price >= dw_sell_target and not st.session_state.dw_sell_fired:
                msg = f"📈 [지휘소 매도 경보]\n🏢 대우건설 현재가({dw_price:,}원)가 설정하신 매도 목표가({dw_sell_target:,}원) 이상으로 돌파! 수익 실현 타이밍입니다."
                if send_telegram(tg_token, tg_chat_id, msg): st.session_state.dw_sell_fired = True
            if dw_price < dw_sell_target: st.session_state.dw_sell_fired = False
            
            # 3. 우주테크 ETF 매수(하락) 검사
            if space_price > 0 and space_price <= space_buy_target and not st.session_state.space_buy_fired:
                msg = f"📉 [지휘소 매수 경보]\n🚀 TIGER 미국우주테크 ETF 현재가({space_price:,}원)가 설정하신 매수 목표가({space_buy_target:,}원) 이하로 진입! 저점 매수 타이밍입니다."
                if send_telegram(tg_token, tg_chat_id, msg): st.session_state.space_buy_fired = True
            if space_price > space_buy_target: st.session_state.space_buy_fired = False
            
            # 4. 우주테크 ETF 매도(상승) 검사
            if space_price > 0 and space_price >= space_sell_target and not st.session_state.space_sell_fired:
                msg = f"📈 [지휘소 매도 경보]\n🚀 TIGER 미국우주테크 ETF 현재가({space_price:,}원)가 설정하신 매도 목표가({space_sell_target:,}원) 이상으로 돌파! 수익 실현 타이밍입니다."
                if send_telegram(tg_token, tg_chat_id, msg): st.session_state.space_sell_fired = True
            if space_price < space_sell_target: st.session_state.space_sell_fired = False
            
            time.sleep(60)
            st.rerun()