from unittest.mock import patch, MagicMock

import pytest

from backend.anonymizer import Anonymizer, create_anonymizer


@pytest.fixture(autouse=True)
def mock_ner_models():
    """Prevent real model loading in all anonymizer tests."""
    with patch.object(Anonymizer, "load_gliner", lambda self: None):
        with patch.object(Anonymizer, "load_spacy", lambda self: None):
            yield


@pytest.fixture
def anonymizer():
    anon = Anonymizer()
    anon.nlp = None
    anon.nlp_spacy = None
    return anon


class TestSkipWords:
    def test_skip_short_text(self, anonymizer):
        assert anonymizer._is_skip_entity("ab") is True

    def test_skip_digits(self, anonymizer):
        assert anonymizer._is_skip_entity("12345") is True

    def test_skip_numeric_with_symbols(self, anonymizer):
        assert anonymizer._is_skip_entity("1,234.56") is True

    def test_keep_valid_entity(self, anonymizer):
        assert anonymizer._is_skip_entity("John Doe") is False

    def test_skip_aadhaar_keyword(self, anonymizer):
        assert anonymizer._is_skip_entity("Aadhaar") is True
        assert anonymizer._is_skip_entity("Aadhar") is True
        assert anonymizer._is_skip_entity("GSTIN") is True


class TestIDPatterns:
    @pytest.fixture(autouse=True)
    def setup(self, anonymizer):
        self.anon = anonymizer

    def test_pan_detection(self):
        text = "My PAN is ABCDE1234F"
        entities = self.anon.extract_entities(text)
        id_placeholders = [k for k in entities if k.startswith("ID_")]
        assert len(id_placeholders) == 1
        assert entities[id_placeholders[0]] == "ABCDE1234F"

    def test_aadhaar_detection(self):
        text = "My Aadhaar is 2345 6789 1234"
        entities = self.anon.extract_entities(text)
        id_placeholders = [k for k in entities if k.startswith("ID_")]
        assert len(id_placeholders) == 1

    def test_gst_detection(self):
        text = "GST: 22AAAAA0000A1Z5"
        entities = self.anon.extract_entities(text)
        id_placeholders = [k for k in entities if k.startswith("ID_")]
        assert len(id_placeholders) == 1
        assert "22AAAAA0000A1Z5" in entities.values()

    def test_cin_detection(self):
        text = "CIN: L12345AB1234ABC123456"
        entities = self.anon.extract_entities(text)
        id_placeholders = [k for k in entities if k.startswith("ID_")]
        assert len(id_placeholders) >= 1


class TestCompanyKeywordFallback:
    @pytest.fixture(autouse=True)
    def setup(self, anonymizer):
        self.anon = anonymizer

    def test_company_with_ltd_detected(self):
        text = "Acme Corp Ltd is a company."
        entities = self.anon.extract_entities(text)
        org_placeholders = [k for k in entities if k.startswith("ORG_")]
        assert len(org_placeholders) >= 1
        found = any("Acme Corp" in v for v in entities.values())
        assert found, f"Expected 'Acme Corp' in entities, got {entities}"

    def test_company_with_inc_detected(self):
        text = "Tech Solutions Inc provides services."
        entities = self.anon.extract_entities(text)
        org_placeholders = [k for k in entities if k.startswith("ORG_")]
        assert len(org_placeholders) >= 1

    def test_company_with_keyword_substring_not_detected(self):
        text = "This is a Private message."
        entities = self.anon.extract_entities(text)
        org_values = [v for k, v in entities.items() if k.startswith("ORG_")]
        assert "Private" not in org_values


class TestAddressFallback:
    @pytest.fixture(autouse=True)
    def setup(self, anonymizer):
        self.anon = anonymizer

    def test_address_detected(self):
        text = "His address is 123 Main Street, Springfield, IL 62701."
        entities = self.anon.extract_entities(text)
        loc_placeholders = [k for k in entities if k.startswith("LOC_")]
        assert len(loc_placeholders) >= 1, f"Expected address LOC_, got {entities}"


class TestEntityTypesFiltering:
    def test_filter_person_only(self, anonymizer):
        text = "John Doe works at Acme Corp Ltd."
        entities = anonymizer.extract_entities(text, entity_types={"ORG": True, "PERSON": False, "LOC": False, "ID": False})
        org_keys = [k for k in entities if k.startswith("ORG_")]
        assert len(org_keys) >= 1

    def test_filter_none_no_entities(self, anonymizer):
        text = "Some random text without entities."
        entities = anonymizer.extract_entities(text, entity_types={"PERSON": False, "ORG": False, "LOC": False, "ID": False})
        assert len(entities) == 0


class TestCreateBridgeKey:
    def test_bridge_key_format(self, anonymizer):
        entity_map = {"PERSON_1": "John Doe"}
        key = anonymizer.create_bridge_key("test.txt", entity_map, 1.5)
        assert key["app"] == "Anon Bridge"
        assert key["version"] == "2.0"
        assert key["multiplier"] == 1.5
        assert key["original_filename"] == "test.txt"
        assert key["entities"] == entity_map
        assert "created_at" in key

    def test_bridge_key_default_multiplier(self, anonymizer):
        entity_map = {}
        key = anonymizer.create_bridge_key("test.txt", entity_map, 1.0)
        assert key["multiplier"] == 1.0


class TestCreateAnonymizer:
    def test_create_anonymizer(self):
        anon = create_anonymizer()
        assert isinstance(anon, Anonymizer)
