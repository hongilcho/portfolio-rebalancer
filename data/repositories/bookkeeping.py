"""Durable request receipts shared by manual bookkeeping transactions."""
import json

from psycopg2.extras import Json


def plain(value):
    result = json.loads(json.dumps(value, default=str))
    def clean(item):
        if isinstance(item, dict):
            return {key:clean(val) for key,val in item.items() if key!='execution' or val is not None}
        if isinstance(item, list): return [clean(val) for val in item]
        return item
    return clean(result)


def begin(cursor, scope, request_id, payload):
    """A unique insert serializes retries; the receipt commits with the ledger."""
    payload = plain(payload)
    cursor.execute("""INSERT INTO bookkeeping_requests(scope,request_id,payload)
        VALUES(%s,%s,%s) ON CONFLICT(scope,request_id) DO NOTHING""",
        (scope, request_id, Json(payload)))
    cursor.execute("""SELECT payload,result FROM bookkeeping_requests
        WHERE scope=%s AND request_id=%s FOR UPDATE""", (scope, request_id))
    row = cursor.fetchone()
    saved = row['payload'] if isinstance(row['payload'], dict) else json.loads(row['payload'])
    if saved != payload:
        raise ValueError('같은 요청 번호의 입력 내용이 변경되었습니다. 저장 결과를 먼저 확인해주세요.')
    result = row['result']
    return result if isinstance(result, dict) or result is None else json.loads(result)


def finish(cursor, scope, request_id, result):
    cursor.execute('UPDATE bookkeeping_requests SET result=%s WHERE scope=%s AND request_id=%s',
                   (Json(plain(result)), scope, request_id))
