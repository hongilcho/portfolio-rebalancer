"""Current NAV from existing cached prices, without dividend collection."""
import math


def current_nav(batch, price_map, fx):
    if not math.isfinite(fx) or fx<=0:
        raise ValueError('유효한 환율이 필요합니다.')
    value=sum(float(a.get('deposit_krw') or 0)+float(a.get('deposit_usd') or 0)*fx for a in batch['accounts'])
    deposits={a['id']:a for a in batch['assets'] if a.get('is_deposit') and float(a.get('deposit_principal') or 0)>0}
    positions={}
    for h in batch['holdings']:
        aid=h['asset_id']
        if aid in deposits or h.get('is_deposit'): continue
        quantity=float(h['quantity'])
        if quantity>0: positions[aid]=positions.get(aid,0)+quantity
    # Match existing NAV: pure deposit master assets are valued once.
    positions.update({aid:1 for aid in deposits})
    for aid,quantity in positions.items():
        price=float(price_map.get(aid) or 0)
        if not math.isfinite(price) or price<=0:
            raise ValueError('보유자산의 유효한 시세가 누락되어 평가액을 저장할 수 없습니다.')
        value+=quantity*price
    if not math.isfinite(value) or value<0:
        raise ValueError('평가액과 잔고를 확인해주세요.')
    return value
