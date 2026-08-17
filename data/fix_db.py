import sqlite3
conn = sqlite3.connect('portfolio.db')
cur = conn.cursor()
cur.execute("UPDATE assets SET ticker = 'M04020000' WHERE ticker = '없음'")
conn.commit()
conn.close()
