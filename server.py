import os, sys, traceback
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.makedirs("downloads", exist_ok=True)
os.makedirs("results", exist_ok=True)
os.makedirs("static", exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload cap
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


def _df_to_response(df, meta, logs):
    rows = df.where(df.notna(), None).to_dict(orient="records")
    return jsonify({
        "meta": meta,
        "columns": list(df.columns),
        "rows": rows,
        "totalRows": len(rows),
        "logs": logs,
    })


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

    try:
        logs = []
        df = _parse_shareholder_pdf(result["savedPath"],
                                    log_callback=lambda m: logs.append(m))
    except Exception as e:
        return jsonify({"error": f"Parse error: {e}"}), 500

    return _df_to_response(df, {
        "title": result.get("title"),
        "announcementDate": result.get("announcementDate"),
        "fileName": result.get("fileName"),
    }, logs)


@app.route("/api/upload", methods=["POST"])
def upload():
    """Parse an uploaded PDF instead of fetching from IDX."""
    if not _lazy_import():
        return jsonify({"error": f"Server module failed to load: {_import_error}"}), 500

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "File must be a PDF"}), 400

    filename = secure_filename(f.filename)
    save_path = os.path.join("downloads", filename)
    f.save(save_path)

    try:
        logs = []
        df = _parse_shareholder_pdf(save_path,
                                    log_callback=lambda m: logs.append(m))
    except Exception as e:
        return jsonify({"error": f"Parse error: {e}"}), 500

    return _df_to_response(df, {
        "title": "Uploaded PDF",
        "announcementDate": "",
        "fileName": filename,
    }, logs)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
