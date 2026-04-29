import pymysql
conn = pymysql.connect(host='localhost', user='neurolearn', password='neurolearn_pass', database='neurolearn')
cur = conn.cursor()
cur.execute("SELECT title, LEFT(content, 300) FROM content_items WHERE title LIKE '%Data%' LIMIT 1")
r = cur.fetchone()
if r:
    print("Title:", r[0])
    print("Content preview:", repr(r[1]))
conn.close()
