"""
Flask web dashboard for the TikTok → YouTube Shorts automation.
Run with: python app.py  (dev)  or  gunicorn app:app  (production/Railway)
"""
import json
import logging
import os
import queue
import threading
from datetime import date
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_from_directory, stream_with_context

import db
import pipeline
import scheduler

# ──────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────
LOG_FILE = os.environ.get("LOG_FILE", "auto_runner.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("app")

# ──────────────────────────────────────────────
# Flask app
# ──────────────────────────────────────────────
app = Flask(__name__)

# In-memory log queue for SSE streaming (last 200 lines)
_log_lines: list[str] = []
_log_lock = threading.Lock()
_sse_queues: list[queue.Queue] = []


def _add_log(msg: str):
    with _log_lock:
        _log_lines.append(msg)
        if len(_log_lines) > 200:
            _log_lines.pop(0)
        for q in list(_sse_queues):
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass


# ──────────────────────────────────────────────
# Startup: init DB and start scheduler
# ──────────────────────────────────────────────
def _pipeline_with_log():
    pipeline.run_pipeline(log_callback=_add_log)


with app.app_context():
    db.init_db()
    try:
        settings = pipeline.load_settings()
        upload_times = settings.get("upload_times", "08:00,14:00,20:00")
        scheduler.reschedule(upload_times, _pipeline_with_log)
        logger.info("Scheduler initialised with times: %s", upload_times)
    except Exception as e:
        logger.warning("Could not load settings on startup: %s", e)


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    try:
        settings = pipeline.load_settings()
    except Exception:
        settings = {}
    today_count = db.get_daily_count(date.today().isoformat())
    limit = int(settings.get("upload_limit_per_day", 3))
    next_runs = scheduler.get_next_run_times()
    return jsonify({
        "today_uploads": today_count,
        "daily_limit": limit,
        "next_runs": next_runs,
        "youtube_authed": os.path.exists(pipeline.TOKEN_FILE),
    })


@app.route("/api/history")
def api_history():
    rows = db.get_recent_uploads(50)
    return jsonify(rows)


@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    try:
        with open(pipeline.SETTINGS_FILE, "r") as f:
            return jsonify(json.load(f))
    except FileNotFoundError:
        return jsonify({})


@app.route("/api/settings", methods=["POST"])
def api_settings_save():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON"}), 400

    # Load existing settings and merge
    try:
        with open(pipeline.SETTINGS_FILE, "r") as f:
            existing = json.load(f)
    except Exception:
        existing = {}
    existing.update(data)

    with open(pipeline.SETTINGS_FILE, "w") as f:
        json.dump(existing, f, indent=2)

    # Re-apply schedule
    upload_times = existing.get("upload_times", "08:00,14:00,20:00")
    scheduler.reschedule(upload_times, _pipeline_with_log)
    logger.info("Settings saved, scheduler updated with times: %s", upload_times)
    return jsonify({"ok": True})


@app.route("/api/run-now", methods=["POST"])
def api_run_now():
    threading.Thread(target=_pipeline_with_log, daemon=True).start()
    _add_log("[manual] Pipeline triggered manually")
    return jsonify({"ok": True, "message": "Pipeline started"})


@app.route("/api/logs")
def api_logs():
    """SSE endpoint — stream log lines in real time."""
    def event_stream():
        q: queue.Queue = queue.Queue(maxsize=100)
        with _log_lock:
            _sse_queues.append(q)
            # Send existing lines first
            for line in _log_lines[-50:]:
                yield f"data: {line}\n\n"
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    yield ": heartbeat\n\n"
        finally:
            with _log_lock:
                if q in _sse_queues:
                    _sse_queues.remove(q)

    return Response(stream_with_context(event_stream()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ──────────────────────────────────────────────
# Video file serving (used by Instagram API to fetch video)
# ──────────────────────────────────────────────
@app.route("/videos/<path:filename>")
def serve_video(filename):
    """
    Serve a converted video file so Instagram can fetch it via public URL.
    Only files from the output folder are served.
    Set PUBLIC_BASE_URL env var to your Railway app URL so Instagram knows
    where to fetch: https://your-app.railway.app/videos/<filename>
    """
    try:
        settings = pipeline.load_settings()
    except Exception:
        settings = {}
    output_folder = os.path.abspath(settings.get("output_folder", "./output"))
    return send_from_directory(output_folder, filename)


# ──────────────────────────────────────────────
# YouTube OAuth routes
# ──────────────────────────────────────────────
_pending_flow = None  # in-memory; single-user app


@app.route("/auth")
def auth_page():
    """Show the auth URL for the user to visit."""
    global _pending_flow
    if not os.path.exists(pipeline.CLIENT_SECRETS):
        return "<h2>client_secrets.json not found on server.</h2>", 500
    auth_url, flow = pipeline.start_auth_flow()
    _pending_flow = flow
    return render_template("auth.html", auth_url=auth_url)


@app.route("/auth/callback", methods=["POST"])
def auth_callback():
    global _pending_flow
    code = request.form.get("code", "").strip()
    if not code or _pending_flow is None:
        return "<h2>Missing code or session expired. Go back and try again.</h2>", 400
    try:
        pipeline.finish_auth_flow(_pending_flow, code)
        _pending_flow = None
        return "<h2>YouTube authenticated! You can close this page.</h2><a href='/'>Back to dashboard</a>"
    except Exception as e:
        return f"<h2>Auth failed: {e}</h2>", 500


# ──────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
