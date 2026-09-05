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

    def test_detect_returns_full_entity_map(self):
        anon.extract_entities = MagicMock(
            return_value={"PERSON_1": "John Doe", "ORG_1": "Acme Corp"}
        )
        with patch("backend.main.extract_text_from_docx", return_value=("text", None)):
            response = client.post(
                "/api/detect",
                files={"file": ("a.docx", b"data", "application/octet-stream")},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["entity_map"] == {"PERSON_1": "John Doe", "ORG_1": "Acme Corp"}


class TestAnonymizeFileSkipEntities:
    def test_skip_entities_passed_to_anonymizer(self):
        captured = {}

        def fake_anonymize(text, multiplier, entity_types, skip_entities=None):
            captured["skip"] = skip_entities
            return (
                {"PERSON_1": "John Doe"},
                "anon text",
                {"persons": 1, "orgs": 0, "locs": 0, "ids": 0},
            )

        anon.anonymize = MagicMock(side_effect=fake_anonymize)
        with patch("backend.main.extract_text_from_docx", return_value=("text", MagicMock())):
            with patch("backend.main.anonymize_docx", return_value=({"entities": 1, "numbers": 0}, {})):
                response = client.post(
                    "/api/anonymize",
                    data={"skip_entities": '["John Doe", "Gross"]'},
                    files={"file": ("a.docx", b"data", "application/octet-stream")},
                )
        assert response.status_code == 200
        assert captured.get("skip") == {"Gross", "John Doe"}


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
