import io
import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from PIL import Image, ImageDraw, ImageFont
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPM

APP_ROOT = Path(__file__).parent
DATA_DIR = APP_ROOT / "data"
DB_PATH = DATA_DIR / "app.db"
ICONS_DIR = DATA_DIR / "icons"
PREVIEWS_DIR = DATA_DIR / "previews"
RENDERS_DIR = DATA_DIR / "renders"

TILE_SIZE = 450
DEFAULT_RADIUS = 30

COLOR_PRESETS = [
    {"name": "AXE Green", "hex": "#4ccd4f"},
    {"name": "AXE Azure Blue", "hex": "#549fe9"},
    {"name": "AXE Indigo Blue", "hex": "#6870ef"},
    {"name": "AXE Ultra Violet", "hex": "#9051e4"},
    {"name": "AXE Berry Red", "hex": "#e74382"},
    {"name": "AXE Coral Red", "hex": "#e94a54"},
]

DEFAULT_LAYOUT = {
    "name": "Default",
    "corner_radius_px": DEFAULT_RADIUS,
    "icon": {"x": 300, "y": 170, "scale": 0.45},
    "text": {
        "x": 60,
        "y": 360,
        "font_size": 48,
        "font_weight": "semibold",
        "align": "left",
    },
}


STORAGE_READY = False


def get_db():
    if not STORAGE_READY:
        init_storage()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_storage():
    global STORAGE_READY
    DATA_DIR.mkdir(exist_ok=True)
    ICONS_DIR.mkdir(exist_ok=True)
    PREVIEWS_DIR.mkdir(exist_ok=True)
    RENDERS_DIR.mkdir(exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS icons (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                tags TEXT,
                file_path TEXT NOT NULL,
                preview_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS color_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                hex TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS layout_presets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                params TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS renders (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                icon_id TEXT,
                color_hex TEXT NOT NULL,
                layout_params TEXT NOT NULL,
                output_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        if conn.execute("SELECT COUNT(*) FROM color_presets").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO color_presets (name, hex) VALUES (?, ?)",
                [(preset["name"], preset["hex"]) for preset in COLOR_PRESETS],
            )
        if conn.execute("SELECT COUNT(*) FROM layout_presets").fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO layout_presets (id, name, params, created_at) VALUES (?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    DEFAULT_LAYOUT["name"],
                    json.dumps(DEFAULT_LAYOUT),
                    datetime.utcnow().isoformat(),
                ),
            )
    STORAGE_READY = True


app = Flask(__name__, static_folder="static", template_folder="templates")


def hex_to_rgba(hex_value):
    if not isinstance(hex_value, str):
        raise ValueError("Color must be string")
    hex_value = hex_value.strip()
    if not hex_value.startswith("#") or len(hex_value) != 7:
        raise ValueError("Invalid hex color")
    return tuple(int(hex_value[i : i + 2], 16) for i in (1, 3, 5)) + (255,)


def load_font(size, weight):
    try:
        if weight in {"bold", "semibold"}:
            return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def truncate_text(text, font, max_width):
    if font.getlength(text) <= max_width:
        return text
    ellipsis = "…"
    trimmed = text
    while trimmed and font.getlength(trimmed + ellipsis) > max_width:
        trimmed = trimmed[:-1]
    return trimmed + ellipsis if trimmed else ellipsis


def rasterize_icon(icon_path, size):
    suffix = Path(icon_path).suffix.lower()
    if suffix == ".svg":
        drawing = svg2rlg(str(icon_path))
        if drawing:
            renderPM.drawToFile(drawing, icon_path.replace('.svg', '.png'), fmt='PNG', dpi=96)
            image = Image.open(icon_path.replace('.svg', '.png')).convert("RGBA")
            if color_hex:
                try:
                    fill_color = hex_to_rgba(color_hex)
                except ValueError:
                    fill_color = None
                if fill_color:
                    alpha = image.getchannel("A")
                    colored = Image.new("RGBA", image.size, fill_color)
                    colored.putalpha(alpha)
                    image = colored
            return image.resize((size, size), Image.LANCZOS)
    image = Image.open(icon_path).convert("RGBA")
    return image.resize((size, size), Image.LANCZOS)


def render_tile(payload):
    color = payload["color_hex"]
    text = payload.get("text", "")
    layout = payload.get("layout", {})
    icon_info = payload.get("icon")

    base = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), hex_to_rgba(color))
    mask = Image.new("L", (TILE_SIZE, TILE_SIZE), 0)
    mask_draw = ImageDraw.Draw(mask)
    radius = int(layout.get("corner_radius_px", DEFAULT_RADIUS))
    mask_draw.rounded_rectangle(
        [0, 0, TILE_SIZE, TILE_SIZE], radius=radius, fill=255
    )
    base.putalpha(mask)

    if icon_info:
        icon_scale = float(icon_info.get("scale", 0.45))
        icon_size = max(1, int(TILE_SIZE * icon_scale))
        icon_image = rasterize_icon(icon_info["path"], icon_size)
        icon_x = int(icon_info.get("x", TILE_SIZE / 2) - icon_size / 2)
        icon_y = int(icon_info.get("y", TILE_SIZE / 2) - icon_size / 2)
        base.alpha_composite(icon_image, (icon_x, icon_y))

    if text:
        text_params = layout.get("text", {})
        font_size = int(text_params.get("font_size", 48))
        font_weight = text_params.get("font_weight", "semibold")
        font = load_font(font_size, font_weight)
        max_width = TILE_SIZE - int(text_params.get("x", 60)) - 40
        text_value = truncate_text(text, font, max_width)
        text_x = int(text_params.get("x", 60))
        text_y = int(text_params.get("y", 360))
        base_draw = ImageDraw.Draw(base)
        base_draw.text((text_x, text_y), text_value, font=font, fill=(255, 255, 255, 255))

    return base


@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


@app.route("/api/colors")
def get_colors():
    with get_db() as conn:
        rows = conn.execute("SELECT id, name, hex FROM color_presets").fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/icons", methods=["GET", "POST"])
def icons():
    if request.method == "POST":
        file = request.files.get("file")
        name = request.form.get("name", "")
        tags = request.form.get("tags", "")
        if not file or not name:
            return jsonify({"error": "Missing file or name"}), 400
        suffix = Path(file.filename).suffix.lower()
        if suffix not in {".svg", ".png"}:
            return jsonify({"error": "Only SVG or PNG supported"}), 400
        icon_id = str(uuid.uuid4())
        file_path = ICONS_DIR / f"{icon_id}{suffix}"
        file.save(file_path)
        preview_image = rasterize_icon(file_path, 256)
        preview_path = PREVIEWS_DIR / f"{icon_id}.png"
        preview_image.save(preview_path)
        with get_db() as conn:
            conn.execute(
                "INSERT INTO icons (id, name, tags, file_path, preview_path, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    icon_id,
                    name,
                    tags,
                    str(file_path),
                    str(preview_path),
                    datetime.utcnow().isoformat(),
                ),
            )
        return jsonify({"id": icon_id}), 201

    query = request.args.get("query", "").lower()
    tag = request.args.get("tag", "").lower()
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM icons ORDER BY created_at DESC").fetchall()
    results = []
    for row in rows:
        if query and query not in row["name"].lower():
            continue
        if tag and tag not in (row["tags"] or "").lower():
            continue
        results.append(
            {
                "id": row["id"],
                "name": row["name"],
                "tags": row["tags"],
                "preview_url": f"/api/icons/{row['id']}/preview",
            }
        )
    return jsonify(results)


@app.route("/api/icons/<icon_id>", methods=["DELETE"])
def delete_icon(icon_id):
    with get_db() as conn:
        row = conn.execute("SELECT file_path, preview_path FROM icons WHERE id = ?", (icon_id,)).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        conn.execute("DELETE FROM icons WHERE id = ?", (icon_id,))
    for path in [row["file_path"], row["preview_path"]]:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    return jsonify({"status": "deleted"})


@app.route("/api/icons/<icon_id>/preview")
def icon_preview(icon_id):
    with get_db() as conn:
        row = conn.execute("SELECT preview_path FROM icons WHERE id = ?", (icon_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return send_file(row["preview_path"], mimetype="image/png")


@app.route("/api/layout-presets", methods=["GET", "POST"])
def layout_presets():
    if request.method == "POST":
        payload = request.get_json(force=True)
        name = payload.get("name")
        params = payload.get("params")
        if not name or not params:
            return jsonify({"error": "Missing name or params"}), 400
        preset_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                "INSERT INTO layout_presets (id, name, params, created_at) VALUES (?, ?, ?, ?)",
                (preset_id, name, json.dumps(params), datetime.utcnow().isoformat()),
            )
        return jsonify({"id": preset_id}), 201

    with get_db() as conn:
        rows = conn.execute("SELECT * FROM layout_presets ORDER BY created_at DESC").fetchall()
    return jsonify(
        [
            {
                "id": row["id"],
                "name": row["name"],
                "params": json.loads(row["params"]),
            }
            for row in rows
        ]
    )


@app.route("/api/layout-presets/<preset_id>", methods=["PUT", "DELETE"])
def layout_preset_detail(preset_id):
    if request.method == "DELETE":
        with get_db() as conn:
            conn.execute("DELETE FROM layout_presets WHERE id = ?", (preset_id,))
        return jsonify({"status": "deleted"})

    payload = request.get_json(force=True)
    name = payload.get("name")
    params = payload.get("params")
    if not name or not params:
        return jsonify({"error": "Missing name or params"}), 400
    with get_db() as conn:
        conn.execute(
            "UPDATE layout_presets SET name = ?, params = ? WHERE id = ?",
            (name, json.dumps(params), preset_id),
        )
    return jsonify({"status": "updated"})


@app.route("/api/render", methods=["POST"])
def render_api():
    payload = request.get_json(force=True)
    name = payload.get("name", "kachel")
    color_hex = payload.get("color_hex")
    icon_id = payload.get("icon_id")
    layout = payload.get("layout_params", {})
    text = payload.get("text", "")

    if not color_hex:
        return jsonify({"error": "Missing color"}), 400
    try:
        hex_to_rgba(color_hex)
    except ValueError:
        return jsonify({"error": "Invalid color hex"}), 400

    icon_path = None
    if icon_id:
        with get_db() as conn:
            row = conn.execute("SELECT file_path FROM icons WHERE id = ?", (icon_id,)).fetchone()
        if row:
            icon_path = row["file_path"]

    layout_params = layout or DEFAULT_LAYOUT
    icon_payload = None
    if icon_path:
        icon_payload = {
            "path": icon_path,
            "x": layout_params.get("icon", {}).get("x", 300),
            "y": layout_params.get("icon", {}).get("y", 170),
            "scale": layout_params.get("icon", {}).get("scale", 0.45),
        }

    tile = render_tile(
        {
            "color_hex": color_hex,
            "text": text,
            "layout": layout_params,
            "icon": icon_payload,
        }
    )

    render_id = str(uuid.uuid4())
    output_path = RENDERS_DIR / f"{render_id}.png"
    tile.save(output_path, "PNG")

    with get_db() as conn:
        conn.execute(
            "INSERT INTO renders (id, name, icon_id, color_hex, layout_params, output_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                render_id,
                name,
                icon_id,
                color_hex,
                json.dumps({"layout": layout_params, "text": text}),
                str(output_path),
                datetime.utcnow().isoformat(),
            ),
        )

    return jsonify(
        {
            "render_id": render_id,
            "download_url": f"/api/renders/{render_id}/download",
            "thumbnail_url": f"/api/renders/{render_id}/download",
        }
    )


@app.route("/api/renders")
def renders():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM renders ORDER BY created_at DESC LIMIT 50").fetchall()
    return jsonify(
        [
            {
                "id": row["id"],
                "name": row["name"],
                "color_hex": row["color_hex"],
                "icon_id": row["icon_id"],
                "layout_params": json.loads(row["layout_params"]),
                "created_at": row["created_at"],
                "download_url": f"/api/renders/{row['id']}/download",
            }
            for row in rows
        ]
    )


@app.route("/api/renders/<render_id>/download")
def render_download(render_id):
    with get_db() as conn:
        row = conn.execute("SELECT output_path FROM renders WHERE id = ?", (render_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    as_attachment = request.args.get("download") == "1"
    return send_file(row["output_path"], mimetype="image/png", as_attachment=as_attachment)


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


if __name__ == "__main__":
    init_storage()
    app.run(host="0.0.0.0", port=5000, debug=True)
