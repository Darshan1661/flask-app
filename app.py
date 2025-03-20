import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import psycopg2
import pandas as pd

app = Flask(__name__)

# --- Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:darshan@localhost:5432/mydatabase")

# --- Flask Secret Key ---
app.secret_key = "default_secret_key"
def connect_db():
    return psycopg2.connect(DATABASE_URL)

# --- EXPORT TO EXCEL FUNCTION ---
@app.route("/export")
def export_to_excel():
    conn = connect_db()
    if conn is None:
        return "Database connection error", 500
    
    df = pd.read_sql_query("SELECT * FROM data", conn)
    conn.close()
    
    file_path = "data.xlsx"
    df.to_excel(file_path, index=False)
    return send_file(file_path, as_attachment=True)

# --- LOGIN PAGE ---
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = connect_db()
        if conn is None:
            return "Database connection error", 500
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session["user"] = username
            return redirect(url_for("home"))
        else:
            return "Invalid credentials! Try again."

    return render_template("login.html")

# --- HOME PAGE ---
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

    # Change "your_actual_table_name" to the correct table name
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
        if not data:
            return jsonify({"status": "ERROR", "message": "No JSON received"}), 400
        
        uid = data.get("UID")
        date = data.get("date")
        value = data.get("value")

        if not uid or not date or not value:
            return jsonify({"status": "ERROR", "message": "Missing required fields"}), 400

        conn = connect_db()
        if conn is None:
            return jsonify({"status": "ERROR", "message": "Database connection error"}), 500
        
        cur = conn.cursor()
        cur.execute("SELECT * FROM data_table WHERE uid = %s", (uid,))
        existing_record = cur.fetchone()

        if not existing_record:
            return jsonify({"status": "ERROR", "message": "UID not found"}), 400

        update_query = f"UPDATE data_table SET \"{date}\" = %s WHERE uid = %s"
        cur.execute(update_query, (value, uid))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"status": "OK", "message": "Data updated successfully"}), 200

    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500

# --- VERIFY UID FUNCTION ---
@app.route("/verify", methods=["POST"])
def verify_uid():
    try:
        data = request.get_json()
        if not data or "UID" not in data:
            return jsonify({"status": "ERROR", "message": "Invalid or missing JSON"}), 400
        
        uid = data.get("UID")

        conn = connect_db()
        if conn is None:
            return jsonify({"status": "ERROR", "message": "Database connection error"}), 500
        
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM data_table WHERE uid = %s", (uid,))
        user = cursor.fetchone()
        conn.close()

        if user:
            return jsonify({"status": "VERIFIED", "name": user[0]}), 200
        return jsonify({"status": "NOT_FOUND"}), 404

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
    app.run(host="0.0.0.0", port=port)
