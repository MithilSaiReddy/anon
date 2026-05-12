import io
import json
import os
import re
import sys
import shutil
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import openpyxl
from docx import Document

from backend.anonymizer import create_anonymizer, Anonymizer
from backend.restorer import create_restorer, Restorer
from backend.file_handlers import (
    extract_text_from_docx, extract_text_from_xlsx, extract_text_from_pdf, extract_text_from_pptx,
    anonymize_docx, anonymize_xlsx, anonymize_pdf, anonymize_pptx,
    restore_docx, restore_xlsx, restore_pdf, restore_pptx
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(os.path.abspath(__file__)).parent.parent
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)

anonymizer: Optional[Anonymizer] = None
restorer: Optional[Restorer] = None


@app.on_event("startup")
async def startup():
    global anonymizer, restorer
    anonymizer = create_anonymizer()
    restorer = create_restorer()
    print("Loading GLiNER NER model...")
    anonymizer.load_gliner()
    print("Loading spaCy NER model (fallback)...")
    anonymizer.load_spacy()
    print("Server ready!")


@app.get("/")
async def root():
    index_path = BASE_DIR / "frontend" / "index.html"
    return FileResponse(index_path)


@app.get("/health")
async def health():
    return {"status": "ok", "gliner_loaded": anonymizer is not None and anonymizer.nlp is not None, "spacy_loaded": anonymizer is not None and anonymizer.nlp_spacy is not None}


@app.post("/api/detect")
async def detect_entities(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    original_filename = file.filename
    file_ext = os.path.splitext(original_filename)[1].lower()
    file_bytes = await file.read()

    try:
        if file_ext == ".docx":
            text, _ = extract_text_from_docx(file_bytes)
        elif file_ext == ".xlsx":
            text, _ = extract_text_from_xlsx(file_bytes)
        elif file_ext == ".pdf":
            text, _ = extract_text_from_pdf(file_bytes)
        elif file_ext == ".pptx":
            text, _ = extract_text_from_pptx(file_bytes)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}")

        entity_map = anonymizer.extract_entities(text)

        counts = {
            "PERSON": sum(1 for k in entity_map if k.startswith("PERSON_")),
            "ORG": sum(1 for k in entity_map if k.startswith("ORG_")),
            "LOC": sum(1 for k in entity_map if k.startswith("LOC_")),
        }

        return JSONResponse({
            "success": True,
            "entities": counts,
            "filename": original_filename,
            "preview": {k: v for k, v in list(entity_map.items())[:10]}
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/anonymize")
async def anonymize_file(
    file: UploadFile = File(...),
    multiplier: float = Form(1.0),
    anonymize_person: bool = Form(True),
    anonymize_org: bool = Form(True),
    anonymize_city: bool = Form(True),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    original_filename = file.filename
    file_ext = os.path.splitext(original_filename)[1].lower()
    file_bytes = await file.read()

    entity_types = {
        "PERSON": anonymize_person,
        "ORG": anonymize_org,
        "LOC": anonymize_city,
    }

    try:
        print(f"\n{'='*60}")
        print(f"Processing: {original_filename}")
        print(f"Multiplier: {multiplier}")
        print(f"{'='*60}")

        if file_ext == ".docx":
            text, doc = extract_text_from_docx(file_bytes)
            entity_map, _, stats = anonymizer.anonymize(text, multiplier, entity_types)

            counts, number_map = anonymize_docx(doc, entity_map, multiplier)

            output_buffer = io.BytesIO()
            doc.save(output_buffer)
            output_buffer.seek(0)
            anon_filename = f"anon_{original_filename}"
            anon_path = TEMP_DIR / anon_filename
            with open(anon_path, "wb") as f:
                f.write(output_buffer.getvalue())

            key_filename = f"{os.path.splitext(original_filename)[0]}.bridgekey.json"
            key_data = anonymizer.create_bridge_key(original_filename, entity_map, multiplier)
            key_data["number_mappings"] = number_map
            key_path = TEMP_DIR / key_filename
            with open(key_path, "w") as f:
                json.dump(key_data, f, indent=2)

            total_entities = stats["persons"] + stats["orgs"] + stats.get("locs", 0)
            message = f"Anonymized {total_entities} entities, modified {counts['numbers']} numbers (x{multiplier})"

            return JSONResponse({
                "success": True,
                "message": message,
                "anon_filename": anon_filename,
                "key_filename": key_filename,
                "entity_mapping": entity_map,
                "stats": stats,
            })

        elif file_ext == ".xlsx":
            text, wb = extract_text_from_xlsx(file_bytes)
            print(f"\nExtracted text ({len(text)} chars):")
            print(text[:500])
            print()

            entity_map, _, stats = anonymizer.anonymize(text, multiplier, entity_types)

            counts, number_map = anonymize_xlsx(wb, entity_map, multiplier)

            anon_filename = f"anon_{original_filename}"
            anon_path = TEMP_DIR / anon_filename
            wb.save(anon_path)

            key_filename = f"{os.path.splitext(original_filename)[0]}.bridgekey.json"
            key_data = anonymizer.create_bridge_key(original_filename, entity_map, multiplier)
            key_data["number_mappings"] = number_map
            key_path = TEMP_DIR / key_filename
            with open(key_path, "w") as f:
                json.dump(key_data, f, indent=2)

            total_entities = stats["persons"] + stats["orgs"] + stats.get("locs", 0)
            message = f"Anonymized {total_entities} entities, modified {counts['numbers']} numbers (x{multiplier})"

            return JSONResponse({
                "success": True,
                "message": message,
                "anon_filename": anon_filename,
                "key_filename": key_filename,
                "entity_mapping": entity_map,
                "stats": stats,
            })

        elif file_ext == ".pdf":
            text, pages = extract_text_from_pdf(file_bytes)
            entity_map, _, stats = anonymizer.anonymize(text, multiplier, entity_types)

            counts, pdf_bytes, number_map = anonymize_pdf(file_bytes, entity_map, multiplier)

            anon_filename = f"anon_{original_filename}"
            anon_path = TEMP_DIR / anon_filename
            with open(anon_path, "wb") as f:
                f.write(pdf_bytes)

            key_filename = f"{os.path.splitext(original_filename)[0]}.bridgekey.json"
            key_data = anonymizer.create_bridge_key(original_filename, entity_map, multiplier)
            key_data["number_mappings"] = number_map
            key_path = TEMP_DIR / key_filename
            with open(key_path, "w") as f:
                json.dump(key_data, f, indent=2)

            total_entities = stats["persons"] + stats["orgs"] + stats.get("locs", 0)
            message = f"Anonymized {total_entities} entities, modified {counts['numbers']} numbers (x{multiplier})"

            return JSONResponse({
                "success": True,
                "message": message,
                "anon_filename": anon_filename,
                "key_filename": key_filename,
                "entity_mapping": entity_map,
                "stats": stats,
            })

        elif file_ext == ".pptx":
            text, prs = extract_text_from_pptx(file_bytes)
            entity_map, _, stats = anonymizer.anonymize(text, multiplier, entity_types)

            counts, number_map = anonymize_pptx(prs, entity_map, multiplier)

            anon_filename = f"anon_{original_filename}"
            anon_path = TEMP_DIR / anon_filename
            prs.save(anon_path)

            key_filename = f"{os.path.splitext(original_filename)[0]}.bridgekey.json"
            key_data = anonymizer.create_bridge_key(original_filename, entity_map, multiplier)
            key_data["number_mappings"] = number_map
            key_path = TEMP_DIR / key_filename
            with open(key_path, "w") as f:
                json.dump(key_data, f, indent=2)

            total_entities = stats["persons"] + stats["orgs"] + stats.get("locs", 0)
            message = f"Anonymized {total_entities} entities, modified {counts['numbers']} numbers (x{multiplier})"

            return JSONResponse({
                "success": True,
                "message": message,
                "anon_filename": anon_filename,
                "key_filename": key_filename,
                "entity_mapping": entity_map,
                "stats": stats,
            })

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    file_path = TEMP_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=filename
    )


@app.post("/api/restore")
async def restore_file(
    file: Optional[UploadFile] = File(None),
    key_file: Optional[UploadFile] = File(None),
    raw_text: Optional[str] = Form(None),
):
    if key_file is None:
        raise HTTPException(status_code=400, detail="Key file is required")

    key_bytes = await key_file.read()
    try:
        key_data = json.loads(key_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid key file format")

    try:
        if raw_text:
            restored_text = raw_text
            entity_map = key_data.get("entities", {})
            number_map = key_data.get("number_mappings", {})
            multiplier = key_data.get("multiplier", 1.0)

            for placeholder, original in entity_map.items():
                if placeholder in restored_text:
                    restored_text = restored_text.replace(placeholder, original)

            for orig_str, new_val in number_map.items():
                if str(new_val) in restored_text:
                    restored_text = restored_text.replace(str(new_val), orig_str)

            return JSONResponse({
                "success": True,
                "message": "Text restored successfully",
                "restored_text": restored_text,
            })

        if file is None:
            raise HTTPException(status_code=400, detail="No file or text provided")

        original_filename = file.filename
        file_ext = os.path.splitext(original_filename)[1].lower()
        file_bytes = await file.read()

        if file_ext == ".docx":
            doc = Document(io.BytesIO(file_bytes))
            restore_counts = restore_docx(doc, key_data)

            output_buffer = io.BytesIO()
            doc.save(output_buffer)
            output_buffer.seek(0)

            restored_filename = f"restored_{original_filename}"
            restored_path = TEMP_DIR / restored_filename
            with open(restored_path, "wb") as f:
                f.write(output_buffer.getvalue())

            return JSONResponse({
                "success": True,
                "message": f"Restored {restore_counts['entities']} entities, {restore_counts['numbers']} numbers",
                "restored_filename": restored_filename,
            })

        elif file_ext == ".xlsx":
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
            restore_counts = restore_xlsx(wb, key_data)

            restored_filename = f"restored_{original_filename}"
            restored_path = TEMP_DIR / restored_filename
            wb.save(restored_path)

            return JSONResponse({
                "success": True,
                "message": f"Restored {restore_counts['entities']} entities, {restore_counts['numbers']} numbers",
                "restored_filename": restored_filename,
            })

        elif file_ext == ".pdf":
            restore_counts, pdf_bytes = restore_pdf(file_bytes, key_data)

            restored_filename = f"restored_{original_filename}"
            restored_path = TEMP_DIR / restored_filename
            with open(restored_path, "wb") as f:
                f.write(pdf_bytes)

            return JSONResponse({
                "success": True,
                "message": f"Restored {restore_counts['entities']} entities, {restore_counts['numbers']} numbers",
                "restored_filename": restored_filename,
            })

        elif file_ext == ".pptx":
            from pptx import Presentation
            prs = Presentation(io.BytesIO(file_bytes))
            restore_counts = restore_pptx(prs, key_data)

            restored_filename = f"restored_{original_filename}"
            restored_path = TEMP_DIR / restored_filename
            prs.save(restored_path)

            return JSONResponse({
                "success": True,
                "message": f"Restored {restore_counts['entities']} entities, {restore_counts['numbers']} numbers",
                "restored_filename": restored_filename,
            })

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cleanup")
async def cleanup_temp():
    for file_path in TEMP_DIR.iterdir():
        if file_path.is_file():
            try:
                file_path.unlink()
            except Exception:
                pass
    return {"success": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
