"""Exchange sessions, independent of the host timezone and without network IO."""
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo
import exchange_calendars as xcals
import os

KST = ZoneInfo('Asia/Seoul')
# Corrections missing in exchange-calendars 4.13.2. Sources and maintenance
# policy are documented in docs/closing-performance.md.
DELAYED_CLOSES = {date(2026, 11, 19)}
EXTRA_HOLIDAYS = {date(2026, 6, 3)}


def configured_dates(name):
    return {date.fromisoformat(s.strip()) for s in os.getenv(name, '').split(',') if s.strip()}


def extra_holiday(day):
    return (day.year >= 2026 and (day.month, day.day) == (7, 17)) or day in EXTRA_HOLIDAYS | configured_dates('PERFORMANCE_KRX_EXTRA_HOLIDAYS')


@lru_cache(maxsize=8)
def calendar(name, year):
    return xcals.get_calendar(name, start=f'{year-1}-01-01', end=f'{year+1}-12-31')


def is_session(day):
    return not extra_holiday(day) and calendar('XKRX', day.year).is_session(day.isoformat())


def cutoff(day):
    """Normally 16:00 KST; wait 30 minutes after a delayed regular close."""
    close = calendar('XKRX', day.year).session_close(day.isoformat()).to_pydatetime()
    if day in DELAYED_CLOSES | configured_dates('PERFORMANCE_KRX_DELAYED_CLOSE_DATES'):
        close = max(close, datetime.combine(day, time(16,30), KST))
    return max(datetime.combine(day, time(16), KST), close.astimezone(KST)+timedelta(minutes=30))


def previous_session(day):
    return last_session(day-timedelta(days=1))


def last_session(day):
    for _ in range(40):
        result = calendar('XKRX', day.year).date_to_session(day.isoformat(), direction='previous').date()
        if not extra_holiday(result):
            return result
        day = result-timedelta(days=1)
    raise ValueError('거래소 달력의 휴장일 설정을 확인해주세요.')


def sessions(start, end):
    if start > end:
        return []
    # Split by year so long-lived installations stay within cached bounds.
    result = []
    for year in range(start.year, end.year+1):
        result.extend(d.date() for d in calendar('XKRX', year).sessions_in_range(
            max(start, datetime(year, 1, 1).date()).isoformat(),
            min(end, datetime(year, 12, 31).date()).isoformat()) if not extra_holiday(d.date()))
    return result


def us_session(valuation_at):
    """Most recent completed US regular session, including DST and holidays."""
    local_day = valuation_at.astimezone(ZoneInfo('America/New_York')).date()
    cal = calendar('XNYS', local_day.year)
    day = cal.date_to_session(local_day.isoformat(), direction='previous')
    if cal.session_close(day).to_pydatetime() > valuation_at:
        day = cal.previous_session(day)
    return day.date()
