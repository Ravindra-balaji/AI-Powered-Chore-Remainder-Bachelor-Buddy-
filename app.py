from flask import Flask, render_template, request, jsonify
import os
from main_logic import process_chores

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
LATEST = os.path.join(UPLOAD_FOLDER, "latest.csv")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_csv():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    # save to uploads/latest.csv (overwrite each upload)
    file.save(LATEST)

    # Preview today's tasks (dry run)
    try:
        logs = process_chores(csv_file=LATEST, dry_run=True)
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/send", methods=["POST"])
def send_messages():
    # send using the last uploaded file
    if not os.path.exists(LATEST):
        return jsonify({"error": "No uploaded file found. Please upload first."}), 400
    try:
        logs = process_chores(csv_file=LATEST, dry_run=False)
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
