"""Small web app that shows the report kits and uploads them to The_New_App platform.

Connect once a day with an admin account; the login token is then valid for 24 hours (also for the
daily auto upload). Grouping rules are in report_groups.py, platform calls in platform_client.py.

Run:  .venv/bin/python webapp/app.py   then open http://127.0.0.1:8090
"""

import argparse
import sys
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import platform_client as pc  # noqa: E402
import report_groups as rg  # noqa: E402

app = Flask(__name__)


def groups_for(folder: str, platform: str) -> list[dict]:
    try:
        return rg.build_groups(folder, pc.load_history(platform))
    except ValueError:
        abort(400, "Unknown input folder")


@app.get("/")
def home():
    return render_template("index.html", folders=rg.input_folders(), platforms=pc.PLATFORMS,
                           input_dir=str(rg.INPUT_DIR), output_dir=str(rg.OUTPUT_DIR))


@app.get("/api/session")
def api_session():
    return jsonify(pc.public_session(pc.load_session()))


@app.post("/api/connect")
def api_connect():
    body = request.get_json(force=True)
    try:
        session = pc.login(body.get("platform", ""), body.get("username", "").strip(), body.get("password", ""))
    except pc.PlatformError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(pc.public_session(session))


@app.post("/api/disconnect")
def api_disconnect():
    pc.logout()
    return jsonify(pc.public_session(None))


@app.get("/api/groups")
def api_groups():
    return jsonify(groups_for(request.args.get("folder", "."), request.args.get("platform", "local")))


@app.post("/api/upload-kit")
def api_upload_kit():
    """Upload one kit. The page calls this once per kit so it can show progress."""
    session = pc.load_session()
    if not session:
        return jsonify({"error": "Not connected. Please connect to the platform first."}), 401
    body = request.get_json(force=True)
    group = next((g for g in groups_for(body.get("folder", "."), session["platform"]) if g["id"] == body.get("id")), None)
    if group is None:
        return jsonify({"error": "Kit not found"}), 404
    if not group["files"]:
        return jsonify({"error": "This kit has no reports to upload yet"}), 400
    try:
        result = pc.upload_kit(session, group)
    except pc.NotConnected as e:
        return jsonify({"error": str(e)}), 401
    except pc.PlatformError as e:
        return jsonify({"error": str(e)}), 502
    pc.record_result(session["platform"], group["id"], result)
    return jsonify({"id": group["id"], **result})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    app.run(host="127.0.0.1", port=args.port, debug=False)
