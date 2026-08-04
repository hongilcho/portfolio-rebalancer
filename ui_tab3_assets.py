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

def render_tab3():
    assets = get_all_assets()
    accounts = get_all_accounts()
    account_options_by_id = {str(a['id']): f"[{a['account_type']}] {a['account_alias']}" for a in accounts}
    
    price_map = {}
    if st.session_state.price_data:
        for item in st.session_state.price_data:
            price_map[str(item['id'])] = item['price_krw']
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
