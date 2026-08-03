import sqlite3
import os

db_path = 'data/portfolio.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT id, account_type FROM accounts')
    accounts = cursor.fetchall()
    for acc in accounts:
        acc_id, acc_type = acc
        new_prio = 99
        if "IRP" in acc_type:
            new_prio = 1
        elif "연금저축" in acc_type:
            new_prio = 2
        elif "ISA" in acc_type:
            new_prio = 3
        elif "일반매매" in acc_type:
            new_prio = 4
        elif "CMA" in acc_type:
            new_prio = 5
        
        if new_prio != 99:
            cursor.execute('UPDATE accounts SET priority = ? WHERE id = ?', (new_prio, acc_id))
    
    conn.commit()
    conn.close()
    print("Priorities updated.")
