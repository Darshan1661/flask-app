import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, session
import psycopg2
import pandas as pd
from flask_session import Session
from io import BytesIO
import requests

app = Flask(__name__)

# --- Secret Key ---
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your_secret_key_here")

# --- Session Config ---
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_FILE_DIR"] = "./flask_sessions"
Session(app)

# --- Database URL ---
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://mydb_bo4h_user:62G78IsSH8APj0GSXgDe8FvhGuTrHfY0@dpg-cvj8hlemcj7s73e9oni0-a.oregon-postgres.render.com/mydb_bo4h?sslmode=require"
)

def connect_db():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    except Exception:
        return None

# --- Export to Excel ---
@app.route("/export")
def export_to_excel():
    if "table_name" not in session:
        return redirect(url_for("login"))

    conn = connect_db()
    if conn is None:
        return "Database connection error", 500

    try:
        table_name = session["table_name"]
        df = pd.read_sql_query(f'SELECT * FROM "{table_name}"', conn)

        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        output.seek(0)

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f"{table_name}_data.xlsx"
        )
    finally:
        conn.close()

# --- Login ---
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
                cursor.execute("SELECT password, table_name, api_key FROM customers WHERE username = %s", (username,))
                result = cursor.fetchone()

                if result and result[0] == password:
                    session["user"] = username
                    session["table_name"] = result[1]
                    session["api_key"] = result[2]
                    return redirect(url_for("home"))

                return render_template("login.html", error="Invalid credentials!")
        finally:
            conn.close()

    return render_template("login.html")

# --- Home ---
@app.route("/home")
def home():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("home.html", username=session["user"])

# --- Table View ---
@app.route("/table")
def show_table():
    if "table_name" not in session:
        return redirect(url_for("login"))

    conn = connect_db()
    if conn is None:
        return "Database connection error", 500

    try:
        cursor = conn.cursor()
        table_name = session["table_name"]
        cursor.execute(f'SELECT * FROM "{table_name}"')
        rows = cursor.fetchall()
        column_names = [desc[0] for desc in cursor.description]
    finally:
        conn.close()

    data = [dict(zip(column_names, row)) for row in rows]
    return render_template("table.html", rows=data)


# --- Update via API ---
@app.route('/update', methods=['POST'])
def update_data():
    api_key = request.headers.get("x-api-key")
    if not api_key:
        return jsonify({"status": "ERROR", "message": "API key missing"}), 401

    # Connect to the database
    conn = connect_db()
    if conn is None:
        return jsonify({"status": "ERROR", "message": "Database connection error"}), 500

    cursor = conn.cursor()
    cursor.execute("SELECT table_name FROM customers WHERE api_key = %s", (api_key,))
    result = cursor.fetchone()

    if not result:
        conn.close()
        return jsonify({"status": "ERROR", "message": "Invalid Token"}), 403

    table_name = result[0]
    
    # Get data from request JSON
    data = request.get_json()
    if not data or "UID" not in data or "item_name" not in data or "amount" not in data or "date" not in data:
        conn.close()
        return jsonify({"status": "ERROR", "message": "Invalid request data"}), 400

    uid = data["UID"]
    item_name = data["item_name"]
    amount = data["amount"]
    date = data["date"]

    try:
        # Retrieve the customer's name and phone number from the database
        cursor.execute(f'SELECT name, phone FROM "{table_name}" WHERE uid = %s', (uid,))
        user = cursor.fetchone()
        
        if user:
            name, phone = user
            # Send WhatsApp message
            send_whatsapp_message(name, item_name, amount, date, phone)
        else:
            return jsonify({"status": "ERROR", "message": "User not found"}), 404

    except Exception as e:
        conn.close()
        return jsonify({"status": "ERROR", "message": f"Database error: {e}"}), 500

    conn.close()
    return jsonify({"status": "SUCCESS", "message": "Message sent successfully"}), 200


# --- WhatsApp via UltraMsg ---
def send_whatsapp_message(name, item_name, amount, date, phone_number): 
    url = "https://api.ultramsg.com/instance114080/messages/chat"
    token = "jnuqsbvmoqiel3pd"  # Replace with actual token

    # Construct message
    message = f"AMRUIT DARI\nname: {name}\nitem: {item_name}\namount: ₹{amount}\ndate: {date}"

    # Create payload
    payload = {
        "token": token,
        "to": phone_number,
        "body": message,
        "priority": 10
    }

    headers = {
        "content-type": "application/x-www-form-urlencoded"
    }

    # Send WhatsApp message
    response = requests.post(url, data=payload, headers=headers)
    
    # Optional: Handle response from WhatsApp API
    if response.status_code != 200:
        print(f"Error sending message: {response.text}")


    # Send WhatsApp message
    requests.post(url, data=payload, headers=headers)


# --- UID Verification ---
@app.route('/verify', methods=['POST'])
def verify_uid():
    api_key = request.headers.get("x-api-key")
    if not api_key:
        return jsonify({"status": "ERROR", "message": "API key missing"}), 401

    data = request.get_json()
    if not data or "UID" not in data:
        return jsonify({"status": "ERROR", "message": "Invalid or missing UID"}), 400

    uid = data["UID"]

    conn = connect_db()
    if conn is None:
        return jsonify({"status": "ERROR", "message": "Database connection error"}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT table_name FROM customers WHERE api_key = %s", (api_key,))
        result = cursor.fetchone()

        if not result:
            return jsonify({"status": "ERROR", "message": "Invalid API Key"}), 403

        table_name = result[0]
        cursor.execute(f'SELECT name FROM "{table_name}" WHERE uid = %s', (uid,))
        user = cursor.fetchone()
    except Exception as e:
        return jsonify({"status": "ERROR", "message": f"Database error: {e}"}), 500
    finally:
        conn.close()

    if user:
        return jsonify({"status": "VERIFIED", "name": user[0]})
    else:
        return jsonify({"status": "NOT_FOUND", "message": "UID not found"}), 404

# --- Logout ---
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# --- Run App ---
if __name__ == "__main__":
    app.run()
