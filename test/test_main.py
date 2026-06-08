import json
import os
from unittest.mock import patch, MagicMock

import pytest

from backend.anonymizer import Anonymizer
from backend.restorer import Restorer

with patch.object(Anonymizer, "load_gliner", lambda self: None), \
     patch.object(Anonymizer, "load_spacy", lambda self: None):
    from backend.main import app, TEMP_DIR

anon = Anonymizer()
anon.nlp = None
anon.nlp_spacy = None
app.state.anonymizer_override = anon
app.state.restorer_override = Restorer()

import backend.main as main_module
main_module.anonymizer = anon
main_module.restorer = Restorer()


from fastapi.testclient import TestClient

client = TestClient(app)


class TestHealth:
    def test_health_endpoint(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


class TestDetectText:
    def test_detect_text_empty(self):
        response = client.post("/api/detect-text", json={"text": ""})
        assert response.status_code == 400

    def test_detect_text_no_entities(self):
        anon.extract_entities = MagicMock(return_value={})
        response = client.post("/api/detect-text", json={"text": "Just normal words here"})
        assert response.status_code == 200
        assert response.json()["total"] == 0


class TestAnonymizeText:
    def test_anonymize_text_empty(self):
        response = client.post("/api/anonymize-text", json={"text": ""})
        assert response.status_code == 400


class TestRestoreText:
    def test_restore_text_basic(self):
        response = client.post("/api/restore-text", json={
            "anonymized_text": "Hello PERSON_1!",
            "bridge_key": {"entities": {"PERSON_1": "John Doe"}},
        })
        assert response.status_code == 200
        assert "John Doe" in response.json()["restored_text"]

    def test_restore_text_empty(self):
        response = client.post("/api/restore-text", json={
            "anonymized_text": "",
            "bridge_key": {"entities": {"PERSON_1": "John Doe"}},
        })
        assert response.status_code == 400


class TestValidateKey:
    def test_valid_key(self):
        response = client.post("/api/validate-key", json={
            "entities": {"PERSON_1": "John Doe", "ORG_1": "Acme"},
            "original_filename": "test.txt",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["total_entities"] == 2

    def test_invalid_key(self):
        response = client.post("/api/validate-key", json={"entities": {}})
        assert response.status_code == 200
        assert response.json()["valid"] is False


class TestDetectFile:
    def test_detect_no_file(self):
        response = client.post("/api/detect")
        assert response.status_code == 422

    def test_detect_unsupported_type(self):
        response = client.post(
            "/api/detect",
            files={"file": ("test.xyz", b"data", "application/octet-stream")},
        )
        assert response.status_code in (400, 500)


class TestCleanup:
    def test_cleanup_success(self):
        with patch("backend.main.cleanup_ocr_temp"):
            response = client.post("/api/cleanup")
            assert response.status_code == 200
            assert response.json()["success"] is True


class TestRoot:
    def test_root_returns_html(self):
        response = client.get("/")
        assert response.status_code == 200
