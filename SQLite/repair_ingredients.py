import sqlite3
import re

DB_NAME = "rules.db"

KNOWN_INGREDIENTS = {
    "phenacetin", "sibutramine", "rimonabant", "cisapride",
    "terfenadine", "astemizole", "nimesulide", "diclofenac",
    "codeine", "dextromethorphan", "paracetamol",
    "phenylephrine", "caffeine", "levocetirizine",
    "cetirizine", "chlorpheniramine",
    "sodium", "potassium", "calcium", "magnesium", "lithium"
}

CATEGORY_KEYWORDS = {
    "vitamin", "analgesic", "antibiotic", "antimicrobial",
    "antidiarrhoeal", "diarrhoea", "diarrhea",
    "antihistaminic", "cough", "cold",
    "paediatric", "pediatric",
    "steroid", "sedative", "opioid", "antipyretic",
    "cardiac", "respiratory", "dermatological"
}


STOPWORDS = {
    "fixed", "dose", "combination", "combinations",
    "preparation", "preparations", "formulation",
    "drug", "drugs", "with", "and", "or", "of", "for", "in",
    "initial", "intended", "human", "use",
    "banned", "prohibited", "restricted","patent", "patented", "proprietary",
    "dover", "powder", "preparations",
    "medicine", "medicines",
    "formulation", "formulations",
    "product", "products",
    "marketed", "manufactured",
    "administered","advise","indicate","pain","container","only",
    "exceed","registered","conspicuous","medical","manner",
    "package-inserts","practitioners","promotional","administer","prescribe",
    "suspension","allowing","certain","disease","inflammatory","pelvic",
    "healing","wound","except",
    
     # articles / connectors
    "a", "an", "the", "and", "or", "of", "for", "with", "without", "in", "on", "at", "by",
    "from", "into", "during", "including", "until", "against", "among", "throughout",
    "despite", "towards", "upon", "about", "over", "before", "after", "above", "below",
    "to", "up", "down", "out", "off", "under", "again", "further", "then", "once",

    # pronouns / determiners
    "this", "that", "these", "those", "such", "same", "other", "another", "any", "each",
    "every", "either", "neither", "some", "many", "few", "several", "all", "both",

    # verbs (common)
    "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had",
    "do", "does", "did",
    "may", "might", "must", "shall", "should", "can", "could", "will", "would",

    # regulatory / legal
    "act", "acts", "rule", "rules", "section", "sections",
    "notification", "notifications", "gazette",
    "ministry", "government", "authority",
    "approved", "approval", "permitted", "permission",
    "prohibited", "banned", "restricted", "revoked",
    "licensed", "license", "licence",

    # manufacturing / commercial
    "manufacturer", "manufacturers", "manufacturing",
    "marketed", "marketing", "sale", "sold", "selling",
    "distribution", "distributed", "supply", "supplied",
    "product", "products", "preparation", "preparations",
    "formulation", "formulations",

    # medical admin / usage
    "use", "usage", "daily", "dose", "dosage",
    "intended", "recommended", "administration",
    "patient", "patients", "human", "animal",

    # warnings / outcomes
    "cancer", "carcinogenic", "toxic", "toxicity",
    "adverse", "reaction", "reactions", "effects",
    "hazard", "risk", "unsafe", "dangerous",
    "fatal", "death", "harmful",

    # intellectual property
    "patent", "patented", "proprietary", "brand", "branded",
    "dover", "powder",

    # generic fillers
    "containing", "contains", "consisting", "consists",
    "including", "includes", "thereof", "hereby",
    "initial", "final", "new", "old"
}

def extract_tokens_from_name(name, risk_level):
    t = name.lower()
    tokens = set()

    # 1. Known molecules and salts
    for ing in KNOWN_INGREDIENTS:
        if ing in t:
            tokens.add(ing)

    # 2. Explicit categories
    for cat in CATEGORY_KEYWORDS:
        if cat in t:
            tokens.add(cat.rstrip("s"))

    # 3. Patterns: "for X", "used in X"
    patterns = [
        r"for ([a-z\- ]+)",
        r"used in ([a-z\- ]+)"
    ]

    for pat in patterns:
        match = re.search(pat, t)
        if match:
            phrase = match.group(1)
            words = phrase.split()
            for w in words:
                if w not in STOPWORDS and len(w) > 4:
                    tokens.add(w)

    # 4. Plus-based FDC
    if "+" in t:
        parts = t.split("+")
        for part in parts:
            words = re.findall(r"[a-z\-]{4,}", part)
            for w in words:
                if w not in STOPWORDS:
                    tokens.add(w)

    # 5. HIGH-risk safety net
    if not tokens and risk_level == "HIGH":
        words = re.findall(r"[a-z\-]{4,}", t)
        for w in words:
            if w not in STOPWORDS:
                tokens.add(w)
                break

    return ", ".join(sorted(tokens)) if tokens else "category_only"



def repair_database():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("SELECT rule_id, name, risk_level, ingredients FROM regulatory_rules")
    rows = cur.fetchall()

    fixes = 0

    for rule_id, name, risk, old_ing in rows:
        new_ing = extract_tokens_from_name(name, risk)

        if new_ing != old_ing:
            cur.execute(
                "UPDATE regulatory_rules SET ingredients = ? WHERE rule_id = ?",
                (new_ing, rule_id)
            )
            fixes += 1

    conn.commit()
    conn.close()
    print(f"Repaired {fixes} rows.")

if __name__ == "__main__":
    repair_database()
