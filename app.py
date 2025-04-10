import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, session
import psycopg2
import pandas as pd
import json
from flask_session import Session
from io import BytesIO  # For Excel export
from twilio.rest import Client

app = Flask(__name__)

# --- Flask Secret Key ---
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your_secret_key_here")

# --- Configure Server-side Session ---
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_FILE_DIR"] = "./flask_sessions"
Session(app)

# --- Database Configuration ---
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://mydb_bo4h_user:62G78IsSH8APj0GSXgDe8FvhGuTrHfY0@dpg-cvj8hlemcj7s73e9oni0-a.oregon-postgres.render.com/mydb_bo4h?sslmode=require"
)

# --- Connect to Database ---
def connect_db():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

# --- EXPORT DATA TO EXCEL ---
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

# --- HOME PAGE ---
@app.route("/home")
def home():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("home.html", username=session["user"])

# --- DISPLAY TABLE PAGE ---
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

# --- UPDATE DATA USING API KEY ---
@app.route('/update', methods=['POST'])
def update_data():
    api_key = request.headers.get("x-api-key")
    if not api_key:
        return jsonify({"status": "ERROR", "message": "API key missing"}), 401

    conn = connect_db()
    if conn is None:
        return jsonify({"status": "ERROR", "message": "Database connection error"}), 500

    cursor = conn.cursor()
    cursor.execute("SELECT table_name FROM customers WHERE api_key = %s", (api_key,))
    result = cursor.fetchone()

    if not result:
        conn.close()
        return jsonify({"status": "ERROR", "message": "Invalid API Key"}), 403

    table_name = result[0]
    data = request.get_json()
    if not data or "UID" not in data or "date" not in data or "value" not in data:
        conn.close()
        return jsonify({"status": "ERROR", "message": "Invalid request data"}), 400

    uid = data["UID"]
    date = data["date"]
    value = data["value"]

    try:
        cursor.execute(f'UPDATE "{table_name}" SET "{date}" = %s WHERE uid = %s', (value, uid))
        conn.commit()

        cursor.execute(f'SELECT name, phone FROM "{table_name}" WHERE uid = %s', (uid,))
        user = cursor.fetchone()
        if user:
            name, phone = user
            send_whatsapp_message(name, value, date, phone)

    except Exception as e:
        conn.close()
        return jsonify({"status": "ERROR", "message": f"Database error: {e}"}), 500

    conn.close()
    return jsonify({"status": "SUCCESS", "message": "Data updated and message sent"}), 200

#--- SEND WHATSAPP MESSAGE (Twilio Sandbox) ---
def send_whatsapp_message(name, value, date, phone):
    # Twilio credentials from environment variables
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    template_sid = os.getenv("TWILIO_TEMPLATE_SID")  # Use your actual template SID

    # Twilio sandbox number (unchanged)
    from_whatsapp = os.getenv("TWILIO_FROM_WHATSAPP", "whatsapp:+14155238886")
    to_whatsapp = f"whatsapp:{phone}"

    # Create the Twilio client
    client = Client(account_sid, auth_token)

    try:
        # Send template message
        message = client.messages.create(
            from_=from_whatsapp,
            to=to_whatsapp,
            content_sid=template_sid,
            content_variables=json.dumps({
                "1": name,
                "2": date,
                "3": f"₹{value}"
            })
        )
        print("Message sent successfully. SID:", message.sid)

    except Exception as e:
        print("Failed to send WhatsApp message:", str(e))



# --- VERIFY UID USING API KEY ---
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
        return jsonify({"status": "VERIFIED", "UID": uid, "name": user[0]}), 200
    else:
        return jsonify({"status": "NOT_FOUND", "message": "UID not found"}), 404

# --- LOGOUT FUNCTION ---
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- RUN FLASK APP ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
