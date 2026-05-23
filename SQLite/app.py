from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from PIL import Image
from rapidfuzz import fuzz
import pytesseract
import sqlite3
import re
import os
import cv2
import numpy as np

# -------------------------
# OCR config (Windows)
# -------------------------
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

app = Flask(__name__)
app.secret_key = "admin_secret_key"

# -------------------------
# Database paths (UNCHANGED)
# -------------------------
SQLITE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SQLITE_DIR)

RULES_DB = os.path.join(PROJECT_DIR, "rules.db")
USER_DB = os.path.join(SQLITE_DIR, "users.db")

# -------------------------
# Helper data
# -------------------------
SALT_MAP = {
    "hydrochloride", "hcl",
    "sodium", "potassium", "calcium", "magnesium",
    "phosphate", "sulphate", "sulfate",
    "nitrate", "acetate"
}

# -------------------------
# Helper functions
# -------------------------
def extract_user_ingredients(text):
    text = text.lower()
    words = re.findall(r"[a-z\-]{3,}", text)
    return {w for w in words if w not in SALT_MAP}

def clean_ocr_text(text):
    text = text.lower()
    text = re.sub(r"\d+(mg|ml|mcg)", " ", text)
    text = re.sub(r"[^a-z\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

FUZZY_THRESHOLD = 85

def normalize_token(token):
    return token.replace(" ", "").replace("-", "")

def check_ingredients(user_tokens):
    conn = sqlite3.connect(RULES_DB)
    cur = conn.cursor()
    cur.execute("SELECT name, ingredients, risk_level FROM regulatory_rules")
    rules = cur.fetchall()
    conn.close()

    exact_matches = []
    related_matches = []

    normalized_user_tokens = {
        normalize_token(t) for t in user_tokens if t not in SALT_MAP
    }

    for name, ing_text, risk in rules:

        if ing_text == "category_only":
            continue

        rule_tokens = {
            t.strip()
            for t in ing_text.split(",")
            if t.strip() and t.strip() not in SALT_MAP
        }

        normalized_rule_tokens = {
            normalize_token(t) for t in rule_tokens
        }

        match_count = 0

        for rt in normalized_rule_tokens:
            for ut in normalized_user_tokens:
                if fuzz.ratio(rt, ut) >= FUZZY_THRESHOLD:
                    match_count += 1
                    break

        if normalized_rule_tokens and match_count == len(normalized_rule_tokens):
            exact_matches.append(name)
            continue

        if match_count > 0:
            related_matches.append(name)

    if exact_matches:
        return {
            "status": "HIGH RISK",
            "message": "Exact harmful combination detected.",
            "exact_matches": exact_matches,
            "related_matches": [r for r in related_matches if r not in exact_matches]
        }

    if related_matches:
        return {
            "status": "NEEDS REVIEW",
            "message": "Category-level regulatory match found.",
            "exact_matches": [],
            "related_matches": related_matches
        }

    return {
        "status": "NO MATCH",
        "message": "No CDSCO regulatory issues detected.",
        "exact_matches": [],
        "related_matches": []
    }

# -------------------------
# OCR Preprocessing
# -------------------------
def preprocess_image(image):
    img = np.array(image)

    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    img = cv2.resize(img, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    img = cv2.GaussianBlur(img, (5, 5), 0)

    img = cv2.adaptiveThreshold(
        img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2
    )

    return img.astype(np.uint8)

# -------------------------
# Public Routes
# -------------------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/check", methods=["POST"])
def check():
    data = request.get_json()
    ingredients_text = data.get("ingredients", "")
    user_tokens = extract_user_ingredients(ingredients_text)
    result = check_ingredients(user_tokens)
    return jsonify(result)

@app.route("/ocr", methods=["POST"])
def ocr_image():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    try:
        img = Image.open(request.files["image"]).convert("RGB")
        processed = preprocess_image(img)
        extracted_text = pytesseract.image_to_string(processed, config='--oem 3 --psm 6')
    except Exception as e:
        return jsonify({"error": f"OCR failed: {str(e)}"}), 500

    cleaned_text = clean_ocr_text(extracted_text)
    user_tokens = extract_user_ingredients(cleaned_text)
    result = check_ingredients(user_tokens)
    result["extracted_text"] = extracted_text

    return jsonify(result)

# -------------------------
# Admin Authentication
# -------------------------
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = sqlite3.connect(USER_DB)
        cur = conn.cursor()
        cur.execute("SELECT user_id, role FROM users WHERE username=? AND password=?", (username, password))
        user = cur.fetchone()
        conn.close()

        if user:
            session["admin_logged_in"] = True
            session["user_id"] = user[0]
            session["role"] = user[1]
            return redirect(url_for("admin_database"))

        return render_template("admin_login.html", error="Invalid credentials")

    return render_template("admin_login.html")

# -------------------------
# Admin Pages
# -------------------------
@app.route("/admin/database")
def admin_database():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    conn = sqlite3.connect(RULES_DB)
    cur = conn.cursor()
    cur.execute("SELECT rule_id, name, ingredients, risk_level FROM regulatory_rules")
    rules = cur.fetchall()
    conn.close()

    return render_template("admin_database.html", role=session.get("role"), rules=rules)

@app.route("/admin/approvals")
def admin_approvals():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    if session.get("role") != "superadmin":
        return "Forbidden", 403

    conn = sqlite3.connect(RULES_DB)
    cur = conn.cursor()

    cur.execute("""
        SELECT pc.id,
               pc.rule_id,
               rr.name AS old_name,
               rr.ingredients AS old_ingredients,
               rr.risk_level AS old_risk,
               pc.proposed_name,
               pc.proposed_ingredients,
               pc.proposed_risk_level
        FROM pending_changes pc
        JOIN regulatory_rules rr
        ON pc.rule_id = rr.rule_id
        WHERE pc.status='PENDING'
    """)

    rows = cur.fetchall()
    conn.close()

    approvals = []

    for row in rows:
        approvals.append({
            "id": row[0],
            "rule_id": row[1],
            "proposed_name": row[5],
            "proposed_ingredients": row[6],
            "proposed_risk": row[7],
            "name_changed": row[2] != row[5],
            "ingredients_changed": row[3] != row[6],
            "risk_changed": row[4] != row[7],
        })

    return render_template(
        "approvals.html",
        role=session.get("role"),
        approvals=approvals
    )

@app.route("/admin/approve/<int:change_id>")
def approve_change(change_id):
    if session.get("role") != "superadmin":
        return "Forbidden", 403

    conn = sqlite3.connect(RULES_DB)
    cur = conn.cursor()

    cur.execute("""
        SELECT rule_id, proposed_name, proposed_ingredients, proposed_risk_level
        FROM pending_changes WHERE id=?
    """, (change_id,))
    row = cur.fetchone()

    if row:
        rule_id, name, ingredients, risk = row
        cur.execute("""
            UPDATE regulatory_rules
            SET name=?, ingredients=?, risk_level=?
            WHERE rule_id=?
        """, (name, ingredients, risk, rule_id))
        cur.execute("UPDATE pending_changes SET status='APPROVED' WHERE id=?", (change_id,))
        conn.commit()

    conn.close()
    return redirect(url_for("admin_approvals"))
@app.route("/admin/reject/<int:change_id>")
def reject_change(change_id):
    if session.get("role") != "superadmin":
        return "Forbidden", 403

    conn = sqlite3.connect(RULES_DB)
    cur = conn.cursor()

    cur.execute(
        "UPDATE pending_changes SET status='REJECTED' WHERE id=?",
        (change_id,)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("admin_approvals"))
# -------------------------
# Admin Register
# -------------------------
@app.route("/admin/register", methods=["GET", "POST"])
def admin_register():
    if request.method == "POST":
        full_name = request.form.get("real_name")
        username = request.form.get("username")
        password = request.form.get("password")
        confirm = request.form.get("confirm_password")
        reg_no = request.form.get("reg_no")
        country = request.form.get("country")
        dob = request.form.get("dob")

        if password != confirm:
            return render_template("admin_register.html", error="Passwords do not match")

        try:
            conn = sqlite3.connect(USER_DB)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO users
                (full_name, username, password, registration_number, country, date_of_birth, role)
                VALUES (?, ?, ?, ?, ?, ?, 'admin')
            """, (full_name, username, password, reg_no, country, dob))
            conn.commit()
            conn.close()
        except sqlite3.IntegrityError:
            return render_template("admin_register.html", error="Username already exists")

        return redirect(url_for("admin_login"))

    return render_template("admin_register.html")
# -------------------------
# Admin Edit Route
# -------------------------

@app.route("/admin/edit/<int:rule_id>", methods=["GET", "POST"])
def edit_rule(rule_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    role = session.get("role")

    conn = sqlite3.connect(RULES_DB)
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name")
        ingredients = request.form.get("ingredients")
        risk = request.form.get("risk_level")

        cur.execute("SELECT ingredients FROM regulatory_rules WHERE rule_id=?", (rule_id,))
        old = cur.fetchone()

        if not old:
            conn.close()
            return "Rule not found", 404

        old_ing = old[0]

        # category_only OR superadmin → direct update
        if old_ing == "category_only" or role == "superadmin":
            cur.execute("""
                UPDATE regulatory_rules
                SET name=?, ingredients=?, risk_level=?
                WHERE rule_id=?
            """, (name, ingredients, risk, rule_id))
            conn.commit()
            conn.close()
            return redirect(url_for("admin_database"))

        # normal admin → pending approval
        cur.execute("""
            INSERT INTO pending_changes
            (rule_id, proposed_name, proposed_ingredients, proposed_risk_level, status)
            VALUES (?, ?, ?, ?, 'PENDING')
        """, (rule_id, name, ingredients, risk))
        conn.commit()
        conn.close()
        return redirect(url_for("admin_database"))

    # GET request → load rule
    cur.execute("""
        SELECT rule_id, name, ingredients, risk_level
        FROM regulatory_rules
        WHERE rule_id=?
    """, (rule_id,))
    rule = cur.fetchone()
    conn.close()

    if not rule:
        return "Rule not found", 404

    return render_template("edit_rule.html", rule=rule)

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))

# -------------------------
# Start Server
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)