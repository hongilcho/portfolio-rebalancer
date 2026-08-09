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

def render_tab4():
    assets = get_all_assets()
    accounts = get_all_accounts()
    account_options_by_id = {str(a['id']): f"[{a['account_type']}] {a['account_alias']}" for a in accounts}
    
    price_map = {}
    if st.session_state.price_data:
        for item in st.session_state.price_data:
            price_map[str(item['id'])] = item['price_krw']
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

    import datetime
    KST = datetime.timezone(datetime.timedelta(hours=9))
    today_kst = datetime.datetime.now(KST).date()
    t_date = st.date_input("일괄 체결 일자", today_kst)
    
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
            
            from data.data_manager import get_holdings_by_account
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
            KST = datetime.timezone(datetime.timedelta(hours=9))
            today_kst = datetime.datetime.now(KST).date()
            
            default_start = max(min_date, today_kst - datetime.timedelta(days=90))
            date_range = st.date_input("조회 기간", value=(default_start, max(max_date, today_kst)))
            
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
