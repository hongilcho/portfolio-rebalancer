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

# Helper function for Korean number formatting
def num_to_kr_mixed(num):
    if not num or num == 0:
        return "0원"
    num = int(num)
    places = ["", "십", "백", "천"]
    units = ["", "만", "억", "조", "경"]
    
    result = ""
    num_str = str(num)
    chunks = []
    while len(num_str) > 0:
        chunks.append(num_str[-4:])
        num_str = num_str[:-4]
        
    for i, chunk in enumerate(chunks):
        if int(chunk) == 0:
            continue
        
        chunk_res = ""
        for j, digit_char in enumerate(chunk[::-1]):
            d = int(digit_char)
            if d > 0:
                chunk_res = f"{d}{places[j]}" + chunk_res
        
        result = chunk_res + units[i] + " " + result
        
    return result.replace("  ", " ").strip() + "원"

def format_usd_label(usd_val):
    if not usd_val or float(usd_val) == 0.0:
        return "0 USD (약 0원)"
    usd_val = float(usd_val)
    rate = st.session_state.get('usd_krw', 1350.0)
    krw_val = usd_val * rate
    return f"{usd_val:,.2f} USD (약 {num_to_kr_mixed(krw_val)})"

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
                zip_file.writestr("accounts.csv", accounts_df.to_csv(index=False, encoding='utf-8-sig'))
            if not assets_df.empty:
                zip_file.writestr("assets.csv", assets_df.to_csv(index=False, encoding='utf-8-sig'))
            if not holdings_df.empty:
                zip_file.writestr("holdings.csv", holdings_df.to_csv(index=False, encoding='utf-8-sig'))
            if not trades_df.empty:
                zip_file.writestr("trade_history.csv", trades_df.to_csv(index=False, encoding='utf-8-sig'))
        
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
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 1. 포트폴리오 현황",
    "🎯 2. 목표 비중 설정",
    "⚖️ 3. 리밸런싱 전략",
    "📝 4. 매매 기록",
    "⚙️ 5. 기초 환경 세팅"
])

# =========================================================
# TAB 1: 계좌 현황 & 보유 잔고 입력/모니터링
# =========================================================
with tab1:
    
    if not accounts:
        st.warning("등록된 계좌가 없습니다. [4. 계좌/자산 등록 및 관리] 탭에서 계좌를 등록해 주세요.")
    else:
        # 계좌별 종합 평가금액 계산
        account_summaries = []
        total_portfolio_eval = 0.0
        
        for acc in accounts:
            acc_id = acc['id']
            acc_no = acc['account_no']
            acc_alias = acc['account_alias']
            acc_type = acc['account_type']
            dep_krw = acc['deposit_krw']
            dep_usd = acc['deposit_usd']
            dep_usd_krw = dep_usd * st.session_state.usd_krw
            total_deposit = dep_krw + dep_usd_krw
            
            holdings = get_holdings_by_account(acc_id)
            stock_eval = 0.0
            risk_stock_eval = 0.0
            safe_stock_eval = 0.0
            
            stock_buy_total = 0.0
            
            holding_details = []
            for h in holdings:
                qty = h['quantity']
                avg_p_krw = h['avg_price']
                curr_p = price_map.get(h['asset_id'], avg_p_krw if avg_p_krw > 0 else 0)
                eval_val = qty * curr_p
                stock_eval += eval_val
                stock_buy_total += (qty * avg_p_krw)
                
                if h['is_risk_asset']:
                    risk_stock_eval += eval_val
                else:
                    safe_stock_eval += eval_val
                    
                profit_krw = eval_val - (qty * avg_p_krw)
                profit_pct = (profit_krw / (qty * avg_p_krw) * 100) if (qty * avg_p_krw) > 0 else 0.0
                
                holding_details.append({
                    "종목명": h['asset_name'],
                    "티커": h['ticker'],
                    "위험구분": "🔴 위험자산" if h['is_risk_asset'] else "🟢 안전자산",
                    "보유수량": f"{qty:,.0f} 주",
                    "평단가": f"{avg_p_krw:,.0f} 원",
                    "현재가": f"{curr_p:,.0f} 원",
                    "평가금액": f"{eval_val:,.0f} 원",
                    "손익": f"{profit_krw:+,.0f} 원 ({profit_pct:+.1f}%)"
                })
                
            total_acc_val = total_deposit + stock_eval
            total_portfolio_eval += total_acc_val
            
            risk_pct = (risk_stock_eval / total_acc_val * 100) if total_acc_val > 0 else 0.0
            
            account_summaries.append({
                "acc": acc,
                "total_val": total_acc_val,
                "deposit_krw": dep_krw,
                "deposit_usd": dep_usd,
                "stock_eval": stock_eval,
                "stock_buy_total": stock_buy_total,
                "risk_eval": risk_stock_eval,
                "safe_eval": safe_stock_eval,
                "risk_pct": risk_pct,
                "holdings": holding_details
            })
            
        # ---------------------------------------------------------
        # 포트폴리오 전체 종목별 집계 로직
        # ---------------------------------------------------------
        portfolio_assets = {}
        total_krw_cash = 0.0
        total_usd_cash = 0.0
        
        for acc in accounts:
            total_krw_cash += acc['deposit_krw']
            total_usd_cash += acc['deposit_usd']
            
            acc_holdings = get_holdings_by_account(acc['id'])
            for h in acc_holdings:
                aid = str(h['asset_id'])
                if aid not in portfolio_assets:
                    portfolio_assets[aid] = {
                        "name": h['asset_name'],
                        "ticker": h['ticker'],
                        "qty": 0.0,
                        "buy_amt_krw": 0.0,
                        "eval_amt_krw": 0.0,
                    }
                qty = h['quantity']
                avg_p_krw = h['avg_price']
                curr_p = price_map.get(aid, avg_p_krw if avg_p_krw > 0 else 0)
                eval_val = qty * curr_p
                
                portfolio_assets[aid]['qty'] += qty
                portfolio_assets[aid]['buy_amt_krw'] += qty * avg_p_krw
                portfolio_assets[aid]['eval_amt_krw'] += eval_val

        stock_summary_rows = []
        cash_summary_rows = []
        
        total_stock_eval = sum(data['eval_amt_krw'] for data in portfolio_assets.values() if data['qty'] > 0)
        total_stock_buy = sum(data['buy_amt_krw'] for data in portfolio_assets.values() if data['qty'] > 0)
        
        target_weight_map = {str(a['id']): a['target_weight'] for a in assets}
        
        # 1. 주식/자산
        for a in assets:
            aid = str(a['id'])
            data = portfolio_assets.get(aid, {
                "name": a['name'],
                "ticker": a['ticker'],
                "qty": 0.0,
                "buy_amt_krw": 0.0,
                "eval_amt_krw": 0.0
            })
            
            profit_krw = data['eval_amt_krw'] - data['buy_amt_krw']
            profit_pct = (profit_krw / data['buy_amt_krw'] * 100) if data['buy_amt_krw'] > 0 else 0.0
            
            # 비중 계산을 현금 제외 주식/금현물 총액 기준으로 변경
            weight_pct = (data['eval_amt_krw'] / total_stock_eval * 100) if total_stock_eval > 0 else 0.0
            target_w = target_weight_map.get(aid, 0.0)
            diff_w = weight_pct - target_w
            
            unit_str = "g" if "KRX 금" in data['name'] or "금현물" in data['name'] else "주"
            qty_disp = f"{int(data['qty']):,}{unit_str}" if float(data['qty']).is_integer() else f"{float(data['qty']):,.2f}{unit_str}"
            
            stock_summary_rows.append({
                "종목명": f"{data['name']} ({data['ticker']})",
                "수량": qty_disp,
                "평가금액(원)": data['eval_amt_krw'],
                "손익(원)": profit_krw,
                "수익률(%)": profit_pct,
                "평단가(원)": data['buy_amt_krw'] / data['qty'] if data['qty'] > 0 else 0,
                "현재가(원)": price_map.get(aid, 0.0),
                "비중(%)": weight_pct,
                "목표비중(%)": target_w,
                "괴리율(%)": diff_w,
            })
        
        # 2. 현금 (원화)
        if total_krw_cash > 0:
            cash_summary_rows.append({
                "종목명": "💵 현금 (KRW)",
                "수량": "-",
                "평가금액(원)": total_krw_cash,
            })
            
        # 3. 현금 (USD)
        if total_usd_cash > 0:
            eval_usd_krw = total_usd_cash * st.session_state.usd_krw
            cash_summary_rows.append({
                "종목명": f"💵 현금 (USD)",
                "수량": f"${total_usd_cash:,.2f}",
                "평가금액(원)": eval_usd_krw,
            })
            
        total_stock_profit = total_stock_eval - total_stock_buy
        total_stock_return = (total_stock_profit / total_stock_buy * 100) if total_stock_buy > 0 else 0.0
        
        # 총 자산 대시보드
        st.markdown("### 📊 전체 포트폴리오 요약")
        
        if total_stock_profit > 0:
            sp_color, sp_sign = "#ff6b6b", "+"
        elif total_stock_profit < 0:
            sp_color, sp_sign = "#4dabf7", ""
        else:
            sp_color, sp_sign = "gray", ""
            
        st.markdown(
            f"<div style='display: flex; gap: 40px; margin-top: 15px; margin-bottom: 20px; flex-wrap: wrap;'>"
            f"  <div>"
            f"    <div style='font-size: 14px; color: gray;'>💵 총 매입 금액 (투자 원금)</div>"
            f"    <div style='font-size: 26px; font-weight: 600;'>{total_stock_buy:,.0f} 원</div>"
            f"  </div>"
            f"  <div>"
            f"    <div style='font-size: 14px; color: gray;'>📈 총 주식 평가금액 (현금 제외)</div>"
            f"    <div style='font-size: 26px; font-weight: 600;'>{total_stock_eval:,.0f} 원</div>"
            f"  </div>"
            f"  <div>"
            f"    <div style='font-size: 14px; color: gray;'>총 평가 손익</div>"
            f"    <div style='font-size: 26px; font-weight: 600; color: {sp_color};'>{sp_sign}{total_stock_profit:,.0f} 원</div>"
            f"  </div>"
            f"  <div>"
            f"    <div style='font-size: 14px; color: gray;'>총 수익률</div>"
            f"    <div style='font-size: 26px; font-weight: 600; color: {sp_color};'>{sp_sign}{total_stock_return:.1f}%</div>"
            f"  </div>"
            f"</div>",
            unsafe_allow_html=True
        )
        
        def style_profit_returns(val):
            if isinstance(val, (int, float)) and val != 0.0:
                if val > 0:
                    return 'color: #ff6b6b; font-weight: 700; font-size: 15px;'
                elif val < 0:
                    return 'color: #4dabf7; font-weight: 700; font-size: 15px;'
            return 'font-weight: 700; font-size: 15px;'

        def style_qty(val):
            return 'font-weight: 700; font-size: 15px;'

        if stock_summary_rows:
            st.markdown("##### 📈 주식 및 금현물 자산")
            df_stock = pd.DataFrame(stock_summary_rows)
            df_stock = df_stock.sort_values(by="비중(%)", ascending=False)
            
            # 표 1: 자산 기본 정보
            st.markdown("**[자산 기본 정보]**")
            df_stock_info = df_stock[["종목명", "수량", "평가금액(원)", "손익(원)", "수익률(%)", "평단가(원)", "현재가(원)"]]
            
            # 합계 행 추가
            total_row_stock = pd.DataFrame([{
                "종목명": "총합계",
                "수량": "-",
                "평가금액(원)": total_stock_eval,
                "손익(원)": total_stock_profit,
                "수익률(%)": total_stock_return,
                "평단가(원)": "-",
                "현재가(원)": "-"
            }])
            df_stock_info = pd.concat([df_stock_info, total_row_stock], ignore_index=True)
            
            styled_info_df = (df_stock_info.style
                         .format({
                             "평가금액(원)": "{:,.0f}",
                             "손익(원)": "{:,.0f}",
                             "평단가(원)": lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else x,
                             "현재가(원)": lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else x
                         })
                         .map(style_profit_returns, subset=["손익(원)", "수익률(%)"])
                         .map(style_qty, subset=["수량"]))
            
            st.dataframe(
                styled_info_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "수익률(%)": st.column_config.NumberColumn(format="%.1f%%"),
                }
            )
            
            # 표 2: 비중 및 괴리율 (HTML 직접 렌더링으로 확실한 막대그래프 제공)
            st.markdown("**[비중 및 괴리율]**")
            df_stock_weight = df_stock[["종목명", "비중(%)", "목표비중(%)", "괴리율(%)"]]
            
            import math
            max_diff = df_stock_weight['괴리율(%)'].abs().max() if not df_stock_weight.empty else 0
            if max_diff == 0:
                scale_max = 1.0
            else:
                scale_max = round(max_diff * 3.5, 1)
            
            html = "<table style='width: 100%; text-align: center; border-collapse: collapse; font-size: 14px;'>"
            html += "<tr style='background-color: rgba(128,128,128,0.1); border-bottom: 2px solid rgba(128,128,128,0.3);'>"
            html += "<th style='padding: 8px;'>종목명</th><th style='padding: 8px;'>현 비중(%)</th><th style='padding: 8px;'>목표비중(%)</th><th style='padding: 8px; width: 220px;'>괴리율(%)</th></tr>"
            
            for _, row in df_stock_weight.iterrows():
                name = row['종목명']
                w = row['비중(%)']
                tw = row['목표비중(%)']
                diff = row['괴리율(%)']
                
                diff_str = f"{diff:+.1f}%"
                diff_color = "#ff6b6b" if diff > 0 else "#4dabf7" if diff < 0 else "gray"
                
                # 막대그래프 HTML (가운데 0 기준, 유동적 스케일)
                bar_html = f"<div style='width: 180px; margin: 0 auto;'>"
                # 괴리율 값 텍스트를 그래프 상단에 오버레이
                bar_html += f"<div style='font-weight: bold; color: {diff_color}; margin-bottom: 4px; font-size: 13px;'>{diff_str}</div>"
                
                bar_html += f"<div style='display: flex; align-items: center; width: 100%; height: 16px; background: rgba(128,128,128,0.15); border-radius: 4px; position: relative;'>"
                bar_html += f"<div style='position: absolute; left: 50%; top: -2px; bottom: -2px; width: 2px; background: rgba(128,128,128,0.8); z-index: 10;'></div>" # 중앙선
                
                if diff > 0:
                    w_px = min(90, int((diff / scale_max) * 90))
                    bar_html += f"<div style='position: absolute; left: 50%; top: 0; bottom: 0; width: {w_px}px; background: #ff6b6b; border-radius: 0 4px 4px 0;'></div>"
                elif diff < 0:
                    w_px = min(90, int((abs(diff) / scale_max) * 90))
                    bar_html += f"<div style='position: absolute; right: 50%; top: 0; bottom: 0; width: {w_px}px; background: #4dabf7; border-radius: 4px 0 0 4px;'></div>"
                    
                bar_html += "</div>"
                
                # 눈금(tick marks)
                bar_html += f"<div style='display: flex; justify-content: space-between; font-size: 11px; color: gray; margin-top: 3px; padding: 0 2px;'>"
                bar_html += f"<span>-{scale_max:.1f}%</span><span>0</span><span>+{scale_max:.1f}%</span>"
                bar_html += "</div></div>"
                
                html += f"<tr style='border-bottom: 1px solid rgba(128,128,128,0.2);'>"
                html += f"<td style='padding: 10px;'>{name}</td>"
                html += f"<td style='padding: 10px;'>{w:.1f}%</td>"
                html += f"<td style='padding: 10px;'>{tw:.1f}%</td>"
                html += f"<td style='padding: 10px;'>{bar_html}</td>"
                html += "</tr>"
                
            html += "</table><br/>"
        st.markdown(html, unsafe_allow_html=True)
            
        if cash_summary_rows:
            st.markdown("##### 💵 현금성 자산")
            df_cash = pd.DataFrame(cash_summary_rows)
            
            total_cash = df_cash["평가금액(원)"].sum()
            total_row_cash = pd.DataFrame([{
                "종목명": "총합계",
                "수량": "-",
                "평가금액(원)": total_cash
            }])
            df_cash = pd.concat([df_cash, total_row_cash], ignore_index=True)
            
            styled_cash_df = df_cash.style.format({"평가금액(원)": "{:,.0f}"})
            
            st.dataframe(
                styled_cash_df,
                use_container_width=True,
                hide_index=True
            )
            
        st.divider()
        
        st.markdown("### 💳 계좌별 자산 현황")
        
        for summary in account_summaries:
            acc = summary['acc']
            acc_type = acc['account_type']
            type_info = ACCOUNT_TYPES.get(acc_type, {})
            
            with st.expander(f"📌 [{acc_type}] {acc['account_alias']} ({acc['account_no']}) - 총 {summary['total_val']:,.0f} 원", expanded=True):
                c1, c2 = st.columns([5, 3])
                
                # 주식 평가금액 및 손익 (HTML Markdown 사용)
                acc_profit_krw = summary['stock_eval'] - summary['stock_buy_total']
                acc_profit_pct = (acc_profit_krw / summary['stock_buy_total'] * 100) if summary['stock_buy_total'] > 0 else 0.0
                
                if acc_profit_krw > 0:
                    p_color, p_sign = "#ff6b6b", "+" # 부드러운 빨강
                elif acc_profit_krw < 0:
                    p_color, p_sign = "#4dabf7", ""  # 부드러운 파랑
                else:
                    p_color, p_sign = "gray", ""
                    
                c1.markdown(
                    f"<div style='display: flex; gap: 30px; margin-bottom: 5px; flex-wrap: wrap;'>"
                    f"  <div>"
                    f"    <div style='font-size: 14px; color: gray;'>📈 주식 평가금액</div>"
                    f"    <div style='font-size: 26px; font-weight: 600;'>{summary['stock_eval']:,.0f} 원</div>"
                    f"  </div>"
                    f"  <div>"
                    f"    <div style='font-size: 14px; color: gray;'>손익</div>"
                    f"    <div style='font-size: 26px; font-weight: 600; color: {p_color};'>{p_sign}{acc_profit_krw:,.0f} 원</div>"
                    f"  </div>"
                    f"  <div>"
                    f"    <div style='font-size: 14px; color: gray;'>수익률</div>"
                    f"    <div style='font-size: 26px; font-weight: 600; color: {p_color};'>{p_sign}{acc_profit_pct:.1f}%</div>"
                    f"  </div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
                
                c2.markdown(
                    f"<div style='font-size: 14px; color: gray;'>💵 계좌 총 자산 (주식 + 예수금)</div>"
                    f"<div style='font-size: 24px; font-weight: 600; padding-bottom: 5px;'>{summary['total_val']:,.0f} 원</div>"
                    f"<div style='font-size: 13px; color: gray;'>"
                    f"보유 예수금: 원화 {acc['deposit_krw']:,.0f}원 | 달러 ${acc['deposit_usd']:,.2f}"
                    f"</div>",
                    unsafe_allow_html=True
                )
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                # IRP 규제 및 한도 모니터링 경고
                if acc_type == "IRP":
                    if summary['risk_pct'] > 70.0:
                        st.error(f"🚨 **[IRP 규제 경고]** 위험자산 비중이 **{summary['risk_pct']:.1f}%**로 최대 한도(70%)를 초과했습니다! 신규 매수가 제한될 수 있으므로 안전자산(채권 등) 비율을 높여주세요.")
                    else:
                        st.success(f"✅ **[IRP 규제 준수]** 위험자산 비중 **{summary['risk_pct']:.1f}%** (70% 한도 이내 준수 중)")
                
                # 한도 게이지 바 (현재 평가금액이 아닌 평단가 기준 투자 원금 및 예수금 총액 기준)
                annual_limit = float(acc.get("annual_limit", 0.0))
                tax_limit = float(acc.get("tax_limit", 0.0))
                
                principal_val = summary['stock_buy_total'] + summary['deposit_krw'] + (summary['deposit_usd'] * st.session_state.usd_krw)
                
                if annual_limit > 0:
                    limit_pct = min(1.0, principal_val / annual_limit)
                    st.caption(f"📅 **연간 납입 한도**: {annual_limit/10000:,.0f}만원 중 현재 투자원금 기준 약 {principal_val/10000:,.1f}만원 소진 ({limit_pct*100:.1f}%)")
                    st.progress(limit_pct)
                elif type_info.get("annual_limit", 0) > 0 and annual_limit == 0:
                    st.caption("📅 **연간 납입 한도**: 무제한 설정됨")
                    
                if tax_limit > 0:
                    tax_pct = min(1.0, principal_val / tax_limit)
                    st.caption(f"💡 **세액공제 최대 한도**: {tax_limit/10000:,.0f}만원 중 현재 투자원금 기준 약 {principal_val/10000:,.1f}만원 채움 ({tax_pct*100:.1f}%)")
                    st.progress(tax_pct)

                # 계좌별 보유 종목 테이블
                st.markdown("##### 📦 보유 종목 목록")
                if summary['holdings']:
                    st.dataframe(pd.DataFrame(summary['holdings']), use_container_width=True, hide_index=True)
                else:
                    st.info("이 계좌에 등록된 보유 주식이 없습니다. 아래 [수량/평단가 입력]에서 추가할 수 있습니다.")
                    
        st.divider()
        # 계좌별 잔고 & 수량/평단가 수정 폼
        # ---------------------------------------------------------
        with st.expander("✏️ 보유 잔고 및 예수금 입력/수정하기"):
            selected_acc_label = st.selectbox(
                "잔고 및 수량을 수정할 계좌 선택",
                options=[f"[{a['account_type']}] {a['account_alias']} ({a['account_no']})" for a in accounts],
                key="select_acc_for_edit"
            )
            selected_acc_idx = [f"[{a['account_type']}] {a['account_alias']} ({a['account_no']})" for a in accounts].index(selected_acc_label)
            target_acc = accounts[selected_acc_idx]
            
            with st.form("edit_holdings_form"):
                st.markdown(f"#### 💳 **{target_acc['account_alias']}** ({target_acc['account_type']}) 잔고 설정")
                
                c_dep1, c_dep2 = st.columns(2)
                with c_dep1:
                    edit_krw = st.number_input("원화 예수금 (원)", min_value=0.0, value=float(target_acc['deposit_krw']), step=10000.0)
                with c_dep2:
                    edit_usd = st.number_input("달러 예수금 ($)", min_value=0.0, value=float(target_acc['deposit_usd']), step=10.0)
                    
                st.markdown("#### 📦 이 계좌에서 운용 가능한 종목 수량 및 평단가")
                
                # 이 계좌에 매핑이 허용된 자산만 표시 (Account ID 기반 매칭)
                current_holdings = get_holdings_by_account(target_acc['id'])
                holding_map = {h['asset_id']: h for h in current_holdings}
                
                allowed_assets_for_acc = [a for a in assets if str(target_acc['id']) in a['allowed_accounts']]
                
                if not allowed_assets_for_acc:
                    st.warning("이 계좌에 운용 가능하도록 매핑된 자산이 없습니다. [3. 목표 비중 & 계좌 매핑] 탭에서 먼저 계좌를 연결해 주세요.")
            
                holding_inputs = []
                for asset in allowed_assets_for_acc:
                    aid = asset['id']
                    existing = holding_map.get(aid, {'quantity': 0.0, 'avg_price': 0.0})
                    
                    risk_str = "🔴 위험자산" if asset['is_risk_asset'] else "🟢 안전자산"
                    st.markdown(f"**{asset['name']}** (`{asset['ticker']}` | {asset['market']} | {risk_str})")
                    
                    col_h1, col_h2 = st.columns(2)
                    with col_h1:
                        current_qty = st.session_state.get(f"qty_{target_acc['id']}_{aid}", float(existing['quantity']))
                        unit_str = "g" if "금현물" in asset['name'] else "주"
                        if float(current_qty).is_integer():
                            qty_disp = f"{int(current_qty):,}{unit_str}"
                        else:
                            qty_disp = f"{float(current_qty):,.2f}{unit_str}"
                        qty = st.number_input(f"보유 수량 :blue[({qty_disp})] - {asset['name']}", min_value=0.0, value=float(existing['quantity']), step=1.0, key=f"qty_{target_acc['id']}_{aid}")
                    with col_h2:
                        current_avg_p = st.session_state.get(f"avg_{target_acc['id']}_{aid}", float(existing['avg_price']))
                        avg_p_disp = f"{int(current_avg_p):,}원" if float(current_avg_p).is_integer() else f"{float(current_avg_p):,.2f}원"
                        avg_p = st.number_input(f"평균 매입가 (원화 환산) :blue[({avg_p_disp})] - {asset['name']}", min_value=0.0, value=float(existing['avg_price']), step=100.0, key=f"avg_{target_acc['id']}_{aid}")
                        
                    holding_inputs.append({'asset_id': aid, 'quantity': qty, 'avg_price': avg_p})
                    st.divider()
                    
                save_h_btn = st.form_submit_button("💾 예수금 및 보유 수량/평단가 저장", use_container_width=True)
                if save_h_btn:
                    # Update deposit
                    update_account(target_acc['id'], target_acc['account_no'], target_acc['account_alias'], target_acc['account_type'], edit_krw, edit_usd, target_acc.get('annual_limit', 0.0), target_acc.get('tax_limit', 0.0), target_acc['notes'], target_acc.get('priority', 99), target_acc.get('limit_preference', 'ANNUAL'), target_acc.get('current_year_deposit', 0.0))
                    # Update holdings
                    if holding_inputs:
                        save_account_holdings(target_acc['id'], holding_inputs)
                    st.session_state.price_data = None
                    st.success("성공적으로 저장되었습니다!")
                    st.rerun()

# =========================================================
# TAB 5: 기초 환경 세팅 (시세 모니터링)
# =========================================================
with tab5:
    st.subheader("📊 실시간 시세 현황 & 자산별 시세 & 위험자산 구분")
    
    if not assets:
        st.warning("등록된 자산이 없습니다.")
    else:
        display_data = []
        if st.session_state.price_data:
            for item, orig_asset in zip(st.session_state.price_data, assets):
                market_icon = "🇰🇷 국내" if item['market'] == 'KR' else "🇺🇸 미국"
                price_native_str = f"{item['price_native']:,.0f} 원" if item['market'] == 'KR' else f"${item['price_native']:,.2f}"
                mapped_accs = [account_options_by_id.get(str(x), f"알수없음({x})") for x in orig_asset['allowed_accounts']] if orig_asset['allowed_accounts'] else []
                allowed_acc_str = ", ".join(mapped_accs) if mapped_accs else "없음"
                risk_label = "🔴 위험자산" if orig_asset['is_risk_asset'] else "🟢 안전자산"
                
                display_data.append({
                    "종목명": item['name'],
                    "티커": item['ticker'],
                    "위험 구분": risk_label,
                    "시장": market_icon,
                    "목표 비중": f"{item['target_weight']:.1f}%",
                    "현재가 (현지)": price_native_str,
                    "원화 환산가": f"{item['price_krw']:,.0f} 원",
                    "운용 가능 계좌": mapped_accs if mapped_accs else ["없음"],
                    "시세 상태": item['status']
                })
        
        st.dataframe(
            pd.DataFrame(display_data), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "운용 가능 계좌": st.column_config.ListColumn("운용 가능 계좌", width="large")
            }
        )

# =========================================================
# TAB 2: 목표 비중 설정
# =========================================================
with tab2:
    st.subheader("🎯 포트폴리오 목표 비중 및 계좌 매핑 설정 & 가능 계좌/위험 구분 설정")
    
    if not assets:
        st.info("설정할 자산이 없습니다.")
    else:
        all_account_type_names = list(ACCOUNT_TYPES.keys())
        weight_inputs = {}
        account_inputs = {}
        risk_inputs = {}
        
        for asset in assets:
            aid = asset['id']
            st.markdown(f"##### 📌 **{asset['name']}** (`{asset['ticker']}` | {asset['market']})")
            
            # 콜백을 통한 슬라이더와 숫자 입력창 실시간 동기화
            tw_slider_key = f"tws_{aid}"
            tw_num_key = f"twn_{aid}"
            
            if tw_slider_key not in st.session_state:
                st.session_state[tw_slider_key] = float(asset['target_weight'])
            if tw_num_key not in st.session_state:
                st.session_state[tw_num_key] = float(asset['target_weight'])
                
            def sync_from_slider(k_s=tw_slider_key, k_n=tw_num_key):
                st.session_state[k_n] = st.session_state[k_s]
                
            def sync_from_num(k_s=tw_slider_key, k_n=tw_num_key):
                st.session_state[k_s] = st.session_state[k_n]
                
            # 시인성 향상을 위해 4개 컬럼으로 분할
            col_slider, col_num, col_acc, col_risk = st.columns([1.5, 0.6, 1.4, 0.9])
            
            with col_slider:
                st.slider(f"🎯 비중 조절", min_value=0.0, max_value=100.0, step=0.1, format="%.1f%%", key=tw_slider_key, on_change=sync_from_slider)
                
            with col_num:
                w_val = st.number_input(f"직접입력(%)", min_value=0.0, max_value=100.0, step=0.1, key=tw_num_key, on_change=sync_from_num)
                weight_inputs[aid] = w_val
                
            with col_acc:
                valid_default_accs = [str(x) for x in asset['allowed_accounts'] if str(x) in account_options_by_id]
                accs_val = st.multiselect(f"매수/운용 가능 계좌 선택", options=list(account_options_by_id.keys()), format_func=lambda x: account_options_by_id[x], default=valid_default_accs, key=f"tacc_{aid}")
                account_inputs[aid] = accs_val
                
            with col_risk:
                st.markdown("<div style='margin-top: 2rem;'></div>", unsafe_allow_html=True)
                if asset['is_risk_asset']:
                    st.markdown("🔴 **위험자산** (IRP 70% 제한)")
                else:
                    st.markdown("🟢 **안전자산**")
                risk_inputs[aid] = asset['is_risk_asset']
            st.divider()
            
        current_sum = sum(weight_inputs.values())
        st.markdown(f"### 🧮 설정된 목표 비중 합계: **{current_sum:.1f}%**")
        
        if st.button("💾 목표 비중 및 계좌 매핑 저장", use_container_width=True):
            for asset in assets:
                aid = asset['id']
                update_asset(aid, asset['name'], asset['ticker'], asset['market'], weight_inputs[aid], account_inputs[aid], risk_inputs[aid], asset['notes'])
            st.session_state.price_data = None
            st.success("저장되었습니다!")
            st.rerun()

# =========================================================
# TAB 3: 리밸런싱 전략 수립
# =========================================================
with tab3:
    st.subheader("⚖️ 리밸런싱 전략 수립")
    st.markdown("현재 자산 상태와 목표 비중을 바탕으로 **구체적인 매매/이체 지시서**를 생성합니다.")
    
    # 1. 시나리오 선택
    scenario = st.radio(
        "리밸런싱 시나리오 선택",
        options=["NEW_CASH", "DRIFT"],
        format_func=lambda x: {
            "NEW_CASH": "💰 신규 자금 투입 (매도 없이 매수만 진행)",
            "DRIFT": "📉 괴리율 기반 리밸런싱 (목표 비중 이탈 시 매도/매수)"
        }[x],
        horizontal=True
    )
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        new_cash_input = st.number_input(f"신규 투입 현금액 :blue[({num_to_kr_mixed(st.session_state.get('new_cash_in', 0))})]", min_value=0.0, value=0.0, step=100000.0, key="new_cash_in")
    with col_s2:
        drift_input = st.number_input("허용 괴리율 (%)", min_value=0.0, value=5.0, step=0.5, disabled=(scenario == "NEW_CASH"))
        
    # 2. 실행 및 초기화 버튼
    # 2. 실행 버튼
    if st.button("🚀 리밸런싱 전략 계산하기", type="primary", use_container_width=True):
        if not assets or not accounts:
            st.error("자산과 계좌를 먼저 등록해주세요.")
        elif not st.session_state.price_data:
            st.error("시세 데이터를 먼저 새로고침 해주세요 (1번 탭).")
        else:
            st.session_state.run_rebalance = True
            
    if st.session_state.get('run_rebalance', False):
        with st.spinner("최적 매매 경로를 계산 중입니다..."):
            total_krw_cash = sum(a['deposit_krw'] for a in accounts if a['account_type'] != 'CMA')
            
            # Fetch holdings
            holdings_raw = []
            for a in accounts:
                holdings_raw.extend(get_holdings_by_account(a['id']))
            
            # Calculate portfolio assets aggregated
            portfolio_assets = {}
            for h in holdings_raw:
                aid = str(h['asset_id'])
                qty = h['quantity']
                price = price_map.get(aid, 0.0)
                if aid not in portfolio_assets:
                    portfolio_assets[aid] = {'qty': 0, 'eval_amt_krw': 0, 'buy_amt_krw': 0}
                portfolio_assets[aid]['qty'] += qty
                portfolio_assets[aid]['eval_amt_krw'] += qty * price
                portfolio_assets[aid]['buy_amt_krw'] += qty * h['avg_price']
            
            # Call Calculator
            t_plan, tr_plan, sim_assets, success, msg = calculate_rebalancing_plan(
                assets=assets,
                portfolio_assets=portfolio_assets,
                accounts=accounts,
                holdings=holdings_raw,
                price_map=price_map,
                total_krw_cash=total_krw_cash,
                usd_krw_rate=st.session_state.usd_krw,
                scenario=scenario,
                new_cash_krw=new_cash_input,
                drift_threshold=drift_input
            )
            

            # --- USER DEBUG OUTPUT ---
            import json
            try:
                with open('debug_output.txt', 'w', encoding='utf-8') as df:
                    df.write("PRICE MAP:\n")
                    df.write(json.dumps(price_map, ensure_ascii=False, indent=2))
                    df.write("\n\nTRADE PLAN:\n")
                    df.write(json.dumps(t_plan, indent=2, ensure_ascii=False))
            except Exception as e:
                pass
            if not success:
                st.error(msg)
            elif len(t_plan) == 0 and len(tr_plan) == 0:
                st.success(msg)
            else:
                st.success("✅ 리밸런싱 전략 계산이 완료되었습니다. 아래 지시서를 순서대로 따라주세요.")
                
                st.markdown("### 1️⃣ 자금 이체 지시서")
                if tr_plan:
                    for tr in tr_plan:
                        if tr['type'] == 'DEPOSIT':
                            st.info(f"📥 {tr['msg']}")
                        else:
                            st.success(f"✔️ {tr['msg']}")
                else:
                    st.write("필요한 자금 이체가 없습니다.")
                    
                st.markdown("### 2️⃣ 매매 지시서")
                if t_plan:
                    df_trade = pd.DataFrame([{
                        "계좌": t['account_alias'],
                        "종류": "🔴 매도" if t['type'] == 'SELL' else "🔵 매수",
                        "자산명": t['asset_name'],
                        "수량": f"{t['qty']:,.0f}주",
                        "예상 체결가": f"{t['price']:,.0f}원",
                        "총액": f"{t['total_krw']:,.0f}원"
                    } for t in t_plan])
                    st.dataframe(df_trade, use_container_width=True, hide_index=True)
                else:
                    st.write("필요한 매매가 없습니다.")
                    
                st.markdown("### 📊 리밸런싱 후 예상 포트폴리오 비중")
                if sim_assets:
                    total_sim = sum(s['projected_val'] for s in sim_assets)
                    
                    html = "<table style='width: 100%; text-align: center; border-collapse: collapse; font-size: 14px;'>"
                    html += "<tr style='background-color: rgba(128,128,128,0.1); border-bottom: 2px solid rgba(128,128,128,0.3);'>"
                    html += "<th style='padding: 8px;'>자산명</th><th style='padding: 8px;'>최종 수량</th><th style='padding: 8px;'>예상 평가액</th>"
                    html += "<th style='padding: 8px;'>목표 비중(%)</th><th style='padding: 8px;'>예상 비중(%)</th><th style='padding: 8px; width: 220px;'>괴리율(%)</th></tr>"
                    
                    max_diff = 0.0
                    for s in sim_assets:
                        s['projected_weight'] = (s['projected_val'] / total_sim * 100) if total_sim > 0 else 0
                        s['drift'] = s['projected_weight'] - s['target_weight']
                        if abs(s['drift']) > max_diff:
                            max_diff = abs(s['drift'])
                    
                    scale_max = round(max_diff * 3.5, 1) if max_diff > 0 else 1.0
                    
                    for s in sim_assets:
                        name = s['asset_name']
                        final_qty = s['current_qty'] + s['qty_diff']
                        
                        if s['qty_diff'] > 0:
                            qty_str = f"{final_qty:,.0f} <span style='color: #ff6b6b;'>(+{s['qty_diff']:,.0f})</span>"
                        elif s['qty_diff'] < 0:
                            qty_str = f"{final_qty:,.0f} <span style='color: #4dabf7;'>({s['qty_diff']:,.0f})</span>"
                        else:
                            qty_str = f"{final_qty:,.0f} (-)"
                            
                        val_str = f"{s['projected_val']:,.0f}원"
                        tw = s['target_weight']
                        pw = s['projected_weight']
                        diff = s['drift']
                        diff_str = f"{diff:+.1f}%"
                        diff_color = "#ff6b6b" if diff > 0 else "#4dabf7" if diff < 0 else "gray"
                        
                        bar_html = f"<div style='width: 180px; margin: 0 auto;'>"
                        bar_html += f"<div style='font-weight: bold; color: {diff_color}; margin-bottom: 4px; font-size: 13px;'>{diff_str}</div>"
                        bar_html += f"<div style='display: flex; align-items: center; width: 100%; height: 16px; background: rgba(128,128,128,0.15); border-radius: 4px; position: relative;'>"
                        bar_html += f"<div style='position: absolute; left: 50%; top: -2px; bottom: -2px; width: 2px; background: rgba(128,128,128,0.8); z-index: 10;'></div>"
                        
                        if diff > 0:
                            w_px = min(90, int((diff / scale_max) * 90))
                            bar_html += f"<div style='position: absolute; left: 50%; top: 0; bottom: 0; width: {w_px}px; background: #ff6b6b; border-radius: 0 4px 4px 0;'></div>"
                        elif diff < 0:
                            w_px = min(90, int((abs(diff) / scale_max) * 90))
                            bar_html += f"<div style='position: absolute; right: 50%; top: 0; bottom: 0; width: {w_px}px; background: #4dabf7; border-radius: 4px 0 0 4px;'></div>"
                            
                        bar_html += "</div></div>"
                        
                        html += f"<tr style='border-bottom: 1px solid rgba(128,128,128,0.2);'>"
                        html += f"<td style='padding: 10px;'>{name}</td>"
                        html += f"<td style='padding: 10px;'>{qty_str}</td>"
                        html += f"<td style='padding: 10px;'>{val_str}</td>"
                        html += f"<td style='padding: 10px;'>{tw:.1f}%</td>"
                        html += f"<td style='padding: 10px;'>{pw:.1f}%</td>"
                        html += f"<td style='padding: 10px;'>{bar_html}</td>"
                        html += "</tr>"
                        
                    # Add Total Row
                    total_pre = sum(portfolio_assets.get(str(s['asset_id']), {}).get('eval_amt_krw', 0.0) for s in sim_assets)
                    total_diff = total_sim - total_pre
                    
                    if total_diff > 0:
                        diff_html = f"<span style='color: #ff6b6b;'>(+{total_diff:,.0f})</span>"
                    elif total_diff < 0:
                        diff_html = f"<span style='color: #4dabf7;'>({total_diff:,.0f})</span>"
                    else:
                        diff_html = "(-)"
                        
                    html += f"<tr style='background-color: rgba(128,128,128,0.1); border-top: 2px solid rgba(128,128,128,0.3); font-weight: bold;'>"
                    html += f"<td style='padding: 10px;'>총합</td>"
                    html += f"<td style='padding: 10px;'>-</td>"
                    html += f"<td style='padding: 10px;'>{total_sim:,.0f}원 <br><span style='font-size: 12px; font-weight: normal;'>{diff_html}</span></td>"
                    html += f"<td style='padding: 10px;'>100.0%</td>"
                    html += f"<td style='padding: 10px;'>100.0%</td>"
                    html += f"<td style='padding: 10px;'>-</td>"
                    html += "</tr>"
                    
                    html += "</table>"
                    st.markdown(html, unsafe_allow_html=True)
                        
                    st.markdown("---")
                    if st.button("🗑️ 계산 결과 지우기", use_container_width=True):
                        st.session_state.run_rebalance = False
                        st.rerun()

# =========================================================
# TAB 4: 실제 매매 기록
# =========================================================
with tab4:
    st.subheader("📝 실제 매매 기록 (일괄 입력)")
    st.markdown("리밸런싱 전략 실행 결과를 한 번에 입력하세요. 아래 표에 행을 추가하여 여러 건을 한 번에 기록할 수 있습니다.")
    st.info("달러($) 해외 자산을 매매한 경우에도 증권사 앱 기준의 **원화(KRW) 환산 체결 단가**를 기입해 주세요.")
    
    # 상단 시세 참고표
    with st.expander("💡 실시간 시세 참고표 (현재가 확인용)", expanded=False):
        if st.session_state.price_data:
            price_ref_df = pd.DataFrame([
                {"종목": ast['name'], "티커": ast['ticker'], "현재가(원)": f"{int(price_map.get(ast['id'], 0)):,}"} 
                for ast in assets
            ])
            st.dataframe(price_ref_df, hide_index=True, use_container_width=True)
        else:
            st.warning("시세 데이터가 아직 로드되지 않았습니다.")
            
    import uuid
    if 'buy_rows' not in st.session_state:
        st.session_state.buy_rows = [str(uuid.uuid4())]
    if 'sell_rows' not in st.session_state:
        st.session_state.sell_rows = [str(uuid.uuid4())]
        
    def add_buy_row():
        st.session_state.buy_rows.append(str(uuid.uuid4()))
    def remove_buy_row(rid):
        if len(st.session_state.buy_rows) > 1:
            st.session_state.buy_rows.remove(rid)
        else:
            st.warning("최소 1개의 행은 있어야 합니다.")
            
    def add_sell_row():
        st.session_state.sell_rows.append(str(uuid.uuid4()))
    def remove_sell_row(rid):
        if len(st.session_state.sell_rows) > 1:
            st.session_state.sell_rows.remove(rid)
        else:
            st.warning("최소 1개의 행은 있어야 합니다.")

    t_date = st.date_input("일괄 체결 일자", datetime.date.today())
    
    col_buy, col_sell = st.columns(2)
    
    buy_inputs = {}
    sell_inputs = {}
    
    with col_buy:
        st.markdown("#### 🔴 매수(Buy) 입력")
        st.markdown("**[계좌] / [종목] / [수량] / [단가]**")
        for rid in st.session_state.buy_rows:
            c1, c2, c3, c4, c5 = st.columns([1.5, 2, 1, 1.2, 0.5])
            
            acc_id = c1.selectbox("계좌", options=[a['id'] for a in accounts], format_func=lambda x: next((f"[{a['account_type']}] {a['account_alias']}" for a in accounts if a['id'] == x), ""), key=f"b_acc_{rid}", label_visibility="collapsed")
            
            allowed_assets = [ast for ast in assets if str(acc_id) in ast.get('allowed_accounts', [])]
            if not allowed_assets:
                c2.error("가능 종목 없음")
                ast_id = None
                qty = c3.number_input("수량", min_value=0.0, max_value=0.0, key=f"b_qty_{rid}", label_visibility="collapsed")
                price = c4.number_input("단가", min_value=0, value=0, key=f"b_pri_{rid}", label_visibility="collapsed")
            else:
                ast_id = c2.selectbox("종목", options=[a['id'] for a in allowed_assets], format_func=lambda x: next((f"{a['name']}" for a in assets if a['id'] == x), ""), key=f"b_ast_{rid}", label_visibility="collapsed")
                qty = c3.number_input("수량", min_value=0.0, step=1.0, format="%.4f", key=f"b_qty_{rid}_{ast_id}", label_visibility="collapsed")
                default_p = int(price_map.get(ast_id, 0)) if ast_id else 0
                price = c4.number_input("단가", min_value=0, step=1000, value=default_p, key=f"b_pri_{rid}_{ast_id}", label_visibility="collapsed")
            
            c5.button("❌", key=f"del_b_{rid}", on_click=remove_buy_row, args=(rid,))
            
            if ast_id and qty > 0 and price > 0:
                buy_inputs[rid] = {'acc': acc_id, 'ast': ast_id, 'qty': qty, 'price': price}
                
        st.button("➕ 매수 추가", on_click=add_buy_row, use_container_width=True)

    with col_sell:
        st.markdown("#### 🔵 매도(Sell) 입력")
        st.markdown("**[계좌] / [종목] / [수량] / [단가]**")
        for rid in st.session_state.sell_rows:
            c1, c2, c3, c4, c5 = st.columns([1.5, 2, 1, 1.2, 0.5])
            
            acc_id = c1.selectbox("계좌", options=[a['id'] for a in accounts], format_func=lambda x: next((f"[{a['account_type']}] {a['account_alias']}" for a in accounts if a['id'] == x), ""), key=f"s_acc_{rid}", label_visibility="collapsed")
            
            from data_manager import get_holdings_by_account
            acc_holdings = get_holdings_by_account(acc_id)
            # 필터링: 수량이 0보다 큰 것만 매도 가능
            acc_holdings = [h for h in acc_holdings if h['quantity'] > 0]
            
            if not acc_holdings:
                c2.error("매도 가능 잔고 없음")
                ast_id = None
                qty = c3.number_input("수량", min_value=0.0, max_value=0.0, key=f"s_qty_{rid}", label_visibility="collapsed")
                price = c4.number_input("단가", min_value=0, value=0, key=f"s_pri_{rid}", label_visibility="collapsed")
            else:
                ast_id = c2.selectbox("종목", options=[h['asset_id'] for h in acc_holdings], format_func=lambda x: next((f"{a['name']}" for a in assets if a['id'] == x), ""), key=f"s_ast_{rid}", label_visibility="collapsed")
                
                max_qty = next((h['quantity'] for h in acc_holdings if h['asset_id'] == ast_id), 0.0)
                qty = c3.number_input("수량", min_value=0.0, max_value=float(max_qty), step=1.0, format="%.4f", key=f"s_qty_{rid}_{ast_id}", label_visibility="collapsed")
                
                default_p = int(price_map.get(ast_id, 0)) if ast_id else 0
                price = c4.number_input("단가", min_value=0, step=1000, value=default_p, key=f"s_pri_{rid}_{ast_id}", label_visibility="collapsed")
            
            c5.button("❌", key=f"del_s_{rid}", on_click=remove_sell_row, args=(rid,))
            
            if ast_id and qty > 0 and price > 0:
                sell_inputs[rid] = {'acc': acc_id, 'ast': ast_id, 'qty': qty, 'price': price}
                
        st.button("➕ 매도 추가", on_click=add_sell_row, use_container_width=True)
        
    if st.button("💾 위 내역 전체 일괄 저장", type="primary", use_container_width=True):
        success_count = 0
        errors = []
        
        for r in buy_inputs.values():
            s, m = execute_trade(str(t_date), r['acc'], r['ast'], "BUY", r['qty'], r['price'])
            if s: success_count += 1
            else: errors.append(m)
            
        for r in sell_inputs.values():
            s, m = execute_trade(str(t_date), r['acc'], r['ast'], "SELL", r['qty'], r['price'])
            if s: success_count += 1
            else: errors.append(m)
            
        if errors:
            st.error("일부 처리에 실패했습니다: " + ", ".join(errors))
        if success_count > 0:
            st.success(f"{success_count}건의 매매 기록이 성공적으로 저장되었습니다!")
            st.session_state.buy_rows = [str(uuid.uuid4())]
            st.session_state.sell_rows = [str(uuid.uuid4())]
            st.rerun()
            
    st.markdown("---")
    st.markdown("##### 📜 최근 매매 기록 (Trade History)")
    trade_history = get_trade_history()
    
    if not trade_history:
        st.info("현재 저장된 매매 기록이 없습니다.")
    else:
        df_trades = pd.DataFrame(trade_history)
        df_trades['계좌'] = df_trades.apply(lambda row: f"[{row['account_type']}] {row['account_alias']}", axis=1)
        df_trades['종목'] = df_trades.apply(lambda row: f"{row['asset_name']}", axis=1)
        df_trades['매매'] = df_trades['trade_type'].apply(lambda x: "매수" if x == "BUY" else "매도")
        df_trades['체결금액(원)'] = df_trades['quantity'] * df_trades['price']
        # trade_date is typically a string 'YYYY-MM-DD', convert to datetime for filtering
        df_trades['trade_date_dt'] = pd.to_datetime(df_trades['trade_date'])
        
        min_date = df_trades['trade_date_dt'].min().date()
        max_date = df_trades['trade_date_dt'].max().date()
        
        # --- 1. 검색 및 필터링 기능 ---
        st.markdown("**🔍 필터링 옵션**")
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            # 기본적으로 최근 3개월 조회를 기본값으로 세팅
            import datetime
            default_start = max(min_date, datetime.date.today() - datetime.timedelta(days=90))
            date_range = st.date_input("조회 기간", value=(default_start, max_date), min_value=min_date, max_value=max_date)
            
        with col_f2:
            all_accounts = ["전체"] + list(df_trades['계좌'].unique())
            sel_acc = st.multiselect("계좌 선택", options=all_accounts, default="전체")
            
        with col_f3:
            all_assets = ["전체"] + list(df_trades['종목'].unique())
            sel_ast = st.multiselect("종목 선택", options=all_assets, default="전체")
            
        # 데이터 필터링 적용
        df_filtered = df_trades.copy()
        
        # 날짜 필터 적용
        if len(date_range) == 2:
            start_d, end_d = date_range
            df_filtered = df_filtered[(df_filtered['trade_date_dt'].dt.date >= start_d) & (df_filtered['trade_date_dt'].dt.date <= end_d)]
        elif len(date_range) == 1:
            start_d = date_range[0]
            df_filtered = df_filtered[df_filtered['trade_date_dt'].dt.date >= start_d]
            
        if "전체" not in sel_acc and len(sel_acc) > 0:
            df_filtered = df_filtered[df_filtered['계좌'].isin(sel_acc)]
        if "전체" not in sel_ast and len(sel_ast) > 0:
            df_filtered = df_filtered[df_filtered['종목'].isin(sel_ast)]
            
        st.caption(f"조회된 데이터: 총 {len(df_filtered)}건 (마우스 스크롤을 통해 전체 확인 가능합니다)")
            
        df_filtered = df_filtered.reset_index(drop=True) # 인덱스 초기화 (선택 로직을 위해)
        
        if len(df_filtered) == 0:
            st.info("조건에 맞는 매매 기록이 없습니다.")
        else:
            display_df = df_filtered[['trade_date', '계좌', '종목', '매매', 'quantity', 'price', '체결금액(원)']]
            display_df.columns = ['날짜', '계좌', '종목', '구분', '수량', '단가(원)', '체결금액(원)']
            
            def color_trade_type(val):
                if val == '매수': return 'color: #ff6b6b; font-weight: bold;'
                elif val == '매도': return 'color: #4dabf7; font-weight: bold;'
                return ''
                
            styled_trades = display_df.style.map(color_trade_type, subset=['구분'])
            
            # --- 2. Interactive Table 렌더링 ---
            event = st.dataframe(
                styled_trades, 
                use_container_width=True, 
                hide_index=True, 
                on_select="rerun",
                selection_mode="multi-row",
                key="trade_history_table",
                height=400, # 약 10행 정도 스크롤 높이 고정
                column_config={
                    "수량": st.column_config.NumberColumn(format="%.4f"),
                    "단가(원)": st.column_config.NumberColumn(format="%d"),
                    "체결금액(원)": st.column_config.NumberColumn(format="%d"),
                }
            )
            
            # 안내 문구를 표 아래로 이동
            st.markdown("💡 *표 좌측 체크박스를 통해 지우고 싶은 기록을 체크(다중 선택 가능)하시면 아래에 삭제 버튼이 나타납니다.*")
            
            # --- 3. 선택된 데이터 삭제 로직 ---
            selected_indices = event.selection.rows
            
            if len(selected_indices) > 0:
                st.markdown("---")
                st.markdown(f"##### 🗑️ 선택된 {len(selected_indices)}개의 기록 삭제 및 되돌리기")
                st.info("해당 기록들을 삭제하면, 데이터베이스가 즉시 재계산되어 평단가와 수량이 완벽히 복원됩니다.")
                
                if st.button("❌ 체크한 기록 모두 삭제", type="primary", use_container_width=True):
                    success_count = 0
                    errors = []
                    
                    for idx in selected_indices:
                        trade_id = df_filtered.iloc[idx]['id']
                        success, msg = delete_trade(trade_id)
                        if success:
                            success_count += 1
                        else:
                            errors.append(msg)
                            
                    if errors:
                        st.error("일부 삭제 실패: " + ", ".join(errors))
                    if success_count > 0:
                        st.success(f"{success_count}건의 매매 기록이 성공적으로 삭제 및 복구되었습니다!")
                        st.rerun()

# =========================================================
# TAB 5: 기초 환경 세팅 (계좌/자산 관리)
# =========================================================
with tab5:
    st.divider()
    st.subheader("⚙️ 계좌/자산 등록 및 관리")
    
    # 모바일 환경을 고려하여 좌우(columns) 배치 대신 st.container()를 활용한 상하 배치 적용
    col_mgmt1 = st.container()
    st.markdown("<br>", unsafe_allow_html=True)
    col_mgmt2 = st.container()
    
    # ---------------------------------------------------------
    # 1. 계좌 등록 및 삭제
    # ---------------------------------------------------------
    with col_mgmt1:
        st.markdown("### 📋 등록된 계좌 목록")
        if accounts:
            acc_df = pd.DataFrame([{
                "계좌번호": a['account_no'],
                "별명": a['account_alias'],
                "유형": a['account_type'],
                "원화예수금(원)": f"{a['deposit_krw']:,.0f}",
                "달러예수금($)": f"{a['deposit_usd']:,.2f}",
                "납입한도(원)": f"{a['annual_limit']:,.0f}" if float(a.get('annual_limit', 0)) > 0 else "무제한",
                "세액공제한도(원)": f"{a['tax_limit']:,.0f}" if float(a.get('tax_limit', 0)) > 0 else "-",
                "한도 적용": "-" if not any(k in a['account_type'] for k in ['IRP', '연금', 'ISA']) else ("연간납입한도" if 'ISA' in a['account_type'] or a.get('limit_preference', 'ANNUAL') == 'ANNUAL' else "세액공제한도"),
                "매수 우선순위": int(a.get('priority', 99))
            } for a in accounts])
            st.dataframe(acc_df, use_container_width=True, hide_index=True)
        else:
            st.info("등록된 계좌가 없습니다.")
            
        st.divider()

        col_acc1, col_acc2, col_acc3 = st.columns(3)

        with col_acc1:
            add_acc_k = st.session_state.get('add_acc_k', 0)
            with st.expander(f"➕ 신규 등록{' '*add_acc_k}"):
                is_unlimited = st.checkbox("한도 제한 없음 (종합매매 등)", value=False, key="add_limit_unlimited")
                
                new_acc_no = st.text_input("계좌번호", placeholder="예: 110-123-456789", key="add_acc_no")
                new_acc_alias = st.text_input("계좌 별명", placeholder="예: 주력 ISA 계좌", key="add_acc_alias")
                new_acc_type = st.selectbox("계좌 유형", options=list(ACCOUNT_TYPES.keys()), key="add_acc_type")
                
                new_krw = st.number_input(f"원화 예수금 :blue[({num_to_kr_mixed(st.session_state.get('add_krw_in', 0))})]", min_value=0.0, value=0.0, step=10000.0, key="add_krw_in")
                new_usd = st.number_input(f"달러 예수금 :blue[({format_usd_label(st.session_state.get('add_usd_in', 0))})]", min_value=0.0, value=0.0, step=10.0, key="add_usd_in")
                new_annual_limit = st.number_input(f"연간 납입 한도 :blue[({num_to_kr_mixed(st.session_state.get('add_ann_in', 20000000.0))})]", min_value=0.0, value=0.0 if is_unlimited else 20000000.0, step=1000000.0, disabled=is_unlimited, key="add_ann_in")
                new_tax_limit = st.number_input(f"세액공제 한도 :blue[({num_to_kr_mixed(st.session_state.get('add_tax_in', 0))})]", min_value=0.0, value=0.0, step=1000000.0, disabled=is_unlimited, key="add_tax_in")
                new_acc_notes = st.text_input("메모", placeholder="계좌 설명", key="add_acc_notes")
                st.markdown("---")
                
                def_prio = {"IRP": 1, "연금저축": 2, "ISA": 3, "일반매매": 4}.get(new_acc_type, 99)
                new_priority = st.number_input("매수 우선순위 (작을수록 우선)", min_value=1, value=def_prio, step=1, key="add_acc_priority")
                
                is_isa_add = "ISA" in new_acc_type
                limit_opts = ["연간 납입 한도 기준", "세액공제 한도 기준"]
                new_limit_pref_label = st.selectbox("한도 적용 방식 (리밸런싱 시)", options=["연간 납입 한도 기준"] if is_isa_add else limit_opts, key="add_acc_limit_pref")
                new_limit_pref = "ANNUAL" if new_limit_pref_label == "연간 납입 한도 기준" else "TAX"
                
                if st.button("등록하기", use_container_width=True, key="add_acc_btn"):
                    if not new_acc_no.strip() or not new_acc_alias.strip():
                        st.error("계좌번호/별명 입력 필요")
                    else:
                        final_annual = 0.0 if is_unlimited else new_annual_limit
                        final_tax = 0.0 if is_unlimited else new_tax_limit
                        success, msg = add_account(new_acc_no, new_acc_alias, new_acc_type, new_krw, new_usd, final_annual, final_tax, new_acc_notes, new_priority, new_limit_pref, 0.0)
                        if success:
                            st.session_state.add_acc_k = add_acc_k + 1
                            for k in ['add_acc_no', 'add_acc_alias', 'add_acc_type', 'add_krw_in', 'add_usd_in', 'add_ann_in', 'add_tax_in', 'add_acc_notes', 'add_limit_unlimited']:
                                if k in st.session_state: del st.session_state[k]
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                                
        with col_acc2:
            edit_acc_k = st.session_state.get('edit_acc_k', 0)
            with st.expander(f"✏️ 정보 수정{' '*edit_acc_k}"):
                if accounts:
                    edit_acc_label = st.selectbox("수정할 계좌 선택", options=[f"[{a['account_type']}] {a['account_alias']} ({a['account_no']})" for a in accounts], key="edit_acc_sel")
                    edit_acc_idx = [f"[{a['account_type']}] {a['account_alias']} ({a['account_no']})" for a in accounts].index(edit_acc_label)
                    target_edit_acc = accounts[edit_acc_idx]
                    acc_id = target_edit_acc['id']
                    
                    is_edit_unlimited = st.checkbox("한도 제한 없음 (종합매매 등)", value=(float(target_edit_acc.get('annual_limit', 0.0)) == 0.0 and float(target_edit_acc.get('tax_limit', 0.0)) == 0.0), key=f"edit_limit_unlimited_{acc_id}")
                    
                    e_acc_no = st.text_input("계좌번호", value=target_edit_acc['account_no'], key=f"edit_acc_no_{acc_id}")
                    e_acc_alias = st.text_input("계좌 별명", value=target_edit_acc['account_alias'], key=f"edit_acc_alias_{acc_id}")
                    e_acc_type = st.selectbox("계좌 유형", options=list(ACCOUNT_TYPES.keys()), index=list(ACCOUNT_TYPES.keys()).index(target_edit_acc['account_type']), key=f"edit_acc_type_{acc_id}")
                    
                    e_krw = st.number_input(f"원화 예수금 :blue[({num_to_kr_mixed(st.session_state.get(f'e_krw_in_{acc_id}', float(target_edit_acc['deposit_krw'])))})]", min_value=0.0, value=float(target_edit_acc['deposit_krw']), step=10000.0, key=f"e_krw_in_{acc_id}")
                    e_usd = st.number_input(f"달러 예수금 :blue[({format_usd_label(st.session_state.get(f'e_usd_in_{acc_id}', float(target_edit_acc['deposit_usd'])))})]", min_value=0.0, value=float(target_edit_acc['deposit_usd']), step=10.0, key=f"e_usd_in_{acc_id}")
                    
                    e_annual = st.number_input(f"연간 납입 한도 :blue[({num_to_kr_mixed(st.session_state.get(f'e_annual_in_{acc_id}', float(target_edit_acc.get('annual_limit', 0.0))))})]", min_value=0.0, value=float(target_edit_acc.get('annual_limit', 0.0)), step=1000000.0, disabled=is_edit_unlimited, key=f"e_annual_in_{acc_id}")
                    e_tax = st.number_input(f"세액공제 한도 :blue[({num_to_kr_mixed(st.session_state.get(f'e_tax_in_{acc_id}', float(target_edit_acc.get('tax_limit', 0.0))))})]", min_value=0.0, value=float(target_edit_acc.get('tax_limit', 0.0)), step=1000000.0, disabled=is_edit_unlimited, key=f"e_tax_in_{acc_id}")
                    
                    e_acc_notes = st.text_input("메모", value=target_edit_acc['notes'] if target_edit_acc['notes'] else "", key=f"e_acc_notes_{acc_id}")
                    st.markdown("---")
                    e_priority = st.number_input("매수 우선순위 (작을수록 우선)", min_value=1, value=int(target_edit_acc.get('priority', 99)), step=1, key=f"e_prio_{acc_id}")
                    
                    is_isa_edit = "ISA" in e_acc_type
                    limit_opts = ["연간 납입 한도 기준", "세액공제 한도 기준"]
                    curr_pref_idx = 0 if target_edit_acc.get('limit_preference', 'ANNUAL') == 'ANNUAL' else 1
                    e_limit_pref_label = st.selectbox("한도 적용 방식 (리밸런싱 시)", options=["연간 납입 한도 기준"] if is_isa_edit else limit_opts, index=0 if is_isa_edit else curr_pref_idx, key=f"e_limit_{acc_id}")
                    e_limit_pref = "ANNUAL" if e_limit_pref_label == "연간 납입 한도 기준" else "TAX"
                    
                    if st.button("수정하기", use_container_width=True, key=f"edit_acc_btn_{acc_id}"):
                        final_annual = 0.0 if is_edit_unlimited else e_annual
                        final_tax = 0.0 if is_edit_unlimited else e_tax
                        success, msg = update_account(target_edit_acc['id'], e_acc_no, e_acc_alias, e_acc_type, e_krw, e_usd, final_annual, final_tax, e_acc_notes, e_priority, e_limit_pref, float(target_edit_acc.get('current_year_deposit', 0.0)))
                        if success:
                            st.session_state.edit_acc_k = edit_acc_k + 1
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                else:
                    st.info("수정할 계좌가 없습니다.")
                    
        with col_acc3:
            with st.expander("🗑️ 계좌 삭제"):
                if accounts:
                    del_acc_label = st.selectbox("삭제할 계좌 선택", options=[f"[{a['account_type']}] {a['account_alias']} ({a['account_no']})" for a in accounts], key="del_acc_sel")
                    del_acc_idx = [f"[{a['account_type']}] {a['account_alias']} ({a['account_no']})" for a in accounts].index(del_acc_label)
                    target_del_acc = accounts[del_acc_idx]
                    
                    if st.button(f"🔴 '{target_del_acc['account_alias']}' 삭제", use_container_width=True):
                        success, msg = delete_account(target_del_acc['id'])
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                else:
                    st.info("삭제할 계좌가 없습니다.")

    # ---------------------------------------------------------
    # 2. 신규 자산 등록 및 삭제
    # ---------------------------------------------------------
    with col_mgmt2:
        st.markdown("### 📋 등록된 자산 목록")
        if assets:
            asset_df = pd.DataFrame([{
                "자산명": a['name'],
                "티커": a['ticker'],
                "시장": "🇰🇷 국내" if a['market'] == 'KR' else "🇺🇸 미국",
                "위험자산여부": "🔴 위험" if a['is_risk_asset'] else "🟢 안전"
            } for a in assets])
            st.dataframe(asset_df, use_container_width=True, hide_index=True)
        else:
            st.info("등록된 자산이 없습니다.")
            
        st.divider()

        col_ast1, col_ast2, col_ast3 = st.columns(3)

        with col_ast1:
            add_ast_k = st.session_state.get('add_ast_k', 0)
            with st.expander(f"➕ 신규 등록{' '*add_ast_k}"):
                is_gold_new = st.checkbox("KRX 실물 금 등록 (티커 불필요)", key=f"is_gold_new_{add_ast_k}")
                with st.form("add_asset_form_v2_inner", clear_on_submit=True):
                    na_name = st.text_input("자산명", value="KRX 금현물" if is_gold_new else "", placeholder="예: SCHD, 금현물 등")
                    na_ticker = st.text_input("종목코드/티커", value="없음" if is_gold_new else "", placeholder="예: 371460", disabled=is_gold_new)
                    na_market = st.selectbox("시장 구분", options=["KR", "US"], format_func=lambda x: "🇰🇷 국내" if x == "KR" else "🇺🇸 미국")
                    na_weight = st.number_input("목표 비중 (%)", min_value=0.0, max_value=100.0, value=10.0, step=1.0)
                    na_accs = st.multiselect("운용 가능 계좌 선택", options=list(account_options_by_id.keys()), format_func=lambda x: account_options_by_id[x])
                    na_is_risk = st.checkbox("위험자산으로 분류 (IRP 70% 제약 대상)", value=True)
                    na_notes = st.text_input("메모", placeholder="설명")
                    
                    if st.form_submit_button("등록하기", use_container_width=True):
                        if not na_name.strip():
                            st.error("자산명을 입력해 주세요.")
                        else:
                            final_ticker = "없음" if is_gold_new else na_ticker
                            success, msg = add_asset(na_name, final_ticker, na_market, na_weight, na_accs, na_is_risk, na_notes)
                            if success:
                                st.session_state.add_ast_k = add_ast_k + 1
                                st.success(msg)
                                st.session_state.price_data = None
                                st.rerun()
                            else:
                                st.error(msg)
                                
        with col_ast2:
            edit_ast_k = st.session_state.get('edit_ast_k', 0)
            with st.expander(f"✏️ 정보 수정{' '*edit_ast_k}"):
                if assets:
                    edit_asset_label = st.selectbox("수정할 자산 선택", options=[f"[{a['ticker']}] {a['name']}" for a in assets], key="edit_asset_sel")
                    edit_asset_idx = [f"[{a['ticker']}] {a['name']}" for a in assets].index(edit_asset_label)
                    target_edit_asset = assets[edit_asset_idx]
                    ast_id = target_edit_asset['id']
                    is_gold_edit = st.checkbox("KRX 실물 금 등록 (티커 불필요)", value=(target_edit_asset['ticker'] == '없음'), key=f"is_gold_edit_{ast_id}")
                    with st.form("edit_asset_form"):
                        e_a_name = st.text_input("자산명", value=target_edit_asset['name'], key=f"e_a_name_{ast_id}")
                        e_a_ticker = st.text_input("종목코드/티커", value="없음" if is_gold_edit else target_edit_asset['ticker'], placeholder="예: 371460", disabled=is_gold_edit, key=f"e_a_ticker_{ast_id}")
                        e_a_market = st.selectbox("시장 구분", options=["KR", "US"], index=0 if target_edit_asset['market'] == 'KR' else 1, format_func=lambda x: "🇰🇷 국내" if x == "KR" else "🇺🇸 미국", key=f"e_a_market_{ast_id}")
                        e_a_is_risk = st.checkbox("위험자산으로 분류", value=target_edit_asset['is_risk_asset'], key=f"e_a_is_risk_{ast_id}")
                        e_a_notes = st.text_input("메모", value=target_edit_asset['notes'] if target_edit_asset['notes'] else "", key=f"e_a_notes_{ast_id}")
                        
                        if st.form_submit_button("수정하기", use_container_width=True):
                            final_edit_ticker = "없음" if is_gold_edit else e_a_ticker
                            success, msg = update_asset(target_edit_asset['id'], e_a_name, final_edit_ticker, e_a_market, target_edit_asset['target_weight'], target_edit_asset['allowed_accounts'], e_a_is_risk, e_a_notes)
                            if success:
                                st.session_state.edit_ast_k = edit_ast_k + 1
                                st.success(msg)
                                st.session_state.price_data = None
                                st.rerun()
                            else:
                                st.error(msg)
                else:
                    st.info("수정할 자산이 없습니다.")

        with col_ast3:
            with st.expander("🗑️ 자산 삭제"):
                if assets:
                    del_asset_label = st.selectbox("삭제할 자산 선택", options=[f"[{a['ticker']}] {a['name']}" for a in assets], key="del_asset_sel")
                    del_asset_idx = [f"[{a['ticker']}] {a['name']}" for a in assets].index(del_asset_label)
                    target_del_asset = assets[del_asset_idx]
                    
                    if st.button(f"🔴 '{target_del_asset['name']}' 삭제", use_container_width=True):
                        success, msg = delete_asset(target_del_asset['id'])
                        if success:
                            st.success(msg)
                            st.session_state.price_data = None
                            st.rerun()
                        else:
                            st.error(msg)
                else:
                    st.info("삭제할 자산이 없습니다.")
