from datetime import date
import pytest
from logic.period_performance import money_weighted_return, report_periods, report_daily
from backend.performance_valuation import current_nav

START=date(2026,1,1)
END=date(2026,12,31)


def flow(day,amount,voided=False):
    return {'event_date':day,'amount_krw':amount,'voided':voided}


def test_return_is_period_growth_without_annualization():
    rate,warning=money_weighted_return(START,date(2026,2,1),100,110,[])
    assert rate==pytest.approx(10)
    assert not warning


def test_deposit_and_withdrawals_are_never_investment_profit():
    assert money_weighted_return(START,END,100,200,[flow(date(2026,7,1),100)])[0]==0.0
    assert money_weighted_return(START,END,100,60,[flow(date(2026,7,1),-40)])[0]==pytest.approx(0,abs=1e-7)


def test_known_dated_contribution_growth_solution():
    middle=date(2026,7,1)
    fraction=(END-middle).days/(END-START).days
    terminal=100*1.1+100*1.1**fraction
    assert money_weighted_return(START,END,100,terminal,[flow(middle,100)])[0]==pytest.approx(10)


def test_negative_zero_and_ambiguous_return_have_explicit_results():
    assert money_weighted_return(START,END,100,80,[])[0]==pytest.approx(-20)
    assert money_weighted_return(START,END,100,0,[])[0]==-100
    assert money_weighted_return(START,START,100,110,[])[0] is None
    assert money_weighted_return(START,END,0,110,[])[0] is None
    assert money_weighted_return(START,END,100,100,[flow(date(2026,3,1),-300),flow(date(2026,6,1),300)])[0] is None


def tracking(day=START):
    return {'baseline_date':day,'baseline_value':100,'revision':1,'confirmed_revision':1,'confirmed_through':END}


def test_reports_require_boundary_dates_but_not_flow_confirmation():
    snaps=[{'snapshot_date':START,'value_krw':100},{'snapshot_date':date(2026,2,28),'value_krw':150}]
    reports=report_periods(tracking(),snaps,[])
    jan=next(r for r in reports if r['label']=='2026-01')
    feb=next(r for r in reports if r['label']=='2026-02')
    assert jan['return_pct'] is None and '2026-01-31' in jan['warning']
    assert feb['return_pct'] is None and feb['start_value'] is None
    year=next(r for r in reports if r['kind']=='연')
    assert year['return_pct']==pytest.approx(50) and year['end']==date(2026,2,28)
    assert report_periods({**tracking(),'confirmed_revision':0},snaps,[])[-1]['return_pct']==pytest.approx(50)


def test_baseline_on_month_last_day_does_not_duplicate_same_day_flows():
    base=date(2026,1,31)
    snaps=[{'snapshot_date':base,'value_krw':200},{'snapshot_date':date(2026,2,28),'value_krw':200}]
    reports=report_periods(tracking(base),snaps,[flow(base,100)])
    feb=next(r for r in reports if r['label']=='2026-02')
    assert feb['start_value']==200 and feb['net_flow']==0 and feb['return_pct']==pytest.approx(0,abs=1e-7)
    assert reports[-1]['profit']==0


def test_voided_flows_are_excluded_without_requiring_manual_confirmation():
    snaps=[{'snapshot_date':date(2026,1,31),'value_krw':110}]
    row=report_periods(tracking(),snaps,[flow(date(2026,1,15),100,True)])[0]
    assert row['profit']==10 and row['return_pct']==pytest.approx(10)
    row=report_periods({**tracking(),'confirmed_through':None},snaps,[])[0]
    assert row['profit']==10 and row['return_pct']==pytest.approx(10) and not row['warning']
    assert row['flow_count']==0


def test_nav_includes_actual_cash_and_pure_deposits_once_and_no_dividend_topup():
    batch={'accounts':[{'deposit_krw':100,'deposit_usd':2}],
           'assets':[{'id':'dep','is_deposit':True,'deposit_principal':1000}],
           'holdings':[{'asset_id':'stock','quantity':3,'dividend_profit':999}, {'asset_id':'dep','quantity':1,'is_deposit':True}]}
    assert current_nav(batch,{'stock':10,'dep':1010},1400)==3940
    with pytest.raises(ValueError): current_nav(batch,{'dep':1010},1400)
    with pytest.raises(ValueError): current_nav(batch,{'stock':float('nan'),'dep':1010},1400)
    with pytest.raises(ValueError): current_nav(batch,{},0)


def test_daily_points_are_baseline_cumulative_not_one_day_returns():
    snapshots = [{'snapshot_date': date(2026, 1, 3), 'value_krw': 121},
                 {'snapshot_date': START, 'value_krw': 100},
                 {'snapshot_date': date(2026, 1, 2), 'value_krw': 110}]
    rows = report_daily(tracking(), snapshots, [])
    assert [r['label'] for r in rows] == ['2026-01-01', '2026-01-02', '2026-01-03']
    assert [r['return_pct'] for r in rows] == pytest.approx([0, 10, 21])
    assert [r['profit'] for r in rows] == [0, 10, 21]
    assert all(r['start'] == START and r['value_krw'] == r['end_value'] for r in rows)


def test_daily_flows_change_valuation_but_do_not_become_profit():
    snapshots = [{'snapshot_date': date(2026, 1, 2), 'value_krw': 200},
                 {'snapshot_date': date(2026, 1, 3), 'value_krw': 160}]
    flows = [flow(date(2026, 1, 2), 100), flow(date(2026, 1, 3), -40),
             flow(date(2026, 1, 3), 999, True), flow(date(2026, 1, 4), 500)]
    rows = report_daily(tracking(), snapshots, flows)
    assert [r['net_flow'] for r in rows] == [100, 60]
    assert [r['profit'] for r in rows] == [0, 0]
    assert [r['return_pct'] for r in rows] == pytest.approx([0, 0], abs=1e-7)


def test_daily_flow_timing_uses_same_money_weighted_method_as_periods():
    middle = date(2026, 7, 1)
    terminal = 100 * 1.1 + 100 * 1.1 ** ((END - middle).days / (END - START).days)
    rows = report_daily(tracking(), [{'snapshot_date': END, 'value_krw': terminal}], [flow(middle, 100)])
    assert rows[0]['return_pct'] == pytest.approx(10)


def test_daily_missing_days_are_not_fabricated_and_require_no_month_boundary():
    rows = report_daily(tracking(), [{'snapshot_date': date(2026, 2, 10), 'value_krw': 150}], [])
    assert len(rows) == 1 and rows[0]['return_pct'] == pytest.approx(50)
    assert report_daily(None, [], []) == []
    assert report_daily(tracking(), [], []) == []
    assert report_daily(tracking(), [{'snapshot_date': date(2025, 12, 31), 'value_krw': 10}], []) == []


def test_new_daily_records_display_returns_without_daily_confirmation():
    snapshots = [{'snapshot_date': START, 'value_krw': 100},
                 {'snapshot_date': date(2026, 1, 2), 'value_krw': 110}]
    rows = report_daily({**tracking(), 'confirmed_through': START}, snapshots, [])
    assert rows[0]['return_pct'] == 0
    assert rows[1]['return_pct'] == pytest.approx(10) and rows[1]['profit'] == 10 and rows[1]['value_krw'] == 110
    assert not rows[1]['warning'] and rows[1]['flow_count']==0
    rows = report_daily({**tracking(), 'confirmed_revision': 0}, snapshots, [])
    assert [r['return_pct'] for r in rows] == pytest.approx([0,10])


def test_recorded_flow_add_cancel_and_restore_recompute_without_confirmation():
    t={**tracking(),'confirmed_revision':-1,'confirmed_through':None}
    end=date(2026,1,31)
    snaps=[{'snapshot_date':end,'value_krw':200}]
    for reporter in (report_daily,report_periods):
        missing=reporter(t,snaps,[])[0]
        assert missing['profit']==100 and missing['return_pct']==pytest.approx(100)
        f=flow(end,100)
        added=reporter(t,snaps,[f])[0]
        assert added['profit']==0 and added['return_pct']==pytest.approx(0,abs=1e-7)
        assert added['flow_count']==1 and not added['warning']
        cancelled=reporter(t,snaps,[{**f,'voided':True}])[0]
        assert cancelled['profit']==100 and cancelled['flow_count']==0
        assert cancelled['return_pct']==pytest.approx(100)
        assert reporter(t,snaps,[f])[0]==added


def test_net_zero_recorded_flows_still_use_their_dates_and_count_as_flows():
    snaps=[{'snapshot_date':END,'value_krw':110}]
    flows=[flow(date(2026,3,1),100),flow(date(2026,10,1),-100)]
    t={**tracking(),'confirmed_revision':-1,'confirmed_through':None}
    daily=report_daily(t,snaps,flows)[0]
    expected,warning=money_weighted_return(START,END,100,110,flows)
    assert daily['net_flow']==0 and daily['flow_count']==2 and daily['profit']==10
    assert daily['return_pct']==pytest.approx(expected) and not warning
    assert daily['return_pct']!=pytest.approx(10)


def test_daily_same_day_value_changes_do_not_claim_zero_return():
    rows = report_daily(tracking(), [{'snapshot_date': START, 'value_krw': 110}], [])
    assert rows[0]['return_pct'] is None and rows[0]['profit'] == 10 and '하루 이상' in rows[0]['warning']
    rows = report_daily(tracking(), [{'snapshot_date': date(2026, 1, 2), 'value_krw': 200}], [flow(START, 100)])
    assert rows[0]['profit'] == 0 and rows[0]['return_pct'] == pytest.approx(0, abs=1e-7)


def test_daily_ambiguous_return_is_not_fabricated_but_profit_is_available():
    rows = report_daily(tracking(), [{'snapshot_date': END, 'value_krw': 100}],
                        [flow(date(2026, 3, 1), -300), flow(date(2026, 6, 1), 300)])
    assert rows[0]['return_pct'] is None and rows[0]['profit'] == 0
    assert '부호' in rows[0]['warning']
