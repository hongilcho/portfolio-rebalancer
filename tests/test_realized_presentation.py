from copy import deepcopy
from logic.realized_presentation import recent_sales


def test_recent_sales_reuses_calculated_amounts_and_keeps_unknown_basis():
    report={'sales':[dict(trade_id='sale',trade_date='2026-11-06',account_id='a',asset_id='mmf',quantity=94,status='COSTS_PENDING',gross_profit_krw=39950,net_profit_krw=None,estimated_net_profit_krw=39800),dict(trade_id='unknown',trade_date='2026-11-05',account_id='a',asset_id='other',quantity=1,status='BASIS_PENDING',gross_profit_krw=None)]}
    original=deepcopy(report)
    result=recent_sales(report,[{'id':'a','account_alias':'QA','account_no':'not-for-display'}],[{'id':'mmf','name':'QA MMF'}])
    assert report==original
    assert result[0]['gross_profit_krw']==39950 and result[0]['estimated_net_profit_krw']==39800
    assert result[0]['net_profit_krw'] is None and result[1]['gross_profit_krw'] is None
    assert result[0]['asset_name']=='QA MMF' and result[0]['account_alias']=='QA'
    assert 'account_no' not in result[0]


def test_recent_sale_metadata_is_bounded_and_does_not_fabricate_empty_records():
    assert recent_sales({'sales':[]},[],[])==[]
    rows=[dict(trade_id=str(i),account_id='a',asset_id='s') for i in range(5)]
    assert [r['trade_id'] for r in recent_sales({'sales':rows},[],[])]==['0','1','2']
