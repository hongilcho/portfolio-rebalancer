import streamlit as st
import pandas as pd
import datetime
from data_manager import (
    get_all_assets, get_all_accounts, get_holdings_by_account, get_all_holdings,
    save_account_holdings, add_account, update_account, delete_account,
    add_asset, update_asset, delete_asset, execute_trade, get_trade_history,
    delete_trade, update_account_settings, update_account_priorities, ACCOUNT_TYPES
)
from utils import num_to_kr_mixed, format_usd_label
from enums import Currency, AccountType, TradeType
from rebalance_calculator import calculate_rebalancing_plan

def render_tab1():
    assets = get_all_assets()
    accounts = get_all_accounts()
    account_options_by_id = {str(a['id']): f"[{a['account_type']}] {a['account_alias']}" for a in accounts}
    
    price_map = {}
    if st.session_state.price_data:
        for item in st.session_state.price_data:
            price_map[str(item['id'])] = item['price_krw']
    
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
                    "보유수량": f"{qty:,.0f} 주",
                    "손익": f"{profit_krw:+,.0f} 원 ({profit_pct:+.1f}%)",
                    "평가금액": f"{eval_val:,.0f} 원",
                    "평단가": f"{avg_p_krw:,.0f} 원",
                    "현재가": f"{curr_p:,.0f} 원",
                    "티커": h['ticker'],
                    "위험구분": "🔴 위험자산" if h['is_risk_asset'] else "🟢 안전자산"
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
                "종목명": data['name'],
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

        def style_profit_string(val):
            if isinstance(val, str):
                if val.startswith('+'):
                    return 'color: #ff6b6b; font-weight: 700; font-size: 15px;'
                elif val.startswith('-'):
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
            df_stock_info = df_stock[["종목명", "수량", "수익률(%)", "손익(원)", "평가금액(원)", "평단가(원)", "현재가(원)"]]
            
            # 합계 행 추가
            total_row_stock = pd.DataFrame([{
                "종목명": "총합계",
                "수량": "-",
                "수익률(%)": total_stock_return,
                "손익(원)": total_stock_profit,
                "평가금액(원)": total_stock_eval,
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
                    df_holdings = pd.DataFrame(summary['holdings'])
                    styled_holdings = df_holdings.style.map(style_profit_string, subset=["손익"])
                    st.dataframe(styled_holdings, use_container_width=True, hide_index=True)
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
