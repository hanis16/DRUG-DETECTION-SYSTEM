from PIL import Image
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import sqlite3
import re
import os


app = Flask(__name__)
app.secret_key = "admin_secret_key"

# -------------------------
# Database paths (ABSOLUTE)
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_DB = os.path.join(BASE_DIR, "rules.db")
USER_DB = os.path.join(BASE_DIR, "users.db")

# -------------------------
# Helper functions
# -------------------------

def extract_user_ingredients(text):
    text = text.lower()
    tokens = re.findall(r"[a-z\-]{3,}", text)
    return set(tokens)


def check_ingredients(user_tokens):
    conn = sqlite3.connect(RULES_DB)
    cur = conn.cursor()

    cur.execute("""
        SELECT name, ingredients, risk_level
        FROM regulatory_rules
    """)
    rules = cur.fetchall()
    conn.close()

    exact_matches = []
    related_matches = []

    for name, ing_text, risk in rules:
        if ing_text == "category_only":
            continue

        rule_tokens = {t.strip() for t in ing_text.split(",")}

        if user_tokens == rule_tokens:
            exact_matches.append(name)
            continue

        if user_tokens & rule_tokens:
            related_matches.append(name)

    if exact_matches:
        return {
            "status": "HIGH RISK",
            "message": "Exact harmful combination detected.",
            "exact_matches": exact_matches,
            "related_matches": related_matches
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

    def clean_ocr_text(text):
        text = text.lower()
        text = re.sub(r"\d+(mg|ml|mcg)", " ", text)
        text = re.sub(r"[^a-z\s\-]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


# -------------------------
# Routes
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

# -------------------------
# Admin login (DB-backed)
# -------------------------

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = sqlite3.connect(USER_DB)
        cur = conn.cursor()

        cur.execute("""
            SELECT user_id FROM users
            WHERE username = ? AND password = ?
        """, (username, password))

        user = cur.fetchone()
        conn.close()

        if user:
            session["admin_logged_in"] = True
            session["user_id"] = user[0]
            return redirect(url_for("admin_dashboard"))

        return render_template(
            "admin_login.html",
            error="Invalid username or password"
        )

    return render_template("admin_login.html")

# -------------------------
# Admin register (DB write)
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
            return render_template(
                "admin_register.html",
                error="Passwords do not match"
            )

        try:
            conn = sqlite3.connect(USER_DB)
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO users
                (full_name, username, password, registration_number, country, date_of_birth)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (full_name, username, password, reg_no, country, dob))

            conn.commit()
            conn.close()

        except sqlite3.IntegrityError:
            return render_template(
                "admin_register.html",
                error="Username already exists"
            )

        return redirect(url_for("admin_login"))

    return render_template("admin_register.html")

# -------------------------
# Admin dashboard
# -------------------------

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    return """
    <h2>Admin Dashboard</h2>
    <p>Admin access granted.</p>
    <a href="/admin/logout">Logout</a>
    """

@app.route("/ocr", methods=["POST"])
def ocr_image():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image_file = request.files["image"]
    img = Image.open(image_file)

    extracted_text = pytesseract.image_to_string(img)
    cleaned_text = clean_ocr_text(extracted_text)

    user_tokens = extract_user_ingredients(cleaned_text)
    result = check_ingredients(user_tokens)

    result["extracted_text"] = extracted_text
    return jsonify(result)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    session.pop("user_id", None)
    return redirect(url_for("home"))

# -------------------------
# Start server
# -------------------------

if __name__ == "__main__":
    app.run(debug=True)
