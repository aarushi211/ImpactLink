import os, psycopg
from dotenv import load_dotenv
load_dotenv()
with psycopg.connect(os.getenv("DATABASE_URL")) as conn:
    count = conn.execute("SELECT COUNT(*) FROM grants").fetchone()[0]
    print("Grants in pgvector:", count)
