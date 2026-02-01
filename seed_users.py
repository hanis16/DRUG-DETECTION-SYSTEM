import sqlite3
import os
import random
import string

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DB = os.path.join(BASE_DIR, "users.db")

# simple 5-letter word pool
WORDS = [
    "mango", "tiger", "river", "cloud", "apple",
    "stone", "green", "light", "music", "earth"
]

SYMBOLS = ["@", "#", "$", "!"]

def generate_password():
    word = random.choice(WORDS)
    number = random.randint(10, 99)
    symbol = random.choice(SYMBOLS)
    return f"{word}{number}{symbol}"

def generate_reg_no():
    return "82" + "".join(random.choices(string.digits, k=4))

users = [
    ("Amit Sharma", "amit01", generate_password(), generate_reg_no(), "India", "1999-05-12"),
    ("Priya Nair", "priya02", generate_password(), generate_reg_no(), "India", "2000-08-21"),
    ("Rahul Verma", "rahul03", generate_password(), generate_reg_no(), "India", "1998-11-03"),
    ("Sneha Iyer", "sneha04", generate_password(), generate_reg_no(), "India", "2001-01-15"),
    ("Arjun Patel", "arjun05", generate_password(), generate_reg_no(), "India", "1997-09-09"),
    ("Neha Gupta", "neha06", generate_password(), generate_reg_no(), "India", "1999-03-27"),
    ("Karan Singh", "karan07", generate_password(), generate_reg_no(), "India", "2000-06-18"),
    ("Pooja Mehta", "pooja08", generate_password(), generate_reg_no(), "India", "1998-12-30"),
    ("Vikram Rao", "vikram09", generate_password(), generate_reg_no(), "India", "1997-04-05"),
    ("Ananya Das", "ananya10", generate_password(), generate_reg_no(), "India", "2001-10-11"),
]

conn = sqlite3.connect(USER_DB)
cur = conn.cursor()

cur.executemany("""
    INSERT OR IGNORE INTO users
    (full_name, username, password, registration_number, country, date_of_birth)
    VALUES (?, ?, ?, ?, ?, ?)
""", users)

conn.commit()
conn.close()

print("10 sample users inserted with formatted registration numbers and passwords.")
