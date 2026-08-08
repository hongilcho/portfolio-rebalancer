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

def render_tab5():
    assets = get_all_assets()
    accounts = get_all_accounts()
    account_options_by_id = {str(a['id']): f"[{a['account_type']}] {a['account_alias']}" for a in accounts}
    
    price_map = {}
    if st.session_state.price_data:
        for item in st.session_state.price_data:
            price_map[str(item['id'])] = item['price_krw']
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
