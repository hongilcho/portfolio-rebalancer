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
