"""
증권사 계좌 실시간 동기화 API 라우터 (Sync Router)
===================================================
NH투자증권(나무증권) Open API를 호출하여 등록된 위탁/금현물 계좌의
예수금 및 보유 종목 잔고를 데이터베이스에 일괄 동기화합니다.
"""

from fastapi import APIRouter
from backend.services import market_service
from data.data_manager import get_all_accounts, sync_account_with_api
from data.nh_api import nh_api_client

router = APIRouter(prefix="/api/sync", tags=["sync"])

@router.post("/namuh")
def sync_namuh_accounts():
    """
    NH투자증권 Open API를 통해 연동 가능한 위탁/금현물 계좌의 잔고를 동기화하고
    시세 캐시를 초기화(Invalidate)합니다.
    (API 연동을 지원하지 않는 ISA, IRP, 연금저축계좌는 스킵)
    """
    accounts = get_all_accounts()
    skip_types = ['ISA', 'IRP', '연금저축계좌']
    
    synced_accounts = []
    errors = []
    
    for acc in accounts:
        acc_no = acc.get('account_no', '').strip()
        acc_type = acc.get('account_type', '')
        acc_alias = acc.get('account_alias', '')
        
        if not acc_no or acc_type in skip_types:
            continue
            
        if acc_type == '금현물':
            api_data, err_msg = nh_api_client.fetch_gold_account_balance(acc_no)
        else:
            api_data, err_msg = nh_api_client.fetch_full_account_balance(acc_no)
            
        if api_data:
            success, msg = sync_account_with_api(acc['id'], api_data)
            if success:
                synced_accounts.append(acc_alias)
            else:
                errors.append(f"[{acc_alias}] {msg}")
        else:
            errors.append(f"[{acc_alias}] API 오류: {err_msg or '잔고 조회 실패'}")
            
    market_service.invalidate_price_cache()
    
    return {
        "success": len(synced_accounts) > 0 or not errors,
        "synced_count": len(synced_accounts),
        "synced_accounts": synced_accounts,
        "errors": errors,
        "message": f"{len(synced_accounts)}개 계좌 동기화 완료" if not errors else f"{len(synced_accounts)}개 완료, {len(errors)}개 실패"
    }
