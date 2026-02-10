import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DB = os.path.join(BASE_DIR, "users.db")

conn = sqlite3.connect(USER_DB)
cur = conn.cursor()

# Set role to superadmin for your account
cur.execute("""
    UPDATE users
    SET role = 'superadmin'
    WHERE full_name = ?
""", ("Hanis M H",))

conn.commit()

if cur.rowcount == 0:
    print("No user with full_name = 'Hanis MH' found. Check spelling.")
else:
    print("Success: Hanis MH is now superadmin.")

conn.close()
