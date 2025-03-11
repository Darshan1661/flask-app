import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import psycopg2
import pandas as pd

app = Flask(__name__)

# Load secret key from environment variables
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

# Database connection function
def connect_db():
    try:
        DATABASE_URL = os.getenv("DATABASE_URL")
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL is not set in environment variables")
        
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        return conn
    except Exception as e:
        print(f"Database Connection Error: {e}")
        return None

# --- EXPORT TO EXCEL FUNCTION ---
@app.route("/export")
def export_to_excel():
    conn = connect_db()
    if conn is None:
        return "Database connection error", 500
    
    df = pd.read_sql_query("SELECT * FROM data_table", conn)
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
    else:
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

    # Execute query
    cursor.execute("SELECT * FROM data_table")  
    rows = cursor.fetchall()

    # Get column names
    column_names = [desc[0] for desc in cursor.description]

    conn.close()

    # Convert tuples to dictionaries
    data = [dict(zip(column_names, row)) for row in rows]

    return render_template("table.html", rows=data)

# --- UPDATE DATABASE (ESP32 API) ---
@app.route("/update", methods=["POST"])
def update():
    try:
        data = request.get_json()
        print("Received JSON:", data)  # Debugging

        if not data:
            return jsonify({"status": "ERROR", "message": "No JSON received"}), 400
        
        if "UID" not in data or "date" not in data or "value" not in data:
            return jsonify({"status": "ERROR", "message": "Missing required fields"}), 400

        uid = data["UID"]
        date = data["date"]
        value = data["value"]

        print(f"UID: {uid}, Date: {date}, Value: {value}")  # Debugging

        # ✅ Connect to PostgreSQL
        conn = connect_db()
        if conn is None:
            return jsonify({"status": "ERROR", "message": "Database connection error"}), 500
        
        cur = conn.cursor()

        # ✅ Check if UID exists
        cur.execute("SELECT * FROM data_table WHERE uid = %s", (uid,))
        existing_record = cur.fetchone()

        if not existing_record:
            return jsonify({"status": "ERROR", "message": "UID not found"}), 400

        # ✅ Update the specific date column in the database
        update_query = f'UPDATE data_table SET "{date}" = %s WHERE uid = %s'
        cur.execute(update_query, (value, uid))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"status": "OK", "message": "Data updated successfully"}), 200

    except Exception as e:
        print("Exception:", str(e))  # Debugging
        return jsonify({"status": "ERROR", "message": str(e)}), 500
    
# --- VERIFY UID FUNCTION ---
@app.route("/verify", methods=["POST"])
def verify_uid():
    try:
        data = request.get_json()

        if not data or "UID" not in data:
            return jsonify({"status": "ERROR", "message": "Invalid or missing JSON"}), 400
        
        uid = data.get("UID")
        print(f"Received UID: {uid}")  # Debugging

        conn = connect_db()
        if conn is None:
            return jsonify({"status": "ERROR", "message": "Database connection error"}), 500
        
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM data_table WHERE uid = %s", (uid,))
        user = cursor.fetchone()
        conn.close()

        if user:
            return jsonify({"status": "VERIFIED", "name": user[0]}), 200
        else:
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
    port = int(os.environ.get("PORT", 10000))  # Use Render's port dynamically
    app.run(host="0.0.0.0", port=port)
