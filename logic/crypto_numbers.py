"""Canonical stored REAL values, independent of PostgreSQL text precision.

Readers cast REAL to double precision so even extra_float_digits=0 retains
enough digits to recover the original float32. No stored value is changed.
"""
import math
import struct


def stored_real(value):
    value=float(value or 0)
    if not math.isfinite(value):raise ValueError('유효한 가상자산 수량·원가가 필요합니다.')
    try:return struct.unpack('!f',struct.pack('!f',value))[0]
    except (OverflowError,struct.error):raise ValueError('가상자산 저장 범위를 벗어난 값입니다.') from None


def precise_holding(row):
    result=dict(row)
    for field in ('quantity','avg_price'):
        key=field+'_precise'
        if key in result:result[field]=stored_real(result.pop(key))
    return result
