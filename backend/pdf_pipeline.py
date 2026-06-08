import concurrent.futures
import gc
import io
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

import pdfplumber
from pdf2image import convert_from_path

from backend.memory_monitor import MemoryMonitor, MemoryThresholdExceeded

logger = logging.getLogger(__name__)

SCANNED_TEXT_THRESHOLD = 100

OCR_TEMP_DIR: Path = None


def _ensure_ocr_temp():
    global OCR_TEMP_DIR
    if OCR_TEMP_DIR is None:
        OCR_TEMP_DIR = Path(tempfile.mkdtemp(prefix="anon_ocr_"))
    return OCR_TEMP_DIR


def cleanup_ocr_temp():
    global OCR_TEMP_DIR
    if OCR_TEMP_DIR is not None and OCR_TEMP_DIR.exists():
        import shutil
        shutil.rmtree(OCR_TEMP_DIR, ignore_errors=True)
        OCR_TEMP_DIR = None


def is_scanned_pdf(file_bytes: bytes) -> bool:
    total_chars = 0
    pages_checked = 0
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    total_chars += len(text)
                pages_checked += 1
                if pages_checked >= 5:
                    break
    except Exception:
        return False
    return total_chars < SCANNED_TEXT_THRESHOLD


def _split_into_chunks(file_bytes: bytes, temp_dir: str, chunk_size: int) -> List[Tuple[str, int]]:
    import fitz
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    total = len(doc)
    num_chunks = (total + chunk_size - 1) // chunk_size
    logger.info("Splitting %d pages into %d chunks (size=%d)", total, num_chunks, chunk_size)
    chunks = []
    for start in range(0, total, chunk_size):
        end = min(start + chunk_size, total)
        chunk_path = os.path.join(temp_dir, f"chunk_{start}.pdf")
        chunk_doc = fitz.open()
        for i in range(start, end):
            chunk_doc.insert_pdf(doc, from_page=i, to_page=i)
        chunk_doc.save(chunk_path)
        chunk_doc.close()
        chunks.append((chunk_path, start))
        logger.debug("Chunk %d: pages %d-%d -> %s", start // chunk_size, start + 1, end, chunk_path)
    doc.close()
    return chunks


def _page_ocr_worker(chunk_pdf_path: str, output_md_path: str, start_page: int) -> str:
    work_dir = os.path.dirname(output_md_path)
    pages_dir = os.path.join(work_dir, f"pages_{start_page}")
    os.makedirs(pages_dir, exist_ok=True)

    with pdfplumber.open(chunk_pdf_path) as pdf:
        total_in_chunk = len(pdf.pages)

    mon = MemoryMonitor()
    first_page = start_page + 1
    last_page = start_page + total_in_chunk
    logger.info("Worker start: pages %d-%d (%s)", first_page, last_page, chunk_pdf_path)

    try:
        with mon:
            with open(output_md_path, "w", encoding="utf-8") as md_file:
                for local_idx in range(total_in_chunk):
                    actual_page = start_page + local_idx + 1
                    mon.check()

                    logger.debug("OCR page %d/%d", actual_page, last_page)

                    images = convert_from_path(
                        chunk_pdf_path,
                        dpi=150,
                        first_page=local_idx + 1,
                        last_page=local_idx + 1,
                        fmt="jpeg",
                    )

                    if not images:
                        logger.warning("No image rendered for page %d, skipping", actual_page)
                        continue

                    img_path = os.path.join(pages_dir, f"page_{actual_page}.jpg")
                    images[0].save(img_path, "JPEG")
                    del images

                    out_base = os.path.join(pages_dir, f"ocr_{actual_page}")

                    result = subprocess.run(
                        ["tesseract", img_path, out_base, "-l", "eng", "--psm", "3"],
                        capture_output=True,
                        timeout=300,
                    )

                    ocr_text_file = out_base + ".txt"
                    page_text = ""
                    if os.path.exists(ocr_text_file):
                        with open(ocr_text_file, "r", encoding="utf-8") as f:
                            page_text = f.read().strip()
                        os.unlink(ocr_text_file)

                    if page_text:
                        md_file.write(f"## Page {actual_page}\n\n{page_text}\n\n---\n\n")
                    else:
                        logger.debug("No text extracted from page %d", actual_page)

                    os.unlink(img_path)
                    gc.collect()

        logger.info("Worker complete: pages %d-%d (%s)", start_page + 1, start_page + total_in_chunk, chunk_pdf_path)

    except MemoryThresholdExceeded:
        if os.path.exists(output_md_path):
            os.unlink(output_md_path)
        raise
    except subprocess.TimeoutExpired:
        if os.path.exists(output_md_path):
            os.unlink(output_md_path)
        raise
    finally:
        for f in os.listdir(pages_dir):
            try:
                os.unlink(os.path.join(pages_dir, f))
            except Exception:
                pass
        try:
            os.rmdir(pages_dir)
        except Exception:
            pass
        try:
            os.unlink(chunk_pdf_path)
        except Exception:
            pass

    return output_md_path


def _process_direct(file_bytes: bytes, pdf_path: str, md_path: str, output_dir: Path) -> Tuple[str, str]:
    pages_dir = os.path.join(os.path.dirname(md_path), "pages_direct")
    os.makedirs(pages_dir, exist_ok=True)

    total_pages = 0
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        total_pages = len(pdf.pages)

    mon = MemoryMonitor()

    try:
        with mon:
            with open(md_path, "w", encoding="utf-8") as md_file:
                for page_num in range(1, total_pages + 1):
                    mon.check()

                    images = convert_from_path(
                        pdf_path,
                        dpi=150,
                        first_page=page_num,
                        last_page=page_num,
                        fmt="jpeg",
                    )

                    if not images:
                        continue

                    img_path = os.path.join(pages_dir, f"page_{page_num}.jpg")
                    images[0].save(img_path, "JPEG")
                    del images

                    out_base = os.path.join(pages_dir, f"ocr_{page_num}")

                    result = subprocess.run(
                        ["tesseract", img_path, out_base, "-l", "eng", "--psm", "3"],
                        capture_output=True,
                        timeout=300,
                    )

                    ocr_text_file = out_base + ".txt"
                    page_text = ""
                    if os.path.exists(ocr_text_file):
                        with open(ocr_text_file, "r", encoding="utf-8") as f:
                            page_text = f.read().strip()
                        os.unlink(ocr_text_file)

                    if page_text:
                        md_file.write(f"## Page {page_num}\n\n{page_text}\n\n---\n\n")

                    os.unlink(img_path)
                    gc.collect()

        with open(md_path, "r", encoding="utf-8") as f:
            markdown_text = f.read()

        return markdown_text, md_path

    except MemoryThresholdExceeded:
        if os.path.exists(md_path):
            os.unlink(md_path)
        raise
    except subprocess.TimeoutExpired:
        if os.path.exists(md_path):
            os.unlink(md_path)
        raise
    finally:
        for f in os.listdir(pages_dir):
            try:
                os.unlink(os.path.join(pages_dir, f))
            except Exception:
                pass
        try:
            os.rmdir(pages_dir)
        except Exception:
            pass


def process_scanned_pdf(
    file_bytes: bytes,
    output_dir: Path,
    chunk_size: int = 10,
    max_workers: int = 2,
) -> Tuple[str, str]:
    temp_dir = _ensure_ocr_temp()
    pdf_path = os.path.join(temp_dir, "input.pdf")
    with open(pdf_path, "wb") as f:
        f.write(file_bytes)

    md_path = os.path.join(output_dir, "ocr_output.md")

    total_pages = 0
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        total_pages = len(pdf.pages)

    if total_pages <= chunk_size:
        try:
            return _process_direct(file_bytes, pdf_path, md_path, output_dir)
        except MemoryThresholdExceeded:
            raise
        finally:
            try:
                os.unlink(pdf_path)
            except Exception:
                pass

    try:
        chunks = _split_into_chunks(file_bytes, temp_dir, chunk_size)
    except Exception:
        try:
            os.unlink(pdf_path)
        except Exception:
            pass
        raise

    chunk_outputs: List[str] = []
    errors: List[Exception] = []

    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for chunk_path, start_page in chunks:
                out_path = os.path.join(temp_dir, f"output_{start_page}.md")
                future = executor.submit(
                    _page_ocr_worker, chunk_path, out_path, start_page
                )
                futures.append((future, chunk_path))

            for future, chunk_path in futures:
                try:
                    result = future.result()
                    chunk_outputs.append(result)
                except Exception as e:
                    errors.append(e)
                    for f, _ in futures:
                        f.cancel()
                    break

        if errors:
            for e in errors:
                if isinstance(e, MemoryThresholdExceeded):
                    raise e
            raise errors[0]

        chunk_outputs.sort(
            key=lambda p: int(
                os.path.basename(p).replace("output_", "").replace(".md", "")
            )
        )

        with open(md_path, "w", encoding="utf-8") as final:
            for chunk_out in chunk_outputs:
                if os.path.exists(chunk_out):
                    with open(chunk_out, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            final.write(content)
                            final.write("\n\n")
                    os.unlink(chunk_out)

        with open(md_path, "r", encoding="utf-8") as f:
            markdown_text = f.read().strip()

        return markdown_text, md_path

    except (
        MemoryThresholdExceeded,
        subprocess.TimeoutExpired,
        concurrent.futures.TimeoutError,
    ):
        if os.path.exists(md_path):
            os.unlink(md_path)
        raise
    finally:
        try:
            os.unlink(pdf_path)
        except Exception:
            pass
        for chunk_path, _ in chunks:
            try:
                os.unlink(chunk_path)
            except Exception:
                pass
