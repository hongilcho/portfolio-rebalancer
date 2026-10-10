"""Deterministic work instructions, never bank transfers or broker orders."""
from decimal import Decimal, ROUND_CEILING
import json
from logic.usd_cost import number, positive

PROTECTED = ('ISA','IRP','PENSION','연금','퇴직')
def can_transfer_out(account):
    return not any(label in str(account.get('account_type','')).upper() for label in PROTECTED)

def build_steps(plan, accounts, assets, setup, existing_quantities=None):
    accounts={str(a['id']):a for a in accounts}
    assets={str(a['id']):a for a in assets}
    main=setup['representative_account_id']
    if main not in accounts or not can_transfer_out(accounts[main]):
        raise ValueError('대표 자금 계좌는 출금 가능한 현재 포트폴리오 계좌로 선택해주세요.')
    fx=positive(setup['usd_krw'])
    incoming=number(setup['additional_cash_krw'])
    if incoming<0:raise ValueError('추가로 입금할 금액은 0 이상이어야 합니다.')
    grouped={}
    for i,line in enumerate(plan['trade_plan']):
        if line.get('execution_excluded'): continue
        if line['type']!='BUY':raise ValueError('첫 버전은 매수 중심 계획을 지원합니다. 매도가 포함되지 않은 계획을 선택해주세요.')
        account,asset=accounts.get(str(line['account_id'])),assets.get(str(line['asset_id']))
        if not account or not asset or asset.get('is_deposit'):
            raise ValueError('계획의 계좌·종목을 다시 확인해주세요.')
        allowed=asset.get('allowed_accounts') or []
        if isinstance(allowed,str):allowed=json.loads(allowed)
        if str(account['id']) not in map(str,allowed):raise ValueError('계좌에 허용되지 않은 계획 종목입니다.')
        qty=positive(line['qty']);price=positive(line['price'])
        filled=number((existing_quantities or {}).get(i,0))
        remaining=max(Decimal(0),qty-filled)
        group=grouped.setdefault(account['id'],{'krw':Decimal(0),'usd':Decimal(0),'lines':[]})
        currency='USD' if asset['market']=='US' else 'KRW'
        unit_price=price/fx if currency=='USD' else price  # saved calculator prices are KRW
        group['usd' if currency=='USD' else 'krw']+=remaining*unit_price
        group['lines'].append(dict(key=f'trade:{i}',kind='BUY',line_no=i,account_id=account['id'],
            account_alias=account['account_alias'],asset_id=asset['id'],asset_name=asset['name'],currency=currency,
            title=f"{asset['name']} 매수",target_quantity=str(qty),estimated_price=str(unit_price),depends_on=[]))
    limits=setup.get('source_limits') or {}
    if any(aid not in accounts or not can_transfer_out(accounts[aid]) or number(amount)<0 for aid,amount in limits.items()):
        raise ValueError('이체 출금 계좌와 사용할 현금 범위를 확인해주세요. 절세계좌는 출금하지 않습니다.')
    steps=[];needed={};fx_steps={}
    fund_key=None
    if incoming>0:
        fund_key='fund';steps.append(dict(key=fund_key,kind='DEPOSIT',account_id=main,account_alias=accounts[main]['account_alias'],
            currency='KRW',target_amount=str(incoming),title='대표 계좌에 투자금 준비',depends_on=[]))
    for aid,g in grouped.items():
        usd_short=max(Decimal(0),g['usd']-max(Decimal(0),number(accounts[aid].get('deposit_usd') or 0)))
        usd_short=usd_short.quantize(Decimal('0.01'),rounding=ROUND_CEILING)
        fx_krw=(usd_short*fx).quantize(Decimal('1'),rounding=ROUND_CEILING)
        g['required_krw']=g['krw']+fx_krw
        needed[aid]=max(Decimal(0),g['required_krw']-max(Decimal(0),number(accounts[aid].get('deposit_krw') or 0)))
        if aid==main:needed[aid]=max(Decimal(0),needed[aid]-incoming)
        if usd_short>0:
            fx_steps[aid]=dict(key=f'fx:{aid}',kind='EXCHANGE_IN',account_id=aid,account_alias=accounts[aid]['account_alias'],
                currency='USD',target_amount=str(usd_short),estimated_krw=str(fx_krw),title='달러 환전',depends_on=[])
    pools={}
    for aid,acc in accounts.items():
        if not can_transfer_out(acc) or (aid!=main and aid not in limits):continue
        cash=max(Decimal(0),number(acc.get('deposit_krw') or 0))
        cap=min(cash,number(limits[aid])) if aid in limits else cash
        own=grouped.get(aid,{}).get('required_krw',Decimal(0))
        pools[aid]=max(Decimal(0),cap+(incoming if aid==main else 0)-own)
    transfer_keys={aid:[] for aid in grouped}
    for dest,amount in needed.items():
        for source in sorted(pools,key=lambda aid:aid!=main):
            if source==dest or amount<=0:continue
            take=min(amount,pools[source])
            if take<=0:continue
            key=f'transfer:{source}:{dest}'
            steps.append(dict(key=key,kind='TRANSFER',account_id=source,account_alias=accounts[source]['account_alias'],
                destination_account_id=dest,destination_alias=accounts[dest]['account_alias'],currency='KRW',target_amount=str(take),
                title=f"{accounts[dest]['account_alias']}로 자금 이동",depends_on=[fund_key] if source==main and fund_key else []))
            transfer_keys[dest].append(key);pools[source]-=take;amount-=take
        if amount>Decimal('0.000001'):
            raise ValueError(f"{accounts[dest]['account_alias']}의 매수·환전 자금이 {amount:,.0f}원 부족합니다. 추가 입금액 또는 사용할 출금 계좌를 확인하거나 계획을 다시 계산해주세요.")
    for aid,g in grouped.items():
        deps=transfer_keys[aid] or ([fund_key] if aid==main and fund_key else [])
        if aid in fx_steps:
            fx_steps[aid]['depends_on']=deps;steps.append(fx_steps[aid])
        for line in g['lines']:
            line['depends_on']=[fx_steps[aid]['key']] if line['currency']=='USD' and aid in fx_steps else deps
            steps.append(line)
    return steps
