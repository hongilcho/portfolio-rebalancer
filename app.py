import streamlit as st
import pandas as pd
import os
import shutil
import io
import zipfile
from data_manager import (
    init_db, get_all_assets, get_all_accounts, add_account, update_account, delete_account,
    add_asset, update_asset, delete_asset, get_holdings_by_account, get_all_holdings, save_account_holdings,
    execute_trade, get_trade_history, delete_trade,
    ACCOUNT_TYPES, update_account_settings, update_account_priorities
)
import datetime
from price_fetcher import get_exchange_rate_usd_krw, fetch_asset_prices
from rebalance_calculator import calculate_rebalancing_plan

from ui_tab1_dashboard import render_tab1
from ui_tab2_rebalance import render_tab2
from ui_tab3_assets import render_tab3
from ui_tab4_history import render_tab4
from ui_tab5_settings import render_tab5
# Helper function for Korean number formatting
from utils import num_to_kr_mixed, format_usd_label
# 페이지 기본 설정
st.set_page_config(
    page_title="자산 배분 포트폴리오 매니저",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# 보안: 로그인 암호 확인 로직
# ---------------------------------------------------------
def check_password():
    """Returns `True` if the user had the correct password."""
    
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # 보안을 위해 입력한 암호는 세션에서 즉시 삭제
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.markdown("<h2 style='text-align: center; margin-top: 100px;'>🔒 포트폴리오 매니저 로그인</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>접속을 위해 암호를 입력해 주세요.</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.text_input(
            "비밀번호", type="password", on_change=password_entered, key="password", label_visibility="collapsed"
        )
        if "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("😕 비밀번호가 일치하지 않습니다.")
    return False

if not check_password():
    st.stop()
# ---------------------------------------------------------

# UI 시인성 향상을 위한 커스텀 CSS 주입
st.markdown("""
<style>
/* 슬라이더 위 숫자(Thumb Value) 크기 및 볼드 적용 */
div[data-testid="stThumbValue"] {
    font-size: 1.4rem !important;
    font-weight: 900 !important;
    padding-bottom: 2px !important;
}
</style>
""", unsafe_allow_html=True)

# DB 초기화
init_db()

# 세션 상태 초기화
if "usd_krw" not in st.session_state:
    rate, source = get_exchange_rate_usd_krw()
    st.session_state.usd_krw = rate
    st.session_state.rate_source = source

if "price_data" not in st.session_state:
    st.session_state.price_data = None

# 사이드바: 데이터 백업 및 복구
with st.sidebar:
    st.header("💾 데이터 내보내기 (CSV)")
    st.write("현재 계좌, 종목, 보유 수량, 매매 기록을 엑셀에서 분석할 수 있도록 CSV 압축 파일로 다운로드합니다.")
    
    # 1. 다운로드 (CSV Zip)
    def generate_csv_zip():
        # fetch data
        accounts_df = pd.DataFrame(get_all_accounts())
        assets_df = pd.DataFrame(get_all_assets())
        holdings_df = pd.DataFrame(get_all_holdings())
        trades_df = pd.DataFrame(get_trade_history())
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            if not accounts_df.empty:
                zip_file.writestr("accounts.csv", accounts_df.to_csv(index=False).encode('utf-8-sig'))
            if not assets_df.empty:
                zip_file.writestr("assets.csv", assets_df.to_csv(index=False).encode('utf-8-sig'))
            if not holdings_df.empty:
                zip_file.writestr("holdings.csv", holdings_df.to_csv(index=False).encode('utf-8-sig'))
            if not trades_df.empty:
                zip_file.writestr("trade_history.csv", trades_df.to_csv(index=False).encode('utf-8-sig'))
        
        zip_buffer.seek(0)
        return zip_buffer
        
    st.download_button(
        label="📥 CSV 분석용 데이터 다운로드",
        data=generate_csv_zip(),
        file_name=f"portfolio_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
        mime="application/zip",
        use_container_width=True
    )
    
    st.divider()
    st.caption("※ 클라우드 DB 연동 중이므로 매일 자동으로 안전하게 백업됩니다. 파일 덮어쓰기를 통한 복구 기능은 제외되었습니다.")

# 커스텀 CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0F172A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #64748B;
        margin-bottom: 1.2rem;
    }
    .account-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .risk-badge {
        background-color: #FEE2E2;
        color: #991B1B;
        border-radius: 4px;
        padding: 2px 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .safe-badge {
        background-color: #DCFCE7;
        color: #166534;
        border-radius: 4px;
        padding: 2px 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">📈 자산 배분 포트폴리오 매니저</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">계좌별 예수금, 보유 수량/평단가 관리 & IRP 위험자산 70% 제약 및 납입/세액공제 한도 모니터링</div>', unsafe_allow_html=True)

# ---------------------------------------------------------
# 상단 환율 바 & 실시간 새로고침
# ---------------------------------------------------------
col_rate1, col_rate2, col_rate3 = st.columns([2, 2, 1])

with col_rate1:
    st.metric(
        label=f"💵 실시간 USD/KRW 환율 ({st.session_state.rate_source})",
        value=f"{st.session_state.usd_krw:,.2f} 원"
    )

with col_rate2:
    custom_rate = st.number_input(
        "환율 수동 수정 (필요시 입력)",
        value=st.session_state.usd_krw,
        step=1.0,
        format="%.2f"
    )
    if custom_rate != st.session_state.usd_krw:
        st.session_state.usd_krw = custom_rate

with col_rate3:
    st.write(" ")
    st.write(" ")
    if st.button("🔄 시세 새로고침", use_container_width=True):
        rate, source = get_exchange_rate_usd_krw()
        st.session_state.usd_krw = rate
        st.session_state.rate_source = source
        st.session_state.price_data = None
        st.success("환율 및 시세를 재요청합니다!")
        st.rerun()

st.divider()

# ---------------------------------------------------------
# 기본 데이터 및 실시간 주가 수집
# ---------------------------------------------------------
assets = get_all_assets()
accounts = get_all_accounts()
account_options_by_id = {str(a['id']): f"[{a['account_type']}] {a['account_alias']}" for a in accounts}

if st.session_state.price_data is None and assets:
    with st.spinner("실시간 주가 및 환율 시세를 불러오는 중입니다..."):
        price_results, _ = fetch_asset_prices(assets, st.session_state.usd_krw)
        st.session_state.price_data = price_results

# 가격 데이터 빠른 조회를 위한 맵 (asset_id -> price_krw)
price_map = {}
if st.session_state.price_data:
    for item in st.session_state.price_data:
        price_map[str(item['id'])] = item['price_krw']

# ---------------------------------------------------------
# 메인 탭 구성
# ---------------------------------------------------------

# ---------------------------------------------------------
# 단일 페이지 라우팅 (Single Page Routing)으로 성능 최적화
# ---------------------------------------------------------
menus = [
    "📊 1. 포트폴리오 현황",
    "🎯 2. 목표 비중 설정",
    "⚖️ 3. 리밸런싱 전략",
    "📝 4. 매매 기록",
    "⚙️ 5. 기초 환경 세팅"
]

# st.pills가 최신 버전에 있지만, 호환성을 위해 horizontal radio 사용
selected_menu = st.radio("메뉴 선택", menus, horizontal=True, label_visibility="collapsed")
st.markdown("<hr style='margin-top: 0px; margin-bottom: 20px;'>", unsafe_allow_html=True)

if selected_menu == menus[0]:
    render_tab1()
elif selected_menu == menus[1]:
    render_tab2()
elif selected_menu == menus[2]:
    render_tab3()
elif selected_menu == menus[3]:
    render_tab4()
elif selected_menu == menus[4]:
    render_tab5()
