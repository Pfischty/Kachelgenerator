import io
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

import app as app_module  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(app_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(app_module, "DB_PATH", data_dir / "app.db")
    monkeypatch.setattr(app_module, "ICONS_DIR", data_dir / "icons")
    monkeypatch.setattr(app_module, "PREVIEWS_DIR", data_dir / "previews")
    monkeypatch.setattr(app_module, "RENDERS_DIR", data_dir / "renders")
    monkeypatch.setattr(app_module, "STORAGE_READY", False)
    app_module.init_storage()
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as test_client:
        yield test_client


def test_colors_endpoint(client):
    response = client.get("/api/colors")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload
    assert all("hex" in row for row in payload)


def test_render_requires_color(client):
    response = client.post("/api/render", json={})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing color"


def test_render_invalid_color(client):
    response = client.post("/api/render", json={"color_hex": "123456"})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid color hex"


def test_render_happy_path(client):
    response = client.post(
        "/api/render",
        json={
            "name": "Demo",
            "color_hex": "#4ccd4f",
            "text": "Hello",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert "render_id" in payload
    download = client.get(payload["download_url"])
    assert download.status_code == 200
    assert download.mimetype == "image/png"


def test_layout_preset_requires_fields(client):
    response = client.post("/api/layout-presets", json={"name": "Missing"})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing name or params"


def test_layout_preset_lifecycle(client):
    response = client.post(
        "/api/layout-presets",
        json={
            "name": "Custom",
            "params": {"corner_radius_px": 10},
        },
    )
    assert response.status_code == 201
    preset_id = response.get_json()["id"]

    update = client.put(
        f"/api/layout-presets/{preset_id}",
        json={
            "name": "Updated",
            "params": {"corner_radius_px": 12},
        },
    )
    assert update.status_code == 200
    assert update.get_json()["status"] == "updated"

    delete = client.delete(f"/api/layout-presets/{preset_id}")
    assert delete.status_code == 200
    assert delete.get_json()["status"] == "deleted"


def _make_png_bytes():
    image = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
    payload = io.BytesIO()
    image.save(payload, format="PNG")
    payload.seek(0)
    return payload


def test_icon_upload_list_and_delete(client):
    payload = _make_png_bytes()
    response = client.post(
        "/api/icons",
        data={
            "name": "Test Icon",
            "tags": "sample,icon",
            "file": (payload, "icon.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    icon_id = response.get_json()["id"]

    list_response = client.get("/api/icons")
    assert list_response.status_code == 200
    icons = list_response.get_json()
    assert any(icon["id"] == icon_id for icon in icons)

    preview = client.get(f"/api/icons/{icon_id}/preview")
    assert preview.status_code == 200
    assert preview.mimetype == "image/png"

    delete = client.delete(f"/api/icons/{icon_id}")
    assert delete.status_code == 200
    assert delete.get_json()["status"] == "deleted"
