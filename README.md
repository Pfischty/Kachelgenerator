# Kachelgenerator MVP

Lokaler MVP für das Erstellen von 450×450 PNG-Kacheln mit transparenten, abgerundeten Ecken, Farb-Presets, Icon-Upload, Layout-Presets und Verlauf.

## Quickstart (lokal)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Öffne dann <http://localhost:5000>.

## Features (MVP)

- PNG-Export 450×450 px, sRGB, Alpha + abgerundete Ecken.
- Farb-Presets + Custom Hex.
- Icon-Upload (SVG/PNG) mit Preview.
- Drag & Drop für Icon/Text, Slider für Scale/Font-Size.
- Layout-Presets speichern/laden.
- Verlauf inkl. Download.

## Deployment (Docker)

```bash
docker build -t kachelgenerator .
docker run -p 5000:5000 kachelgenerator
```

## Datenhaltung

Alle Daten werden lokal im Ordner `data/` gespeichert (SQLite + Dateien).
