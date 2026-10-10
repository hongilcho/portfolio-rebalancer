"""Funding instructions and API boundaries, no credentials or external IO."""
from copy import deepcopy
import pytest
from pydantic import ValidationError
from logic.investment_execution import build_steps,can_transfer_out
from backend.routers.investments import Setup
from backend.execution_models import ExecutionLink
from data.repositories.bookkeeping import plain

@pytest.fixture
def inputs():
    accounts=[dict(id='cma',account_alias='CMA',account_type='CMA',deposit_krw=1150000,deposit_usd=0),
      dict(id='isa',account_alias='ISA',account_type='ISA',deposit_krw=0,deposit_usd=0),
      dict(id='us',account_alias='US',account_type='GENERAL',deposit_krw=0,deposit_usd=100)]
    assets=[dict(id='bond',name='bond',market='KR',allowed_accounts=['isa']),dict(id='vt',name='VT',market='US',allowed_accounts=['us'])]
    plan={'trade_plan':[dict(account_id='isa',asset_id='bond',type='BUY',qty=20,price=9000),
      dict(account_id='us',asset_id='vt',type='BUY',qty=5,price=140000)]}
    setup=dict(representative_account_id='cma',additional_cash_krw=0,usd_krw=1400,source_limits={})
    return plan,accounts,assets,setup

def test_existing_cma_and_usd_need_no_fake_contribution(inputs):
    steps=build_steps(*inputs)
    assert not any(s['kind']=='DEPOSIT' for s in steps)
    exchange=next(s for s in steps if s['kind']=='EXCHANGE_IN')
    assert float(exchange['target_amount'])==400
    assert float(exchange['estimated_krw'])==560000
    transfers=[s for s in steps if s['kind']=='TRANSFER']
    assert sum(float(s['target_amount']) for s in transfers)==740000
    buy=next(s for s in steps if s.get('asset_id')=='vt')
    assert buy['depends_on']==[exchange['key']]
    assert float(buy['estimated_price'])==100

def test_future_deposit_and_existing_deposit_are_distinct(inputs):
    plan,accounts,assets,setup=deepcopy(inputs)
    accounts[0]['deposit_krw']=0
    setup['additional_cash_krw']=740000
    steps=build_steps(plan,accounts,assets,setup)
    assert steps[0]['kind']=='DEPOSIT'
    assert float(steps[0]['target_amount'])==740000
    assert all('fund' in s['depends_on'] for s in steps if s['kind']=='TRANSFER')

def test_insufficient_cash_has_account_and_resolution_in_message(inputs):
    plan,accounts,assets,setup=deepcopy(inputs);accounts[0]['deposit_krw']=100
    with pytest.raises(ValueError,match='추가 입금액'):
        build_steps(plan,accounts,assets,setup)

@pytest.mark.parametrize('kind',['ISA','IRP','연금저축계좌','PENSION','퇴직연금'])
def test_tax_accounts_never_supply_transfer_cash(inputs,kind):
    plan,accounts,assets,setup=deepcopy(inputs);accounts[0]['account_type']=kind
    assert not can_transfer_out(accounts[0])
    with pytest.raises(ValueError,match='대표 자금 계좌'):
        build_steps(plan,accounts,assets,setup)
    setup['representative_account_id']='us';setup['source_limits']={'cma':100}
    with pytest.raises(ValueError,match='절세계좌'):
        build_steps(plan,accounts,assets,setup)

def test_partially_linked_trades_only_require_remaining_purchase_cash(inputs):
    plan,accounts,assets,setup=inputs
    steps=build_steps(plan,accounts,assets,setup,{0:10,1:3})
    assert sum(float(s['target_amount']) for s in steps if s['kind']=='TRANSFER')==230000
    assert float(next(s for s in steps if s.get('asset_id')=='vt')['target_quantity'])==5

def test_optional_link_metadata_preserves_old_retry_payload():
    assert plain({'execution':None,'trades':[{'execution':None,'exchange_rate':None}]})=={'trades':[{'exchange_rate':None}]}
    link=ExecutionLink(cycle_id='cycle',step_id='step',revision=1).model_dump()
    assert plain({'execution':link})['execution']==link

def test_setup_rejects_nonfinite_fx_and_link_rejects_missing_revision():
    base=dict(request_id='qa-start-01',plan_id='plan',representative_account_id='cma',usd_krw=1400)
    assert Setup(**base).additional_cash_krw==0
    with pytest.raises(ValidationError):Setup(**{**base,'usd_krw':float('nan')})
    with pytest.raises(ValidationError):ExecutionLink(cycle_id='cycle',step_id='step',revision=0)

def test_preview_token_changes_with_action_but_is_stable_for_key_order():
    from data.repositories.investments import preview_token
    assert preview_token([{'kind':'BUY','qty':2}])==preview_token([{'qty':2,'kind':'BUY'}])
    assert preview_token([{'qty':2}])!=preview_token([{'qty':3}])

def test_revision_model_bounds():
    from backend.routers.investments import Revision
    change=dict(step_id='task',target=2)
    base=dict(request_id='qa-change-01',revision=1,reason='smaller budget',changes=[change])
    assert Revision(**base).changes[0].status=='ACTIVE'
    for invalid in ({**base,'reason':''},{**base,'revision':0},
                    {**base,'changes':[]},{**base,'changes':[{**change,'target':float('nan')}]}):
        with pytest.raises(ValidationError): Revision(**invalid)

def test_excluded_buy_keeps_original_line_numbers(inputs):
    plan,accounts,assets,setup=deepcopy(inputs)
    plan['trade_plan'][0]['execution_excluded']=True
    steps=build_steps(plan,accounts,assets,setup)
    assert not any(s.get('asset_id')=='bond' for s in steps)
    assert next(s for s in steps if s.get('asset_id')=='vt')['line_no']==1

def test_execution_schema_does_not_extend_legacy_public_security_inventory():
    from data.investment_schema import TABLES
    from data.security_schema import APP_TABLES
    assert len(TABLES)==5 and len(APP_TABLES)==20
    assert not set(TABLES)&set(APP_TABLES)


def test_browser_cannot_supply_internal_confirmation_metadata():
    with pytest.raises(ValidationError):
        ExecutionLink(cycle_id="cycle",step_id="step",revision=1,confirmation_id="forged")


def test_closing_progress_uses_only_valid_posted_facts():
    from logic.investment_execution import closing_progress
    step = dict(id='buy', kind='BUY', account_id='isa', asset_id='bond',
        currency='KRW', target_quantity='20', title='Bond purchase')
    def fill(ident, quantity, **extra):
        return dict(id=ident, step_id='buy', kind='BUY', account_id='isa',
            asset_id='bond', currency='KRW', quantity=quantity,
            ledger_status='RECORDED', **extra)
    cycle = dict(steps=[step], results=[fill('a',7), fill('a',7),
        fill('b',13,voided=True), {**fill('c',20),'account_id':'other'}])
    progress = closing_progress(cycle)
    assert progress['remaining_steps'][0]['recorded']=='7'
    assert progress['remaining_steps'][0]['remaining']=='13'
    cycle['results'].append(fill('d',13))
    assert closing_progress(cycle)['remaining_steps']==[]
    cycle['results'].append({**fill('e',1),'ledger_status':'UNCERTAIN'})
    assert closing_progress(cycle)['remaining_steps'][0]['review_required']


@pytest.mark.parametrize('target', [0,None,float('nan'),''])
def test_invalid_target_cannot_close_as_completed(target):
    from logic.investment_execution import closing_progress
    progress=closing_progress(dict(steps=[dict(id='s',kind='DEPOSIT',
        account_id='cma',currency='KRW',target_amount=target)],results=[]))
    assert progress['remaining_steps'][0]['review_required']


def test_excluded_and_existing_cash_are_distinct_in_closing_report():
    from logic.investment_execution import closing_progress
    base=dict(kind='TRANSFER',account_id='cma',currency='KRW',target_amount=100)
    progress=closing_progress(dict(steps=[dict(base,id='excluded',status='EXCLUDED'),
        dict(base,id='cash',satisfied_by_existing_cash=True)],results=[]))
    assert progress==dict(remaining_steps=[],excluded_step_ids=['excluded'])


def test_multiple_us_assets_share_one_conversion_and_preserve_existing_cash(inputs):
    plan,accounts,assets,setup=deepcopy(inputs)
    assets.append(dict(id='pdbc',name='PDBC',market='US',allowed_accounts=['us']))
    plan['trade_plan'].append(dict(account_id='us',asset_id='pdbc',type='BUY',qty=10,price=14000))
    steps=build_steps(plan,accounts,assets,setup)
    conversions=[s for s in steps if s['kind']=='EXCHANGE_IN']
    assert len(conversions)==1 and float(conversions[0]['target_amount'])==500
    buys=[s for s in steps if s['kind']=='BUY' and s['currency']=='USD']
    assert len(buys)==2 and all(s['depends_on']==[conversions[0]['key']] for s in buys)
    assert float(next(s for s in steps if s['key']=='transfer:cma:us')['target_amount'])==700000


def test_start_review_detects_cash_changes_even_when_instructions_are_identical():
    from data.repositories.investments import preview_token
    steps=[{'kind':'TRANSFER','target_amount':'180000'}]
    before={'accounts':[{'id':'cma','deposit_krw':1150000,'deposit_usd':0}]}
    after={'accounts':[{'id':'cma','deposit_krw':1150001,'deposit_usd':0}]}
    assert preview_token(steps,before)!=preview_token(steps,after)


def test_domestic_buffer_deducts_existing_cash_without_raising_buy_quantity(inputs):
    plan,accounts,assets,setup=deepcopy(inputs)
    plan['trade_plan']=plan['trade_plan'][:1];plan['trade_plan'][0].update(qty=80,price=10000)
    accounts[1]['deposit_krw']=200000;setup['price_buffer_percent']=1
    steps=build_steps(plan,accounts,assets,setup)
    assert float(next(s for s in steps if s['kind']=='TRANSFER')['target_amount'])==608000
    assert float(next(s for s in steps if s['kind']=='BUY')['target_quantity'])==80

def test_us_price_and_fx_buffers_deduct_existing_dollars_separately(inputs):
    plan,accounts,assets,setup=deepcopy(inputs);setup.update(price_buffer_percent=1,fx_buffer_percent=1)
    steps=build_steps(plan,accounts,assets,setup)
    exchange=next(s for s in steps if s['kind']=='EXCHANGE_IN')
    assert float(exchange['target_amount'])==405
    assert float(exchange['estimated_krw'])==572670
    assert float(next(s for s in steps if s['kind']=='BUY' and s['currency']=='USD')['target_quantity'])==5
    accounts[2]['deposit_usd']=1000
    steps=build_steps(plan,accounts,assets,setup)
    assert not any(s['kind']=='EXCHANGE_IN' for s in steps)

def test_buffer_bounds_and_legacy_setup_remain_compatible(inputs):
    plan,accounts,assets,setup=inputs
    for value in (-1,21,float('nan'),float('inf')):
        with pytest.raises(ValueError):build_steps(plan,accounts,assets,{**setup,'price_buffer_percent':value})
    assert plain(Setup(request_id='legacy-request',plan_id='p',representative_account_id='cma',usd_krw=1400).model_dump()).get('price_buffer_percent') is None

def test_cash_return_plan_only_allows_current_same_scope_unprotected_krw(inputs):
    from logic.investment_execution import build_return_steps
    _,accounts,_,_=deepcopy(inputs)
    accounts[2]['deposit_krw']=10000
    plan=dict(plan_type='CASH_RETURN',destination_account_id='cma',return_plan=[dict(account_id='us',amount_krw='9000')])
    steps=build_return_steps(plan,accounts)
    assert steps[0]['kind']=='TRANSFER' and steps[0]['currency']=='KRW' and float(steps[0]['target_amount'])==9000
    assert accounts[2]['deposit_krw']==10000
    for changes in ({'account_id':'isa','amount_krw':'1'},{'account_id':'other','amount_krw':'1'},{'account_id':'us','amount_krw':'11000'},{'account_id':'us','amount_krw':'1.5'}):
        with pytest.raises(ValueError):build_return_steps({**plan,'return_plan':[changes]},accounts)
