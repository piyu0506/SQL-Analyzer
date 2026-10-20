"""Flask entry point for the SQL Query Security Analyzer."""

import logging

from flask import Flask, jsonify, render_template, request

from analyzer.pipeline import analyze_query
from analyzer.workspace_db import (
    create_table,
    create_random_schema,
    delete_record,
    drop_table,
    execute_select_query,
    generate_sample_data,
    get_table_definition,
    get_table_rows,
    get_workspace_snapshot,
    insert_record,
    preview_random_schema,
    reset_workspace,
    update_record,
    update_table,
)


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024
logging.basicConfig(level=logging.INFO)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "SQL Query Security Analyzer"})


@app.get("/api/schema")
@app.get("/api/workspace")
def workspace_snapshot():
    return jsonify(get_workspace_snapshot())


@app.post("/api/workspace/tables")
@app.post("/api/create-table")
@app.post("/api/manage-table")
def create_table_endpoint():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    raw_table_name = payload.get("name") or payload.get("table_name") or ""
    if not isinstance(raw_table_name, str):
        return jsonify({"error": "Table name must be text."}), 400
    table_name = raw_table_name.strip()
    columns = payload.get("columns") or payload.get("fields") or []
    if not table_name:
        return jsonify({"error": "Table name is required."}), 400
    if not isinstance(columns, list) or not columns:
        return jsonify({"error": "At least one column definition is required."}), 400

    try:
        previous_name = payload.get("original_name")
        if previous_name is not None and not isinstance(previous_name, str):
            return jsonify({"error": "Original table name must be text."}), 400
        if payload.get("update_existing") is True or previous_name:
            result = update_table(table_name, columns, previous_name=previous_name or None)
            return jsonify({"success": True, "message": f"Table '{table_name}' updated successfully.", "table": result})
        result = create_table(table_name, columns)
        return jsonify({"success": True, "message": f"Table '{table_name}' created successfully.", "table": result})
    except Exception as exc:  # pragma: no cover - flask-level handling
        return jsonify({"error": str(exc)}), 400


@app.put("/api/workspace/tables/<table_name>")
def update_table_endpoint(table_name):
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    columns = payload.get("columns") or payload.get("fields") or []
    if not isinstance(columns, list) or not columns:
        return jsonify({"error": "At least one column definition is required."}), 400
    try:
        result = update_table(table_name, columns)
        return jsonify({"success": True, "message": f"Table '{table_name}' updated successfully.", "table": result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/workspace/table/<table_name>")
def table_detail(table_name):
    try:
        return jsonify({"table": get_table_definition(table_name), "rows": get_table_rows(table_name, 25)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/workspace/tables/<table_name>/records")
def insert_table_record(table_name):
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    try:
        result = insert_record(table_name, payload.get("values", payload))
        return jsonify({
            "success": True,
            "message": f"Record inserted into '{table_name}'.",
            "record": result,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.put("/api/workspace/tables/<table_name>/records")
def update_table_record(table_name):
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    try:
        result = update_record(
            table_name,
            payload.get("locator", {}),
            payload.get("values", {}),
        )
        return jsonify({"success": True, "message": "Record updated.", "result": result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.delete("/api/workspace/tables/<table_name>/records")
def delete_table_record(table_name):
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("confirm_delete") is not True:
        return jsonify({"error": "Explicit confirmation is required to delete a record."}), 400
    try:
        result = delete_record(table_name, payload.get("locator", {}))
        return jsonify({"success": True, "message": "Record deleted.", "result": result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.delete("/api/workspace/tables/<table_name>")
@app.delete("/api/delete-table/<table_name>")
def delete_table_endpoint(table_name):
    payload = request.get_json(silent=True)
    if not request.is_json or not isinstance(payload, dict) or payload.get("confirm_delete") is not True:
        return jsonify({"error": "Explicit confirmation is required to delete a table."}), 400
    try:
        result = drop_table(table_name)
        return jsonify({"success": True, "message": f"Table '{table_name}' deleted successfully.", "result": result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/workspace/sample-data")
def sample_data_endpoint():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    try:
        rows = int(payload.get("rows_per_table") or payload.get("rows") or 10)
        selected = payload.get("tables") or payload.get("selected_tables") or None
        result = generate_sample_data(selected, rows, payload.get("manual_rows") or {})
        return jsonify({"success": True, **result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/workspace/random-schema/preview")
def random_schema_preview():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    try:
        result = preview_random_schema(
            theme=payload.get("theme", "random"),
            table_count=payload.get("table_count", 4),
            columns_per_table=payload.get("columns_per_table", 5),
            relationships=payload.get("relationships", True),
            mode=payload.get("mode", "add"),
        )
        return jsonify({"success": True, **result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/workspace/random-schema/create")
def random_schema_create():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    try:
        result = create_random_schema(
            tables=payload.get("tables"),
            mode=payload.get("mode", "add"),
            confirm_replace=payload.get("confirm_replace") is True,
            rows_per_table=payload.get("rows_per_table", 0),
            generate_samples=payload.get("generate_samples") is True,
        )
        return jsonify({"success": True, **result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/workspace/reset")
def reset_workspace_endpoint():
    payload = request.get_json(silent=True)
    if not request.is_json or not isinstance(payload, dict) or payload.get("confirm_reset") is not True:
        return jsonify({"error": "Explicit confirmation is required to reset the playground database."}), 400
    try:
        return jsonify(reset_workspace())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/run-query")
@app.post("/api/execute")
def run_query():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        return jsonify({"error": "'query' must be a non-empty string."}), 400
    try:
        analysis = analyze_query(query)
        security_blocked = any(
            finding["severity"] == "HIGH"
            for finding in analysis["security_findings"]
        )
        if analysis["overall_status"] != "passed" or security_blocked:
            return jsonify({
                "success": False,
                "blocked": True,
                "error": (
                    "A high-severity security finding blocks execution in the playground."
                    if security_blocked else
                    "Query analysis did not pass validation, so it is not eligible to run in the playground."
                ),
                "analysis": analysis,
            }), 400
        result = execute_select_query(query)
        return jsonify({"success": True, "result": result, "analysis": analysis})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


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
