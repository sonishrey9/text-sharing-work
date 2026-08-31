from __future__ import annotations

import hmac
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import (
    Flask,
    Response,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_socketio import SocketIO, disconnect, emit
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "gif", "txt", "pdf", "docx"})
DEFAULT_MAX_TEXT_LENGTH = 100_000
DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024

socketio = SocketIO(async_mode="threading")


def _environment_flag(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def allowed_file(filename: str) -> bool:
    """Return whether a filename has one of the explicitly allowed extensions."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _session_is_current_unlocked() -> bool:
    return (
        session.get("authenticated") is True
        and session.get("auth_generation") == current_app.extensions["auth_generation"]
    )


def _session_is_current() -> bool:
    with current_app.extensions["state_lock"]:
        return _session_is_current_unlocked()


def create_app(test_config: Mapping[str, Any] | None = None) -> Flask:
    """Create the text-sharing application from environment-backed configuration."""
    app = Flask(__name__)
    app.config.from_mapping(
        AUTH_PASSWORD=os.environ.get("AUTH_PASSWORD"),
        MAX_CONTENT_LENGTH=DEFAULT_MAX_UPLOAD_BYTES,
        MAX_TEXT_LENGTH=DEFAULT_MAX_TEXT_LENGTH,
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_environment_flag("SESSION_COOKIE_SECURE"),
        UPLOAD_FOLDER=os.environ.get(
            "UPLOAD_FOLDER", str(Path(app.root_path) / "uploads")
        ),
    )
    if test_config:
        app.config.update(test_config)

    if not app.config["TESTING"]:
        if not (app.config["AUTH_PASSWORD"] and app.config["SECRET_KEY"]):
            raise RuntimeError("AUTH_PASSWORD and SECRET_KEY must be configured.")
        if len(str(app.config["AUTH_PASSWORD"])) < 16:
            raise RuntimeError("AUTH_PASSWORD must be at least 16 characters.")

    upload_folder = Path(app.config["UPLOAD_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)
    app.extensions["shared_text"] = {"text": ""}
    app.extensions["auth_generation"] = 0
    app.extensions["state_lock"] = threading.Lock()
    app.extensions["emit_lock"] = threading.Lock()

    socketio.init_app(app, cors_allowed_origins=None)

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.socket.io; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; "
            "img-src 'self' data: blob:; "
            "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        )
        return response

    @app.get("/health")
    def health() -> ResponseReturnValue:
        return jsonify({"status": "ok"}), 200

    @app.get("/")
    def index() -> ResponseReturnValue:
        if _session_is_current():
            return render_template("index.html")
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login() -> ResponseReturnValue:
        if request.method == "POST":
            supplied_password = request.form.get("password", "")
            configured_password = str(current_app.config["AUTH_PASSWORD"] or "")
            if configured_password and hmac.compare_digest(
                supplied_password, configured_password
            ):
                with current_app.extensions["state_lock"]:
                    session.clear()
                    session["authenticated"] = True
                    session["auth_generation"] = current_app.extensions[
                        "auth_generation"
                    ]
                return redirect(url_for("index"))
            return render_template(
                "login.html", error="Incorrect password. Please try again."
            ), 401
        return render_template("login.html")

    @app.post("/logout")
    def logout() -> ResponseReturnValue:
        with current_app.extensions["state_lock"]:
            if _session_is_current_unlocked():
                current_app.extensions["auth_generation"] += 1
            session.clear()
        return redirect(url_for("login"))

    @app.post("/upload")
    def upload_file() -> ResponseReturnValue:
        if not _session_is_current():
            return jsonify({"error": "Unauthorized"}), 403

        file = request.files.get("file")
        if file is None:
            return jsonify({"error": "No file part"}), 400
        if not file.filename:
            return jsonify({"error": "No selected file"}), 400
        if not allowed_file(file.filename):
            return jsonify({"error": "Invalid file type"}), 400

        filename = secure_filename(file.filename)
        if not filename:
            return jsonify({"error": "Invalid filename"}), 400

        stored_filename = f"{uuid4().hex}{Path(filename).suffix.lower()}"
        file.save(upload_folder / stored_filename)
        file_url = url_for(
            "uploaded_file",
            stored_filename=stored_filename,
            download_name=filename,
        )
        payload = {"file_url": file_url, "file_name": filename}
        with current_app.extensions["emit_lock"]:
            socketio.emit("file_shared", payload)
        return jsonify(payload), 200

    @app.get("/uploads/<stored_filename>/<download_name>")
    def uploaded_file(stored_filename: str, download_name: str) -> ResponseReturnValue:
        if not _session_is_current():
            return jsonify({"error": "Unauthorized"}), 403
        safe_download_name = secure_filename(download_name)
        if not safe_download_name or not allowed_file(safe_download_name):
            abort(404)
        return send_from_directory(
            upload_folder,
            stored_filename,
            as_attachment=True,
            download_name=safe_download_name,
        )

    return app


@socketio.on("connect")
def handle_connect(auth: Mapping[str, Any] | None = None) -> bool | None:
    del auth
    if not _session_is_current():
        return False
    return None


@socketio.on("update_text")
def handle_update_text(data: Any) -> None:
    with current_app.extensions["state_lock"]:
        if not _session_is_current_unlocked():
            with current_app.extensions["emit_lock"]:
                disconnect()
            return
        if not isinstance(data, dict) or not isinstance(data.get("text"), str):
            with current_app.extensions["emit_lock"]:
                emit("share_error", {"message": "Text must be a string."})
            return

        text = data["text"]
        if len(text) > int(current_app.config["MAX_TEXT_LENGTH"]):
            with current_app.extensions["emit_lock"]:
                emit("share_error", {"message": "Text is too long."})
            return

        current_app.extensions["shared_text"]["text"] = text
        with current_app.extensions["emit_lock"]:
            socketio.emit("text_update", text)


@socketio.on("fetch_text")
def handle_fetch_text() -> None:
    with current_app.extensions["state_lock"]:
        if not _session_is_current_unlocked():
            with current_app.extensions["emit_lock"]:
                disconnect()
            return
        with current_app.extensions["emit_lock"]:
            socketio.emit(
                "text_update",
                current_app.extensions["shared_text"]["text"],
                to=getattr(request, "sid"),
            )


app = create_app()


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
