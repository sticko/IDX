import os, sys, traceback
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.makedirs("downloads", exist_ok=True)
os.makedirs("results", exist_ok=True)
os.makedirs("static", exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB
CORS(app)

_fetch_idx_pdf = None
_parse_shareholder_pdf = None
_import_error = None

def _lazy_import():
    global _fetch_idx_pdf, _parse_shareholder_pdf, _import_error
    if _parse_shareholder_pdf is not None:
        return True
    try:
        from idx_fetcher import fetch_idx_pdf
        from pdf_parser import parse_shareholder_pdf
        _fetch_idx_pdf = fetch_idx_pdf
        _parse_shareholder_pdf = parse_shareholder_pdf
        return True
    except Exception as e:
        _import_error = f"{e}\n{traceback.format_exc()}"
        print(f"[IMPORT ERROR] {_import_error}", flush=True)
        return False


@app.route("/health")
def health():
    return "ok", 200


@app.route("/")
def index():
    if os.path.exists(os.path.join("static", "index.html")):
        return send_from_directory("static", "index.html")
    return "<h1>IDX Parser</h1><p>Static index.html not found.</p>", 200


@app.route("/api/fetch", methods=["POST"])
def fetch():
    if not _lazy_import():
        return jsonify({"error": f"Server module failed to load: {_import_error}"}), 500

    body = request.get_json(force=True, silent=True) or {}
    mode = body.get("mode", "latest")
    exact_date = None

    if mode == "exact":
        raw = body.get("date", "").strip()
        if not raw:
            return jsonify({"error": "Date is required for exact mode"}), 400
        from datetime import datetime
        try:
            exact_date = datetime.strptime(raw, "%Y-%m-%d").strftime("%Y%m%d")
        except ValueError:
            return jsonify({"error": "Date must be YYYY-MM-DD"}), 400

    try:
        result = _fetch_idx_pdf(exact_date=exact_date)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"Fetch error: {e}"}), 500

    return _parse_and_respond(result["savedPath"], meta={
        "title": result.get("title"),
        "announcementDate": result.get("announcementDate"),
        "fileName": result.get("fileName"),
    })


@app.route("/api/upload", methods=["POST"])
def upload():
    if not _lazy_import():
        return jsonify({"error": f"Server module failed to load: {_import_error}"}), 500

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Use form field 'file'."}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are allowed"}), 400

    safe_name = os.path.basename(f.filename).replace(" ", "_")
    save_path = os.path.join("downloads", safe_name)
    try:
        f.save(save_path)
    except Exception as e:
        return jsonify({"error": f"Failed to save file: {e}"}), 500

    return _parse_and_respond(save_path, meta={
        "title": "Manual upload",
        "announcementDate": "",
        "fileName": safe_name,
    })


def _parse_and_respond(pdf_path, meta):
    try:
        log_messages = []
        df = _parse_shareholder_pdf(pdf_path, log_callback=lambda m: log_messages.append(m))
    except Exception as e:
        return jsonify({"error": f"Parse error: {e}\n{traceback.format_exc()}"}), 500

    rows = df.where(df.notna(), None).to_dict(orient="records")
    columns = list(df.columns)

    return jsonify({
        "meta": meta,
        "columns": columns,
        "rows": rows,
        "totalRows": len(rows),
        "logs": log_messages,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
