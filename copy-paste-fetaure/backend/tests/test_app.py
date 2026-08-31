import io
import os
import threading
from pathlib import Path

import pytest

os.environ.setdefault("AUTH_PASSWORD", "test-password-long-enough")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough")

from app import create_app, socketio  # noqa: E402


@pytest.fixture()
def app(tmp_path: Path):
    return create_app(
        {
            "TESTING": True,
            "AUTH_PASSWORD": "correct-horse",
            "SECRET_KEY": "test-secret-key-that-is-long-enough",
            "SESSION_COOKIE_SECURE": False,
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "MAX_TEXT_LENGTH": 100,
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()


def log_in(client) -> None:
    response = client.post("/login", data={"password": "correct-horse"})
    assert response.status_code == 302


def test_health_check_is_public(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
    assert response.headers["Content-Security-Policy"].startswith("default-src 'self'")


def test_index_requires_login(client) -> None:
    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_login_rejects_wrong_password_without_echoing_it(client) -> None:
    response = client.post("/login", data={"password": "wrong-password"})

    assert response.status_code == 401
    assert b"Incorrect password" in response.data
    assert b"wrong-password" not in response.data


def test_login_unlocks_index_and_logout_locks_it_again(client) -> None:
    log_in(client)

    index = client.get("/")
    assert index.status_code == 200
    assert b'integrity="sha384-' in index.data
    assert client.post("/logout").status_code == 302
    assert client.get("/").status_code == 302


def test_unauthenticated_socket_connection_is_rejected(app) -> None:
    realtime_client = socketio.test_client(app)

    assert not realtime_client.is_connected()


def test_authenticated_clients_share_text(app) -> None:
    first_http_client = app.test_client()
    second_http_client = app.test_client()
    log_in(first_http_client)
    log_in(second_http_client)
    first = socketio.test_client(app, flask_test_client=first_http_client)
    second = socketio.test_client(app, flask_test_client=second_http_client)

    assert first.is_connected()
    assert second.is_connected()
    first.get_received()
    second.get_received()

    first.emit("update_text", {"text": "copy this"})

    assert {
        "name": "text_update",
        "args": ["copy this"],
        "namespace": "/",
    } in second.get_received()

    second.emit("fetch_text")
    assert {
        "name": "text_update",
        "args": ["copy this"],
        "namespace": "/",
    } in second.get_received()


def test_logout_revokes_an_existing_socket(app) -> None:
    http_client = app.test_client()
    log_in(http_client)
    realtime_client = socketio.test_client(app, flask_test_client=http_client)
    assert realtime_client.is_connected()

    http_client.post("/logout")
    realtime_client.emit("update_text", {"text": "must not be accepted"})

    assert not realtime_client.is_connected()


def test_unauthenticated_logout_does_not_revoke_other_sessions(app) -> None:
    authenticated_http_client = app.test_client()
    unauthenticated_http_client = app.test_client()
    log_in(authenticated_http_client)
    realtime_client = socketio.test_client(
        app, flask_test_client=authenticated_http_client
    )

    assert unauthenticated_http_client.post("/logout").status_code == 302
    realtime_client.emit("update_text", {"text": "still authorized"})

    assert realtime_client.is_connected()
    assert app.extensions["shared_text"]["text"] == "still authorized"


def test_concurrent_updates_leave_clients_consistent_with_server_state(
    app, monkeypatch
) -> None:
    first_http_client = app.test_client()
    second_http_client = app.test_client()
    log_in(first_http_client)
    log_in(second_http_client)
    first = socketio.test_client(app, flask_test_client=first_http_client)
    second = socketio.test_client(app, flask_test_client=second_http_client)

    first_inside_emit = threading.Event()
    second_inside_emit = threading.Event()
    release_first_emit = threading.Event()
    observed_updates: list[str] = []
    original_emit = socketio.server.emit

    def controlled_emit(event, data=None, *args, **kwargs) -> None:
        if event == "text_update" and data == "first":
            first_inside_emit.set()
            assert release_first_emit.wait(timeout=2)
        elif event == "text_update" and data == "second":
            second_inside_emit.set()
        if event == "text_update":
            observed_updates.append(data)
        original_emit(event, data, *args, **kwargs)

    monkeypatch.setattr(socketio.server, "emit", controlled_emit)
    first_thread = threading.Thread(
        target=first.emit, args=("update_text", {"text": "first"})
    )
    second_thread = threading.Thread(
        target=second.emit, args=("update_text", {"text": "second"})
    )

    first_thread.start()
    assert first_inside_emit.wait(timeout=1)
    second_thread.start()
    second_inside_emit.wait(timeout=0.25)
    release_first_emit.set()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert observed_updates[-1] == app.extensions["shared_text"]["text"]


def test_oversized_text_is_rejected_without_replacing_current_text(app) -> None:
    http_client = app.test_client()
    log_in(http_client)
    realtime_client = socketio.test_client(app, flask_test_client=http_client)
    realtime_client.emit("update_text", {"text": "keep me"})
    realtime_client.get_received()

    realtime_client.emit("update_text", {"text": "x" * 101})

    assert {
        "name": "share_error",
        "args": [{"message": "Text is too long."}],
        "namespace": "/",
    } in realtime_client.get_received()
    realtime_client.emit("fetch_text")
    assert {
        "name": "text_update",
        "args": ["keep me"],
        "namespace": "/",
    } in realtime_client.get_received()


def test_upload_and_download_require_login(app, client) -> None:
    assert client.post("/upload").status_code == 403
    assert client.get(f"/uploads/{'0' * 32}.txt/note.txt").status_code == 403

    log_in(client)
    upload = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"hello"), "note.txt")},
        content_type="multipart/form-data",
    )

    assert upload.status_code == 200
    payload = upload.get_json()
    assert payload["file_name"] == "note.txt"
    assert payload["file_url"].endswith("/note.txt")
    download = client.get(payload["file_url"])
    assert download.status_code == 200
    assert download.data == b"hello"


def test_upload_rejects_disallowed_file_type(client) -> None:
    log_in(client)

    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"unsafe"), "script.html")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid file type"}


def test_same_named_uploads_get_distinct_urls_and_keep_both_files(client) -> None:
    log_in(client)
    first = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"first"), "note.txt")},
        content_type="multipart/form-data",
    ).get_json()
    second = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"second"), "note.txt")},
        content_type="multipart/form-data",
    ).get_json()

    assert first["file_url"] != second["file_url"]
    assert client.get(first["file_url"]).data == b"first"
    assert client.get(second["file_url"]).data == b"second"


def test_production_configuration_requires_secrets(monkeypatch) -> None:
    monkeypatch.delenv("AUTH_PASSWORD", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="AUTH_PASSWORD and SECRET_KEY"):
        create_app({"TESTING": False})


def test_production_configuration_rejects_a_weak_password(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_PASSWORD", "too-short")
    monkeypatch.setenv("SECRET_KEY", "production-secret-key-that-is-long-enough")

    with pytest.raises(RuntimeError, match="at least 16 characters"):
        create_app({"TESTING": False})
