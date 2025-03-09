from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import sqlite3
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = "your_secret_key"

# --- DATABASE CONNECTION FUNCTION ---
def connect_db():
    return sqlite3.connect("database.db")

# --- EXPORT TO EXCEL FUNCTION ---
@app.route("/export")
def export_to_excel():
    conn = connect_db()
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
        username = request.form["username"]
        password = request.form["password"]

        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
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
    else:
        return redirect(url_for("login"))

# --- DISPLAY TABLE PAGE ---
@app.route("/table")
def show_table():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = connect_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM data")
    rows = cursor.fetchall()
    conn.close()

    return render_template("table.html", rows=rows)

# --- UPDATE DATABASE (ESP32 API) ---
@app.route("/update", methods=["POST"])
def update_data():
    try:
        data = request.get_json()
        uid = data.get("UID")
        date = data.get("date")
        value = data.get("value")

        if not uid or not date or value is None:
            return jsonify({"status": "ERROR", "message": "Missing data"}), 400

        print(f"Received: UID={uid}, Date={date}, Value={value}")  # Debugging

        conn = connect_db()
        cursor = conn.cursor()

        # Check if UID exists and get the namen n
        cursor.execute("SELECT name FROM data WHERE uid = ?", (uid,))
        result = cursor.fetchone()

        if result:
            name = result[0]
            try:
                cursor.execute(f"UPDATE data SET `{date}` = ? WHERE uid = ?", (int(value), uid))
                conn.commit()
            except sqlite3.OperationalError:
                conn.close()
                return jsonify({"status": "ERROR", "message": f"Date column '{date}' not found"}), 400

            conn.close()
            return jsonify({"status": "VERIFIED", "name": name}), 200
        else:
            conn.close()
            return jsonify({"status": "NOT_FOUND"}), 404
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 400

# --- VERIFY UID FUNCTION ---
@app.route("/verify", methods=["POST"])
def verify_uid():
    try:
        data = request.get_json()
        uid = data.get("UID")
        print(f"Received UID: {uid}")  # Debugging

        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM data WHERE uid = ?", (uid,))
        user = cursor.fetchone()
        conn.close()

        if user:
            return jsonify({"status": "VERIFIED", "name": user[0]})
        else:
            return jsonify({"status": "NOT_FOUND"}), 404
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 400

# --- LOGOUT FUNCTION ---
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- RUN APP ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
