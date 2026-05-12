# Anon

A local desktop application for anonymizing sensitive data before sending to AI models. Runs entirely on your machine — no data leaves your computer.

## How It Works

1. **Upload** a file (Excel `.xlsx`, Word `.docx`, PDF `.pdf`, or PowerPoint `.pptx`)
2. **Anonymize** — detects names, organizations, and locations using GLiNER (primary) + spaCy (fallback), replaces them with placeholders (`PERSON_1`, `ORG_1`, `LOC_1`), and multiplies all numbers by a factor you choose
3. **Output** — two files:
   - **Anonymized file** — safe to send anywhere
   - **Bridge key** (`.bridgekey.json`) — stores the mapping between placeholders and originals
4. **Restore** — upload the anonymized file (or paste text) along with the key file to recover the original data

## Quick Start

```bash
# One-command setup and start (creates venv, installs deps, downloads models, launches server)
python run.py          # Windows
python3 run.py         # Linux
```

Then open **http://localhost:8000** in your browser.

### Manual setup

```bash
# Create virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# Linux:
source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Download NER models
python -c "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_medium-v2.1')"
python -m spacy download en_core_web_lg

# Start the server
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

## NER Engine

- **Primary:** [GLiNER](https://github.com/urchade/GLiNER) (`gliner_medium-v2.1`) — a lightweight bidirectional NER model that detects PERSON, ORGANIZATION, and LOCATION entities
- **Fallback:** [spaCy](https://spacy.io/) (`en_core_web_lg`) — large English model, catches anything GLiNER misses

Both run locally. No API calls, no data leaks.

## Files

| File | Description |
|---|---|
| `run.py` | Cross-platform one-command setup and launcher (Windows + Linux) |
| `backend/main.py` | FastAPI server with REST endpoints |
| `backend/anonymizer.py` | NER detection using GLiNER + spaCy |
| `backend/file_handlers.py` | File parsing, entity replacement, and restoration for all formats |
| `backend/restorer.py` | Text restoration from bridge key |
| `backend/requirements.txt` | Python dependencies |
| `frontend/index.html` | Web UI |

## Supported File Types

- Microsoft Word (`.docx`)
- Microsoft Excel (`.xlsx`)
- PDF (`.pdf`)
- PowerPoint (`.pptx`)
- Raw text paste (restore only)

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Web UI |
| `GET` | `/health` | Server health + model status |
| `POST` | `/api/detect` | Detect entities in a file (returns counts) |
| `POST` | `/api/anonymize` | Anonymize a file with entity type toggles and number multiplier |
| `POST` | `/api/restore` | Restore original data from an anonymized file + key |
| `GET` | `/api/download/{filename}` | Download a processed file |
| `POST` | `/api/cleanup` | Delete all temp files |

## Bridge Key Format

```json
{
  "app": "Anon",
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
