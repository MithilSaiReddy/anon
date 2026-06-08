import os
from unittest.mock import patch, MagicMock, mock_open

import pytest

from backend.pdf_pipeline import (
    is_scanned_pdf,
    process_scanned_pdf,
    cleanup_ocr_temp,
    SCANNED_TEXT_THRESHOLD,
)


class InlineExecutor:
    """Mocks ProcessPoolExecutor — runs submitted functions synchronously in-process."""

    def __init__(self, max_workers=2):
        self.max_workers = max_workers

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def submit(self, fn, *args, **kwargs):
        future = MagicMock()
        try:
            result = fn(*args, **kwargs)
            future.result.return_value = result
        except Exception as e:
            future.result.side_effect = e
        return future


class TestIsScannedPDF:
    @patch("backend.pdf_pipeline.pdfplumber.open")
    def test_scanned_pdf_detected(self, mock_pdfplumber):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pdf = MagicMock()
        mock_pdf.__enter__.return_value.pages = [mock_page] * 5
        mock_pdfplumber.return_value = mock_pdf

        result = is_scanned_pdf(b"fake-pdf-bytes")
        assert result is True

    @patch("backend.pdf_pipeline.pdfplumber.open")
    def test_text_pdf_detected(self, mock_pdfplumber):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "A" * 200
        mock_pdf = MagicMock()
        mock_pdf.__enter__.return_value.pages = [mock_page]
        mock_pdfplumber.return_value = mock_pdf

        result = is_scanned_pdf(b"fake-pdf-bytes")
        assert result is False

    @patch("backend.pdf_pipeline.pdfplumber.open")
    def test_empty_pdf_handled(self, mock_pdfplumber):
        mock_pdfplumber.side_effect = Exception("corrupt PDF")
        result = is_scanned_pdf(b"")
        assert result is False

    def test_threshold_value(self):
        assert SCANNED_TEXT_THRESHOLD == 100


class TestProcessScannedPDF:
    @patch("backend.pdf_pipeline.os.unlink")
    @patch("backend.pdf_pipeline.os.listdir")
    @patch("backend.pdf_pipeline.os.rmdir")
    @patch("backend.pdf_pipeline.MemoryMonitor")
    @patch("backend.pdf_pipeline.convert_from_path")
    @patch("backend.pdf_pipeline.pdfplumber.open")
    @patch("backend.pdf_pipeline.subprocess.run")
    @patch("backend.pdf_pipeline.gc")
    def test_basic_ocr_flow(
        self,
        mock_gc,
        mock_subprocess,
        mock_pdfplumber,
        mock_convert,
        mock_monitor_cls,
        mock_rmdir,
        mock_listdir,
        mock_unlink,
        temp_dir,
    ):
        mock_listdir.return_value = []

        mock_monitor = MagicMock()
        mock_monitor.__enter__.return_value = mock_monitor
        mock_monitor_cls.return_value = mock_monitor

        mock_image = MagicMock()
        mock_convert.return_value = [mock_image]

        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pdf = MagicMock()
        mock_pdf.__enter__.return_value.pages = [mock_page]
        mock_pdfplumber.return_value = mock_pdf

        mock_subprocess.return_value = MagicMock(returncode=0)

        with patch("builtins.open", mock_open()) as mock_file:
            mock_file.return_value.__enter__.return_value.read.return_value = "## Page 1\n\nOCR text here\n\n---\n\n"
            text, md_path = process_scanned_pdf(b"fake-pdf-bytes", temp_dir)

        mock_convert.assert_called_once()
        mock_subprocess.assert_called_once()

    @patch("backend.pdf_pipeline.MemoryMonitor")
    @patch("backend.pdf_pipeline.convert_from_path")
    @patch("backend.pdf_pipeline.pdfplumber.open")
    @patch("backend.pdf_pipeline.subprocess.run")
    @patch("backend.pdf_pipeline.gc")
    def test_cleanup_on_memory_error(
        self,
        mock_gc,
        mock_subprocess,
        mock_pdfplumber,
        mock_convert,
        mock_monitor_cls,
        temp_dir,
    ):
        from backend.memory_monitor import MemoryThresholdExceeded

        mock_monitor = MagicMock()
        mock_monitor.__enter__.return_value = mock_monitor
        mock_monitor.check.side_effect = MemoryThresholdExceeded("test limit")
        mock_monitor_cls.return_value = mock_monitor

        mock_image = MagicMock()
        mock_convert.return_value = [mock_image]

        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pdf = MagicMock()
        mock_pdf.__enter__.return_value.pages = [mock_page]
        mock_pdfplumber.return_value = mock_pdf

        mock_subprocess.return_value = MagicMock(returncode=0)

        with pytest.raises(MemoryThresholdExceeded):
            process_scanned_pdf(b"fake-pdf-bytes", temp_dir)

        assert mock_monitor.check.called


class TestChunkedProcessing:
    @patch("backend.pdf_pipeline.os.unlink")
    @patch("backend.pdf_pipeline.os.listdir")
    @patch("backend.pdf_pipeline.os.rmdir")
    @patch("backend.pdf_pipeline.concurrent.futures.ProcessPoolExecutor", new=InlineExecutor)
    @patch("backend.pdf_pipeline._split_into_chunks")
    @patch("backend.pdf_pipeline.MemoryMonitor")
    @patch("backend.pdf_pipeline.convert_from_path")
    @patch("backend.pdf_pipeline.pdfplumber.open")
    @patch("backend.pdf_pipeline.subprocess.run")
    @patch("backend.pdf_pipeline.gc")
    def test_chunked_flow_merges_chunks(
        self,
        mock_gc,
        mock_subprocess,
        mock_pdfplumber,
        mock_convert,
        mock_monitor_cls,
        mock_split,
        mock_rmdir,
        mock_listdir,
        mock_unlink,
        temp_dir,
    ):
        mock_listdir.return_value = []

        mock_monitor = MagicMock()
        mock_monitor.__enter__.return_value = mock_monitor
        mock_monitor_cls.return_value = mock_monitor

        mock_image = MagicMock()
        mock_convert.return_value = [mock_image]

        mock_pdf = MagicMock()
        mock_pdf.__enter__.return_value.pages = [MagicMock()] * 15
        mock_pdfplumber.return_value = mock_pdf

        mock_subprocess.return_value = MagicMock(returncode=0)

        fake_chunks = [
            (os.path.join(temp_dir, "chunk_0.pdf"), 0),
            (os.path.join(temp_dir, "chunk_5.pdf"), 5),
            (os.path.join(temp_dir, "chunk_10.pdf"), 10),
        ]
        mock_split.return_value = fake_chunks

        with patch("builtins.open", mock_open()) as mock_file:
            mock_file.return_value.__enter__.return_value.read.return_value = (
                "## Page 1\n\ntext\n\n---\n\n## Page 6\n\ntext\n\n---\n\n## Page 11\n\ntext\n\n---\n\n"
            )
            text, md_path = process_scanned_pdf(
                b"fake-pdf-bytes", temp_dir, chunk_size=5, max_workers=2
            )

        assert mock_split.called
        assert md_path == os.path.join(temp_dir, "ocr_output.md")
        assert len(text) > 0

    @patch("backend.pdf_pipeline.os.unlink")
    @patch("backend.pdf_pipeline.os.listdir")
    @patch("backend.pdf_pipeline.os.rmdir")
    @patch("backend.pdf_pipeline.concurrent.futures.ProcessPoolExecutor", new=InlineExecutor)
    @patch("backend.pdf_pipeline._split_into_chunks")
    @patch("backend.pdf_pipeline.MemoryMonitor")
    @patch("backend.pdf_pipeline.convert_from_path")
    @patch("backend.pdf_pipeline.pdfplumber.open")
    @patch("backend.pdf_pipeline.subprocess.run")
    @patch("backend.pdf_pipeline.gc")
    def test_chunk_worker_failure_propagates(
        self,
        mock_gc,
        mock_subprocess,
        mock_pdfplumber,
        mock_convert,
        mock_monitor_cls,
        mock_split,
        mock_rmdir,
        mock_listdir,
        mock_unlink,
        temp_dir,
    ):
        from backend.memory_monitor import MemoryThresholdExceeded

        mock_listdir.return_value = []

        mock_monitor = MagicMock()
        mock_monitor.__enter__.return_value = mock_monitor
        mock_monitor_cls.return_value = mock_monitor

        mock_image = MagicMock()
        mock_convert.return_value = [mock_image]

        mock_pdf = MagicMock()
        mock_pdf.__enter__.return_value.pages = [MagicMock()] * 15
        mock_pdfplumber.return_value = mock_pdf

        mock_subprocess.return_value = MagicMock(returncode=0)

        fake_chunks = [
            (os.path.join(temp_dir, "chunk_0.pdf"), 0),
            (os.path.join(temp_dir, "chunk_5.pdf"), 5),
        ]
        mock_split.return_value = fake_chunks

        mock_monitor.check.side_effect = MemoryThresholdExceeded("test limit")

        with pytest.raises(MemoryThresholdExceeded):
            process_scanned_pdf(
                b"fake-pdf-bytes", temp_dir, chunk_size=5, max_workers=2
            )

    @patch("backend.pdf_pipeline.os.unlink")
    @patch("backend.pdf_pipeline.os.listdir")
    @patch("backend.pdf_pipeline.os.rmdir")
    @patch("backend.pdf_pipeline._split_into_chunks")
    @patch("backend.pdf_pipeline.MemoryMonitor")
    @patch("backend.pdf_pipeline.convert_from_path")
    @patch("backend.pdf_pipeline.pdfplumber.open")
    @patch("backend.pdf_pipeline.subprocess.run")
    @patch("backend.pdf_pipeline.gc")
    def test_single_page_uses_direct_path(
        self,
        mock_gc,
        mock_subprocess,
        mock_pdfplumber,
        mock_convert,
        mock_monitor_cls,
        mock_split,
        mock_rmdir,
        mock_listdir,
        mock_unlink,
        temp_dir,
    ):
        mock_listdir.return_value = []

        mock_monitor = MagicMock()
        mock_monitor.__enter__.return_value = mock_monitor
        mock_monitor_cls.return_value = mock_monitor

        mock_image = MagicMock()
        mock_convert.return_value = [mock_image]

        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pdf = MagicMock()
        mock_pdf.__enter__.return_value.pages = [mock_page]
        mock_pdfplumber.return_value = mock_pdf

        mock_subprocess.return_value = MagicMock(returncode=0)

        with patch("builtins.open", mock_open()) as mock_file:
            mock_file.return_value.__enter__.return_value.read.return_value = (
                "## Page 1\n\nOCR text here\n\n---\n\n"
            )
            text, md_path = process_scanned_pdf(b"fake-pdf-bytes", temp_dir)

        mock_split.assert_not_called()
        mock_convert.assert_called_once()
        mock_subprocess.assert_called_once()


class TestCleanupOCR:
    def test_cleanup_does_not_crash_when_no_temp(self):
        cleanup_ocr_temp()
