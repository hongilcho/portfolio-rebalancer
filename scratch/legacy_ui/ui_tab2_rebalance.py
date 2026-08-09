import streamlit as st
import pandas as pd
import datetime
from data.data_manager import (
    get_all_assets, get_all_accounts, get_holdings_by_account, get_all_holdings,
    save_account_holdings, add_account, update_account, delete_account,
    add_asset, update_asset, delete_asset, execute_trade, get_trade_history,
    delete_trade, update_account_settings, update_account_priorities, ACCOUNT_TYPES
)
from ui.utils import num_to_kr_mixed, format_usd_label
from data.enums import Currency, AccountType, TradeType
from logic.rebalance_calculator import calculate_rebalancing_plan

def render_tab2():
    assets = get_all_assets()
    accounts = get_all_accounts()
    account_options_by_id = {str(a['id']): f"[{a['account_type']}] {a['account_alias']}" for a in accounts}
    
    price_map = {}
    if st.session_state.price_data:
        for item in st.session_state.price_data:
            price_map[str(item['id'])] = item['price_krw']
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
