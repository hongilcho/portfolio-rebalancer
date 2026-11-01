"""
포트폴리오 리밸런싱 계산 엔진 (Rebalance Calculator)
=====================================================
사용자가 설정한 목표 비중(Target Weight)과 현재 자산 평가액을 비교하여,
최적의 매매 계획(Trade Plan)과 계좌 간 현금 이체 계획(Transfer Plan)을 도출합니다.

주요 특징 및 제약조건:
1. 3가지 리밸런싱 시나리오:
   - NEW_CASH: 신규 자금 투입 시 매도 없이 매수만으로 목표 비중에 최대한 근접
   - DRIFT: 현재 비중과 목표 비중 간 괴리율이 임계치(기본 5%)를 초과한 자산이 있을 때만 트리거
   - PERIODIC: 정기 리밸런싱 (비중 초과분 매도 후 부족분 매수)
2. 절세 계좌 우선순위 매칭:
   - 매수: 사용자 지정 우선순위(priority 낮은 번호 우선: 예: 연금/ISA 우선 매수)
   - 매도: 일반과세 계좌 -> 절세 계좌 순 역순 매도 (비과세/과세이연 혜택 보호)
3. 연금 규정 및 특수 자산 보호:
   - IRP 계좌 위험자산(주식형 등) 비중 70% 한도 자동 검증 및 초과 매수 방지
   - 정기예금 등 매도 잠금(`lock_rebalance_sell=True`) 자산 매도 제외
4. 계좌 간 자금 이동 최적화:
   - 매매 체결 후 각 계좌의 예수금 과부족을 정밀 계산하여 이체 지시서(`transfer_plan`) 생성
"""

import copy
from logic.rebalance_steps import (
    allocate_buys,
    build_targets,
    index_rebalance_inputs,
    plan_sales,
    plan_transfers,
    prepare_funding,
    project_assets,
)
from typing import List, Dict, Tuple

def calculate_rebalancing_plan(
    assets: List[dict],
    portfolio_assets: Dict[str, dict], # aggregated current holdings by asset id
    accounts: List[dict],
    holdings: List[dict], # raw holdings to know exact qty per account
    price_map: Dict[str, float],
    total_krw_cash: float,
    usd_krw_rate: float,
    scenario: str, # "NEW_CASH", "DRIFT", "PERIODIC"
    new_cash_krw: float = 0.0,
    drift_threshold: float = 5.0
) -> Tuple[List[dict], List[dict], List[dict], bool, str]:
    """
    포트폴리오 리밸런싱 알고리즘을 수행하여 최적의 매매 및 현금 이체 계획을 산출합니다.

    Args:
        assets (List[dict]): 자산 마스터 목록 (목표비중, 허용계좌, 위험자산여부, 매도잠금여부 등)
        portfolio_assets (Dict[str, dict]): 자산 ID별 현재 보유수량 및 원화 평가금액 집계
        accounts (List[dict]): 계좌 마스터 목록 (우선순위, 계좌유형, 보유예수금, 납입한도 등)
        holdings (List[dict]): 계좌별 실제 보유 종목 및 수량, 평균단가 목록
        price_map (Dict[str, float]): 자산 ID별 원화 실시간 시세 매핑
        total_krw_cash (float): 포트폴리오 내 모든 계좌의 원화 환산 현금 총액
        usd_krw_rate (float): 달러-원 기준 환율
        scenario (str): 리밸런싱 시나리오 ("NEW_CASH", "DRIFT", "PERIODIC")
        new_cash_krw (float): 신규 투입 현금 (NEW_CASH 시나리오 시 필수)
        drift_threshold (float): 허용 괴리율 임계치 (%) (DRIFT 시나리오 시 기준값)

    Returns:
        Tuple[List[dict], List[dict], List[dict], bool, str]:
            - trade_plan: 계좌별 매매 계획 리스트 (계좌, 종목, 매수/매도, 수량, 단가, 예상손익 등)
            - transfer_plan: 계좌 간 현금 입출금 이체 지시서 리스트
            - simulated_assets: 리밸런싱 완료 후 자산별 예상 비중 및 평가액 시뮬레이션
            - success: 리밸런싱 계산 성공 여부 (bool)
            - msg: 상태 및 안내 메시지 (str)
    """
    # Normalize price_map keys to string to prevent lookup failures
    price_map = {str(k): float(v) for k, v in price_map.items()}

    # 1. Total Current Value
    rebalance_assets = [a for a in assets if a.get('include_in_rebalance', True)]
    rebalance_asset_ids = {str(a['id']) for a in rebalance_assets}
    
    rebalance_asset_krw = sum(d['eval_amt_krw'] for aid, d in portfolio_assets.items() if str(aid) in rebalance_asset_ids)
    total_cash_krw = total_krw_cash + new_cash_krw
    
    total_rebalance_portfolio_krw = rebalance_asset_krw + total_cash_krw
    if total_rebalance_portfolio_krw <= 0:
        return [], [], [], False, "리밸런싱 대상 포트폴리오 총액이 0원입니다."

    inputs = index_rebalance_inputs(assets, accounts, holdings)

    # Sort accounts by user priority (lowest number = highest priority)
    # Default to 99 if not set.
    sorted_accounts = copy.deepcopy(sorted(accounts, key=lambda x: int(x.get('priority', 99))))
    
    # 2. Check Drift Condition (if scenario == "DRIFT")
    if scenario == "DRIFT":
        needs_rebalance = False
        for aid in rebalance_asset_ids:
            data = portfolio_assets.get(aid, {'eval_amt_krw': 0.0})
            current_w = (data['eval_amt_krw'] / rebalance_asset_krw * 100) if rebalance_asset_krw > 0 else 0
            # We match with asset target
            target_w = (inputs.assets[aid]['target_weight'] if aid in inputs.assets else 0)
            if abs(current_w - target_w) >= drift_threshold:
                needs_rebalance = True
                break
        if not needs_rebalance:
            return [], [], [], True, "모든 자산이 허용 괴리율 이내에 있어 리밸런싱이 필요하지 않습니다."

    targets = build_targets(
        assets, portfolio_assets, price_map, total_rebalance_portfolio_krw, scenario
    )
    trade_plan = plan_sales(targets, sorted_accounts, inputs)
    funding = prepare_funding(
        accounts, sorted_accounts, holdings, trade_plan, new_cash_krw, scenario,
        usd_krw_rate, inputs,
    )
    allocate_buys(
        targets, sorted_accounts, trade_plan, funding,
        total_rebalance_portfolio_krw, scenario, inputs,
    )
    transfer_plan = plan_transfers(accounts, trade_plan, new_cash_krw, inputs)
    simulated = project_assets(assets, portfolio_assets, trade_plan)
    return trade_plan, transfer_plan, simulated, True, "리밸런싱 계산 완료"



def compute_realized_summary(trade_plan: List[dict]) -> dict:
    """
    리밸런싱 매도 계획(SELL)에 대한 예상 실현 손익 집계를 산출합니다.

    Args:
        trade_plan (List[dict]): 리밸런싱 매매 계획 목록

    Returns:
        dict: 매도 존재 여부, 매도 종목 수, 총 매도대금, 총 매입원가, 총 실현손익금, 총 수익률(%)
    """
    sell_trades = [t for t in trade_plan if t.get('type') == 'SELL']
    total_sell_amount = sum(float(t.get('total_krw', 0.0)) for t in sell_trades)
    total_cost_basis = sum(float(t.get('cost_basis_krw', 0.0)) for t in sell_trades)
    total_realized_profit = sum(float(t.get('realized_profit_krw', 0.0)) for t in sell_trades)
    total_realized_return_pct = ((total_realized_profit / total_cost_basis) * 100.0) if total_cost_basis > 0 else 0.0
    return {
        "has_sell": len(sell_trades) > 0,
        "sell_count": len(sell_trades),
        "total_sell_amount": total_sell_amount,
        "total_cost_basis": total_cost_basis,
        "total_realized_profit": total_realized_profit,
        "total_realized_return_pct": total_realized_return_pct
    }

