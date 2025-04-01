import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import psycopg2
import pandas as pd

app = Flask(__name__)

# --- Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mydb_bo4h_user:62G78IsSH8APj0GSXgDe8FvhGuTrHfY0@dpg-cvj8hlemcj7s73e9oni0-a.oregon-postgres.render.com/mydb_bo4h?sslmode=require")

# --- Flask Secret Key ---
app.secret_key = os.getenv("FLASK_SECRET_KEY", "a3f1c9b8d7e6f5a4b3c2d1e0f9e8d7c6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1")

# -- Connect to Database --
def connect_db():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except Exception as e:
        return None

conn = connect_db()
if conn:
    with conn.cursor() as cursor:
        username = "admin"
        raw_password = "admin123"  # Store as plain text

        # Check if user already exists
        cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
        existing_user = cursor.fetchone()

        if not existing_user:
            cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", 
                           (username, raw_password))  # Save as plain text
            conn.commit()
    conn.close()

# --- EXPORT TO EXCEL FUNCTION ---
@app.route("/export")
def export_to_excel():
    conn = connect_db()
    if conn is None:
        return "Database connection error", 500
    
    try:
        df = pd.read_sql_query("SELECT * FROM records_2025_03", conn)
        file_path = "data.xlsx"
        df.to_excel(file_path, index=False)
        return send_file(file_path, as_attachment=True)
    finally:
        conn.close()
        
# --- LOGIN FUNCTION ---
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = connect_db()
        if conn is None:
            return "Database connection error", 500
            
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT password FROM users WHERE username = %s", (username,))
                result = cursor.fetchone()
                
                if result and result[0] == password:
                    session["user"] = username
                    return redirect(url_for("home"))
                return render_template("login.html", error="Invalid credentials! Try again.")
        finally:
            conn.close()
    return render_template("login.html")

# --- HOME ---
@app.route("/home")
def home():
    if "user" in session:
        return render_template("home.html", username=session["user"])
    return redirect(url_for("login"))

# --- DISPLAY TABLE PAGE ---
@app.route("/table")
def show_table():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = connect_db()
    if conn is None:
        return "Database connection error", 500

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM records_2025_03")  
    rows = cursor.fetchall()
    column_names = [desc[0] for desc in cursor.description]
    conn.close()

    data = [dict(zip(column_names, row)) for row in rows]
    return render_template("table.html", rows=data)

# --- UPDATE DATABASE (ESP32 API) ---
@app.route("/update", methods=["POST"])
def update():
    try:
        data = request.get_json()
        print("Received JSON:", data)  # Debugging print
        if not data or not all(field in data for field in ["UID", "date", "value"]):
            return jsonify({"status": "ERROR", "message": "Invalid JSON or missing fields"}), 400

        uid, date, value = data["UID"], data["date"], data["value"]
        conn = connect_db()
        if conn is None:
            return jsonify({"status": "ERROR", "message": "Database connection error"}), 500
        
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE records_2025_03 
                    SET {date} = %s 
                    WHERE uid = %s
                """, (value, uid))
                conn.commit()
            return jsonify({"status": "OK", "message": "Data updated successfully"}), 200
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500

# --- VERIFY UID FUNCTION ---
@app.route("/verify", methods=["POST", "GET"])  # Allow both POST and GET  
def verify_uid():
    try:
        data = request.get_json()
        if not data or "UID" not in data:
            return jsonify({"status": "ERROR", "message": "Invalid or missing JSON"}), 400
        
        uid = data["UID"]
        conn = connect_db()
        if conn is None:
            return jsonify({"status": "ERROR", "message": "Database connection error"}), 500
        
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM records_2025_03 WHERE uid = %s", (uid,))
        user = cursor.fetchone()
        conn.close()

        return jsonify({"status": "VERIFIED", "name": user[0] if user else "Unknown"}), 200 if user else 404
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500


# --- LOGOUT FUNCTION ---
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- RUN APP ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
app.run(host="0.0.0.0", port=10000, debug=True)

