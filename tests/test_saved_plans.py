import pytest
from backend.routers.plans import Plan
from data.repositories.plans import validate_lines


def test_scope_and_quantity_validation():
    row={'account_id':'a','asset_id':'s','type':'BUY','qty':2}
    validate_lines([row], {'a'}, {'s'})
    for invalid in ({**row,'account_id':'other'}, {**row,'qty':float('nan')}, {**row,'type':'INIT'}):
        with pytest.raises(ValueError):
            validate_lines([invalid], {'a'}, {'s'})


def test_api_never_accepts_nonfinite_plan_or_unknown_direction():
    from pydantic import ValidationError
    payload={'name':'plan','scenario':'NEW_CASH','new_cash_krw':0,'drift_threshold':5,
             'trade_plan':[{'account_id':'a','asset_id':'s','type':'BUY','qty':1,'price':10,'total_krw':10}]}
    assert Plan(**payload).trade_plan[0].qty==1
    for bad in ('INIT','EXCHANGE'):
        with pytest.raises(ValidationError):
            Plan(**{**payload,'trade_plan':[{**payload['trade_plan'][0],'type':bad}]})
