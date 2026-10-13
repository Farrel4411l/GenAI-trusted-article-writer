import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()
cur.execute("SELECT uuid FROM langchain_pg_collection WHERE name = 'wiki_travelista'")
row = cur.fetchone()
if row:
    uuid = row[0]
    cur.execute("SELECT count(1) FROM langchain_pg_embedding WHERE collection_id = %s", (uuid,))
    print('ROWS:', cur.fetchone()[0])
else:
    print('Collection not found')
