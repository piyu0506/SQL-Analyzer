"""Flask entry point for the SQL Query Security Analyzer."""

import logging

from flask import Flask, jsonify, render_template, request

from analyzer.pipeline import analyze_query


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024
logging.basicConfig(level=logging.INFO)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "SQL Query Security Analyzer"})


@app.post("/api/analyze")
def analyze():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        return jsonify({"error": "'query' must be a non-empty string."}), 400
    try:
        return jsonify(analyze_query(query))
    except Exception:
        app.logger.exception("Unexpected failure while analyzing SQL input.")
        return jsonify({"error": "An unexpected analysis error occurred."}), 500


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "Query is too large. Maximum request size is 32 KB."}), 413


if __name__ == "__main__":
    app.run(debug=False)
