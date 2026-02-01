import sqlite3
import re
import os

DB_NAME = "rules.db"
INPUT_FILE = r"C:\Users\hanis\Downloads/banneddrugs.txt"

# -------------------------------
# DATABASE SETUP & CLEAN RESET
# -------------------------------

def create_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS regulatory_rules (
        rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        ingredients TEXT,
        risk_level TEXT,
        type TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rule_conditions (
        condition_id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_id INTEGER,
        condition_type TEXT,
        condition_value REAL,
        unit TEXT,
        FOREIGN KEY(rule_id) REFERENCES regulatory_rules(rule_id)
    )
    """)

    conn.commit()
    conn.close()


def clear_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM rule_conditions")
    cursor.execute("DELETE FROM regulatory_rules")
    conn.commit()
    conn.close()

# -------------------------------
# RULE LINE VALIDATION
# -------------------------------

def is_valid_rule_line(line):
    l = line.lower()

    # Reject legal / structural junk
    if any(x in l for x in [
        "dated", "gazette", "gsr", "section",
        "ministry", "notification", "vide",
        "substituted", "revoked", "hon'ble",
        "supreme court", "high court"
    ]):
        return False

    # Reject fragments
    if len(line.strip()) < 15:
        return False

    # Accept numbered rules
    if re.match(r"^\d+\.\s*[A-Za-z]", line):
        return True

    # Accept FDC and combination rules
    if "fixed dose combination" in l or "+" in line:
        return True

    return True   # TXT is already pre-cleaned

# -------------------------------
# INPUT INGESTION (TXT)
# -------------------------------

def load_rules_from_txt(filepath):
    if not os.path.exists(filepath):
        print("Input file not found:", filepath)
        return []

    with open(filepath, "r", encoding="cp1252", errors="ignore") as f:
        lines = f.readlines()

    rules = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if is_valid_rule_line(line):
            rules.append(line)

    return rules


# -------------------------------
# RULE CLASSIFICATION
# -------------------------------

def detect_type(text):
    t = text.lower()
    if "+" in t or "fixed dose combination" in t:
        return "FDC"
    elif "%" in t or "more than" in t or "less than" in t or "below" in t:
        return "CONDITIONAL"
    else:
        return "SINGLE_SUBSTANCE"


def assign_risk(rule_type):
    if rule_type == "SINGLE_SUBSTANCE":
        return "HIGH"
    elif rule_type == "FDC":
        return "MEDIUM"
    else:
        return "LOW"

# -------------------------------
# INGREDIENT EXTRACTION (HYBRID)
# -------------------------------
STOPWORDS = {
    "fixed", "dose", "combination", "combinations",
    "preparation", "preparations", "formulation", "formulations",
    "drug", "drugs", "containing", "containts",
    "with", "and", "or", "of", "for", "in",
    "initial", "intended", "human", "use",
    "banned", "prohibited", "restricted",
    "including", "excluding"
}

KNOWN_INGREDIENTS = [
    "phenacetin", "paracetamol", "phenylephrine", "caffeine",
    "alcohol", "sibutramine", "diclofenac", "nimesulide",
    "codeine", "dextromethorphan", "levocetirizine",
    "cetirizine", "chlorpheniramine"
]
CATEGORY_KEYWORDS = [
    "vitamin", "vitamins",
    "analgesic", "analgesics",
    "antibiotic", "antibiotics",
    "antihistamine", "antihistaminic",
    "antidiarrhoeal", "antidiarrhoeals",
    "antimicrobial", "antimicrobials",
    "cough", "cold",
    "steroid", "steroids",
    "sedative", "sedatives",
    "opioid", "opioids",
    "antipyretic", "antipyretics",
    "penicillin", "sulphonamide"
]

def extract_ingredients(text):
    t = text.lower()
    tokens = set()

    # 1. Exact known molecules (highest confidence)
    for ing in KNOWN_INGREDIENTS:
        if ing in t:
            tokens.add(ing)

    # 2. Category keywords
    for cat in CATEGORY_KEYWORDS:
        if cat in t:
            tokens.add(cat.rstrip("s"))

    # 3. Explicit FDC using '+'
    if "+" in t:
        parts = t.split("+")
        for part in parts:
            part = re.sub(r"[^a-z\s\-]", "", part)
            words = part.split()
            for w in words:
                if len(w) > 4 and w not in STOPWORDS:
                    tokens.add(w)

    # 4. Pattern-based extraction (of X with Y)
    patterns = [
        r"of ([a-z\s\-]+?) with ([a-z\s\-]+)",
        r"containing ([a-z\s\-]+)",
        r"containing ([a-z\s\-]+?) and ([a-z\s\-]+)"
    ]

    for pat in patterns:
        match = re.search(pat, t)
        if match:
            for group in match.groups():
                words = group.split()
                for w in words:
                    if len(w) > 4 and w not in STOPWORDS:
                        tokens.add(w)

    # FINAL CLEANUP
    cleaned = []
    for tok in tokens:
        tok = tok.strip()
        if tok and tok not in STOPWORDS and len(tok) > 4:
            cleaned.append(tok)

    return ", ".join(sorted(cleaned)) if cleaned else "category_only"


# -------------------------------
# CONDITIONAL EXTRACTION
# -------------------------------

def extract_condition(text):
    t = text.lower()
    p = re.search(r"(\d+(\.\d+)?)\s*%", t)
    proof = re.search(r"(\d+(\.\d+)?)\s*proof", t)

    if p:
        return ("PERCENTAGE", float(p.group(1)), "%")
    if proof:
        return ("PERCENTAGE", float(proof.group(1)), "proof")
    return (None, None, None)

# -------------------------------
# CORE PIPELINE
# -------------------------------

def process_rule(raw_text):
    rule_type = detect_type(raw_text)
    risk = assign_risk(rule_type)
    ingredients = extract_ingredients(raw_text)

    name = raw_text[:100] + "..." if len(raw_text) > 100 else raw_text

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO regulatory_rules (name, ingredients, risk_level, type)
        VALUES (?, ?, ?, ?)
    """, (name, ingredients, risk, rule_type))

    rule_id = cursor.lastrowid

    if rule_type == "CONDITIONAL":
        ctype, val, unit = extract_condition(raw_text)
        if ctype:
            cursor.execute("""
                INSERT INTO rule_conditions (rule_id, condition_type, condition_value, unit)
                VALUES (?, ?, ?, ?)
            """, (rule_id, ctype, val, unit))

    conn.commit()
    conn.close()

# -------------------------------
# MAIN
# -------------------------------

def main():
    print("Initializing backend...")
    create_database()
    clear_database()

    rules = load_rules_from_txt(INPUT_FILE)

    print(f"Valid rules loaded: {len(rules)}")

    for rule in rules:
        process_rule(rule)

    print("Database populated successfully.")

if __name__ == "__main__":
    main()
