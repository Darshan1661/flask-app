import os
from flask import Flask, jsonify
import psycopg2

app = Flask(__name__)

# PostgreSQL connection details
DATABASE_URL = os.getenv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/my_database")

def connect_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except psycopg2.Error as e:
        print(f"❌ Database Connection Error: {e}")
        return None

@app.route("/")
def test_connection():
    conn = connect_db()
    if conn:
        conn.close()
        return "✅ Database connected successfully!"
    else:
        return "❌ Database connection failed!", 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
