# Anon

A local desktop app that anonymizes sensitive data in documents before sharing them. Runs entirely on your machine — **no data leaves your computer**.

Detects names, organizations, and locations using AI, replaces them with placeholders, and scrambles numbers. You can restore the original data later with a bridge key.

---

## Prerequisites

- **Python 3.8 or newer**
- **pip** (usually included with Python)

### Linux
```bash
sudo apt install python3-venv python3-pip   # Debian / Ubuntu
sudo dnf install python3-virtualenv          # Fedora
sudo pacman -S python-virtualenv             # Arch
```

### Windows
1. Download Python from [python.org](https://python.org) — **check** "Add Python to PATH" during install
2. Open **Command Prompt** or **PowerShell** (no admin needed)

---

## Quick Start

```bash
# Linux
python3 run.py

# Windows
python run.py
```

This single command:
1. Creates a virtual environment (`venv/`)
2. Installs all Python dependencies
3. Downloads NER models into `models/` (~700 MB total, one-time)
4. Starts the web server at **http://localhost:8000**
5. Opens your browser

The first run downloads models and may take **5–15 minutes** depending on your connection. Subsequent runs start immediately.

---

## Docker Quick Start

The application is completely containerised. The Dockerfile compiles build dependencies and bakes the AI model layers directly into the image so it can run strictly offline.

```bash
# Clone and spin up the stack
docker compose up -d --build
```

This single command:
- Builds the `python:3.11-slim` stack
- Fetches GLiNER and spaCy models into the layer cache during build
- Sets `HF_HUB_OFFLINE=1` ensuring no unexpected runtime outbound connections
- Exposes the app at **http://localhost:8000**

To tear down the container:

```bash
docker compose down
```

### Container Environment Variables

These variables are defined inside the `Dockerfile` to govern execution limits:

| Variable | Default | Purpose |
|----------|---------|---------|
| `PYTHONDONTWRITEBYTECODE` | `1` | Prevents Python from writing `.pyc` files to disk |
| `PYTHONUNBUFFERED` | `1` | Forces stdout/stderr to be unbuffered for instant Docker logging |
| `HF_HUB_OFFLINE` | `1` | Blocks Hugging Face transformers from attempting telemetry/network checks |
| `HOST` | `0.0.0.0` | Binds server to all interfaces inside the container virtual network boundary |
| `PORT` | `8000` | Target port allocation |

---

## Manual Setup

If the one-command launcher doesn't work for your system:

```bash
# 1. Create virtual environment
python3 -m venv venv          # Linux
python -m venv venv           # Windows

# 2. Activate it
source venv/bin/activate      # Linux
venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r backend/requirements.txt

# 4. Download NER models
python -c "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_medium-v2.1', cache_dir='models')"
python -m spacy download en_core_web_lg

# 5. Start the server
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open **http://localhost:8000** in your browser.

---

## How to Use

1. **Upload** a file (`.docx`, `.xlsx`, `.pdf`, `.pptx`)
2. **Review** detected entities (Person / Organization / Location)
3. **Choose** which entity types to anonymize and a number multiplier
4. **Download** the anonymized file + `.bridgekey.json`
5. **Restore** later by uploading the anonymized file and key

---

## Project Structure

```
anon/
├── run.py               # Cross-platform launcher (Linux / macOS / Windows)
├── .gitignore           # Ignores venv/, models/, temp/, __pycache__
├── backend/
│   ├── main.py          # FastAPI server — all API routes
│   ├── anonymizer.py    # NER engine: GLiNER + spaCy + regex
│   ├── file_handlers.py # Parse, anonymize & restore for each file format
│   ├── restorer.py      # Reverse placeholders using bridge key
│   └── requirements.txt # Python dependencies
├── frontend/
│   └── index.html       # Single-page web UI (vanilla JS, no build step)
├── models/              # Downloaded NER models (auto-created, gitignored)
└── temp/                # Processed files (auto-created, gitignored)
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web UI |
| `GET` | `/health` | Server + model status |
| `POST` | `/api/detect` | Detect entities in a file (returns preview) |
| `POST` | `/api/anonymize` | Anonymize a file (entity toggles + number multiplier) |
| `POST` | `/api/restore` | Restore from anonymized file + bridge key |
| `GET` | `/api/download/{filename}` | Download processed file |
| `POST` | `/api/cleanup` | Delete all temp files |

---

## Bridge Key Format

```json
{
  "app": "Anon Bridge",
  "version": "2.0",
  "multiplier": 3.7,
  "created_at": "2026-05-12T10:30:00",
  "original_filename": "report.docx",
  "entities": {
    "PERSON_1": "John Doe",
    "ORG_1": "Acme Corp",
    "LOC_1": "New York"
  },
  "number_mappings": {
    "15000": 55500.0,
    "23400": 86580.0
  }
}
```

The bridge key is the **only way** to reverse anonymization. Keep it safe.

---

## NER Engine

| Stage | Model | Role |
|-------|-------|------|
| Primary | [GLiNER](https://github.com/urchade/GLiNER) `gliner_medium-v2.1` | Detects Person, Organization, Location (threshold 0.3) |
| Fallback | [spaCy](https://spacy.io/) `en_core_web_lg` | Catches anything GLiNER misses |
| Regex | Keyword matching | Detects company names containing Ltd, Inc, Corp, etc. |

Both models are downloaded once into `models/` and run entirely locally.

---

## Supported File Types

| Type | Library | Anonymization approach |
|------|---------|----------------------|
| Word (`.docx`) | `python-docx` | Run-level text replacement, preserves formatting |
| Excel (`.xlsx`) | `openpyxl` | Cell-level string + numeric replacement |
| PDF (`.pdf`) | `pdfplumber` + `PyMuPDF` | Text extraction via pdfplumber, redaction via PyMuPDF annotations |
| PowerPoint (`.pptx`) | `python-pptx` | Run-level text replacement in slides, text frames, and tables |
| Raw text (paste) | N/A | Placeholder replacement in pasted text |

---

## Troubleshooting

### `ensurepip` is not available
```bash
# Debian / Ubuntu
sudo apt install python3-venv

# Fedora
sudo dnf install python3-virtualenv

# Arch
sudo pacman -S python-virtualenv
```

### GLiNER model download fails
- Check your internet connection
- The model is ~200 MB. On slow connections, increase the timeout in `run.py`
- The model is cached in `models/` — delete that folder to force a fresh download

### spaCy model download fails
```bash
# Try installing via pip directly:
python -m pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl
```

### Port 8000 is already in use
```bash
# Kill the process using port 8000:
# Linux
lsof -ti:8000 | xargs kill

# Windows (PowerShell as admin)
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess -Force
```

### "Python not found" on Windows
Make sure you checked **"Add Python to PATH"** during installation. Reinstall Python from [python.org](https://python.org) if needed.

---

## License

MIT
