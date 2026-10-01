"""
Portfolio Rebalancer — Development Database Seeder (Python Runner)
===================================================================
이 스크립트는 SUPABASE_URL 환경변수로 연결된 데이터베이스에
scripts/seed_dev_db.sql의 최신 DDL 스키마 및 가짜(Mock) 샘플 데이터를 자동 적재합니다.

사용법:
    python scripts/seed_dev_db.py
"""

import os
import sys

# 프로젝트 루트를 sys.path에 추가
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from data.data_manager import get_connection

SQL_PATH = os.path.join(BASE_DIR, "scripts", "seed_dev_db.sql")

def run_seed():
    if not os.path.exists(SQL_PATH):
        print(f"Error: {SQL_PATH} not found.")
        sys.exit(1)

    print("Reading seed_dev_db.sql...")
    with open(SQL_PATH, "r", encoding="utf-8") as f:
        sql = f.read()

    print("Connecting to database and executing schema & seed...")
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute(sql)
            conn.commit()
        conn.close()
        print("Success! Development schema and mock data seeded successfully.")
    except Exception as e:
        print(f"Failed to seed database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_seed()
