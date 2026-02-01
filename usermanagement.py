import sqlite3

conn = sqlite3.connect("users.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    registration_number TEXT NOT NULL,
    country TEXT NOT NULL,
    date_of_birth TEXT NOT NULL
)
""")

conn.commit()
conn.close()

print("users.db created successfully with users table.")
