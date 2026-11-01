"""Cold scheduler/report requests must not build exchange calendars concurrently."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier, Event, Lock, RLock

import pytest
from logic import close_calendar as cal


def test_cold_misses_serialize_shared_constructor_and_keep_cached_results(monkeypatch):
    attempted = Event()
    entered = Event()
    release = Event()
    count_lock = Lock()
    state = {'attempts':0,'active':0,'maximum':0,'calls':0}

    class ObservedLock:
        def __init__(self):self.lock=RLock()
        def __enter__(self):
            with count_lock:
                state['attempts']+=1
                if state['attempts']==4:attempted.set()
            return self.lock.__enter__()
        def __exit__(self,*args):return self.lock.__exit__(*args)

    def unsafe_constructor(name, **bounds):
        with count_lock:
            state['active']+=1;state['calls']+=1
            state['maximum']=max(state['maximum'],state['active'])
        entered.set()
        try:
            assert release.wait(5)
            return (name,bounds)
        finally:
            with count_lock:state['active']-=1

    cal.calendar.cache_clear()
    monkeypatch.setattr(cal,'_calendar_build_lock',ObservedLock())
    monkeypatch.setattr(cal.xcals,'get_calendar',unsafe_constructor)
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            pending=[pool.submit(cal.calendar,'XKRX',year) for year in (2024,2025,2026,2027)]
            try:
                assert entered.wait(5) and attempted.wait(5)
                assert state['maximum']==1
            finally:release.set()
            results=[f.result(timeout=5) for f in pending]
        assert results[2]==('XKRX',{'start':'2025-01-01','end':'2027-12-31'})
        assert cal.calendar('XKRX',2026) is results[2]
        assert state['calls']==4 and state['maximum']==1
    finally:cal.calendar.cache_clear()


def test_real_calendar_cold_parallel_reports_keep_session_rules():
    cal.calendar.cache_clear()
    gate=Barrier(4)
    def query(index):
        gate.wait(timeout=5)
        if index==0:return cal.last_session(date(2026,10,31))
        if index==1:return cal.is_session(date(2026,11,2))
        if index==2:return cal.sessions(date(2026,10,6),date(2026,10,8))
        return cal.calendar('XNYS',2026).is_session('2026-10-30')
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending=[pool.submit(query,i) for i in range(4)]
        results=[f.result(timeout=20) for f in pending]
    assert results==[date(2026,10,30),True,[date(2026,10,6),date(2026,10,7),date(2026,10,8)],True]


def test_failed_calendar_construction_can_be_retried(monkeypatch):
    cal.calendar.cache_clear()
    calls=[]
    def build(name,**kwargs):
        calls.append(name)
        if len(calls)==1:raise ValueError('synthetic constructor failure')
        return object()
    monkeypatch.setattr(cal.xcals,'get_calendar',build)
    try:
        with pytest.raises(ValueError):cal.calendar('XKRX',2026)
        result=cal.calendar('XKRX',2026)
        assert cal.calendar('XKRX',2026) is result and len(calls)==2
    finally:cal.calendar.cache_clear()
