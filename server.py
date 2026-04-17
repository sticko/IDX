from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import os, sys

sys.path.insert(0, os.path.dirname(__file__))

from idx_fetcher import fetch_idx_pdf
from pdf_parser import parse_shareholder_pdf

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)


@app.route("/health")
def health():
    return "ok", 200


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/fetch", methods=["POST"])
def fetch():
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
        result = fetch_idx_pdf(exact_date=exact_date)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"Fetch error: {e}"}), 500

    try:
        log_messages = []
        df = parse_shareholder_pdf(result["savedPath"],
                                   log_callback=lambda m: log_messages.append(m))
    except Exception as e:
        return jsonify({"error": f"Parse error: {e}"}), 500

    rows = df.where(df.notna(), None).to_dict(orient="records")
    columns = list(df.columns)

    return jsonify({
        "meta": {
            "title": result.get("title"),
            "announcementDate": result.get("announcementDate"),
            "fileName": result.get("fileName"),
        },
        "columns": columns,
        "rows": rows,
        "totalRows": len(rows),
        "logs": log_messages,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
