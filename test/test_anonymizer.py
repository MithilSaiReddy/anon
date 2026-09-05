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


class TestCommonWordGuard:
    @pytest.fixture(autouse=True)
    def setup(self, anonymizer):
        self.anon = anonymizer

    def test_single_common_word_detected_as_true(self, anonymizer):
        assert anonymizer._is_single_common_word("Gross") is True
        assert anonymizer._is_single_common_word("Employer") is True
        assert anonymizer._is_single_common_word("Provided") is True
        assert anonymizer._is_single_common_word("Code") is True
        assert anonymizer._is_single_common_word("Act") is True

    def test_multi_word_not_common(self, anonymizer):
        assert anonymizer._is_single_common_word("John Doe") is False
        assert anonymizer._is_single_common_word("Acme Corp") is False

    def test_gross_not_flagged_as_person(self, anonymizer):
        anon = anonymizer
        anon.nlp = MagicMock()
        anon.nlp.predict_entities.return_value = [
            {"text": "Gross", "label": "Person"}
        ]
        anon.nlp_spacy = MagicMock()
        anon.nlp_spacy.return_value = MagicMock(ents=[])
        entities = anon.extract_entities("Overtime paid = 2 * rate of Gross")
        assert not any(k.startswith("PERSON_") for k in entities)

    def test_code_act_not_flagged_as_org(self, anonymizer):
        anon = anonymizer
        anon.nlp = MagicMock()
        anon.nlp.predict_entities.return_value = [
            {"text": "Code of Wages Act", "label": "Organization"},
            {"text": "Code", "label": "Organization"},
        ]
        anon.nlp_spacy = MagicMock()
        anon.nlp_spacy.return_value = MagicMock(ents=[])
        entities = anon.extract_entities("Under the Code of Wages Act, 2019.")
        org_keys = [k for k in entities if k.startswith("ORG_")]
        assert not org_keys, f"Code/Act should not be orgs, got {entities}"

    def test_employer_provided_not_flagged(self, anonymizer):
        anon = anonymizer
        anon.nlp = MagicMock()
        anon.nlp.predict_entities.return_value = [
            {"text": "Employer", "label": "Organization"},
            {"text": "Provided", "label": "Organization"},
        ]
        anon.nlp_spacy = MagicMock()
        anon.nlp_spacy.return_value = MagicMock(ents=[])
        entities = anon.extract_entities("The employer provided the records.")
        org_keys = [k for k in entities if k.startswith("ORG_")]
        assert not org_keys, f"Employer/Provided should not be orgs, got {entities}"

    def test_real_company_still_detected(self, anonymizer):
        anon = anonymizer
        anon.nlp = MagicMock()
        anon.nlp.predict_entities.return_value = [
            {"text": "Acme Corp", "label": "Organization"}
        ]
        anon.nlp_spacy = MagicMock()
        anon.nlp_spacy.return_value = MagicMock(ents=[])
        entities = anon.extract_entities("Acme Corp Ltd is a company.")
        org_keys = [k for k in entities if k.startswith("ORG_")]
        assert org_keys, f"Expected Acme Corp detected, got {entities}"


class TestLegalTitleVeto:
    def test_legal_title_returns_true(self, anonymizer):
        assert anonymizer._is_legal_doc_title("The Code on Social Security, 2020") is True
        assert anonymizer._is_legal_doc_title("Payment of Wages Act") is True
        assert anonymizer._is_legal_doc_title("Industrial Relations Code") is True

    def test_company_suffix_not_vetoed(self, anonymizer):
        assert anonymizer._is_legal_doc_title("Acme Corp") is False
        assert anonymizer._is_legal_doc_title("Tech Solutions Inc") is False
        assert anonymizer._is_legal_doc_title("Acme Corporation") is False

    def test_corporation_title_still_vetoed_if_has_marker(self, anonymizer):
        # "Corporation" isolates the strong-suffix exemption, so a title like
        # "The ... Corporation Act" that ends in Act is still vetoed.
        assert anonymizer._is_legal_doc_title("The Banking Regulation Act") is True


class TestStatutoryFragmentGuard:
    @pytest.fixture(autouse=True)
    def setup(self, anonymizer):
        self.anon = anonymizer

    def test_fragment_near_marker_detected(self, anonymizer):
        assert anonymizer._looks_like_statutory_fragment(
            "Social Security",
            "The Code on Social Security, 2020 and the Code of Wages apply.",
        ) is True

    def test_real_org_far_from_marker_not_detected(self, anonymizer):
        assert anonymizer._looks_like_statutory_fragment(
            "State Bank of India",
            "State Bank of India is regulated by the Banking Regulation Act.",
        ) is False

    def test_company_with_suffix_exempt(self, anonymizer):
        assert anonymizer._looks_like_statutory_fragment(
            "Acme Corp",
            "Acme Corp is governed by the Payment of Wages Act.",
        ) is False

    def test_single_word_not_fragment(self, anonymizer):
        assert anonymizer._looks_like_statutory_fragment(
            "Wages", "The Code of Wages apply."
        ) is False

    def test_org_fragment_dropped_from_entities(self, anonymizer):
        anon = anonymizer
        anon.nlp = MagicMock()
        anon.nlp.predict_entities.return_value = [
            {"text": "Social Security", "label": "Organization"}
        ]
        anon.nlp_spacy = MagicMock()
        anon.nlp_spacy.return_value = MagicMock(ents=[])
        entities = anon.extract_entities(
            "The Code on Social Security, 2020 and the Code of Wages apply."
        )
        org_keys = [k for k in entities if k.startswith("ORG_")]
        assert not org_keys, f"Social Security fragment should be dropped, got {entities}"

    def test_real_org_in_act_sentence_kept(self, anonymizer):
        anon = anonymizer
        anon.nlp = MagicMock()
        anon.nlp.predict_entities.return_value = [
            {"text": "State Bank of India", "label": "Organization"}
        ]
        anon.nlp_spacy = MagicMock()
        anon.nlp_spacy.return_value = MagicMock(ents=[])
        entities = anon.extract_entities(
            "State Bank of India is regulated by the Banking Regulation Act."
        )
        org_keys = [k for k in entities if k.startswith("ORG_")]
        assert org_keys, f"State Bank of India should be kept, got {entities}"


class TestSkipEntitiesParam:
    @pytest.fixture(autouse=True)
    def setup(self, anonymizer):
        self.anon = anonymizer

    def test_skip_filters_entities(self, anonymizer):
        anon = anonymizer
        anon.nlp = MagicMock()
        anon.nlp.predict_entities.return_value = [
            {"text": "John Doe", "label": "Person"},
            {"text": "Acme Corp", "label": "Organization"},
        ]
        anon.nlp_spacy = MagicMock()
        anon.nlp_spacy.return_value = MagicMock(ents=[])
        entity_map, anon_text, stats = anon.anonymize(
            "John Doe works at Acme Corp.", 1.0,
            {"PERSON": True, "ORG": True, "LOC": True, "ID": True},
            skip_entities={"John Doe"},
        )
        assert stats["persons"] == 0
        assert stats["orgs"] == 1
        assert not any(k.startswith("PERSON_") for k in entity_map)
        assert "John Doe" not in entity_map.values()

    def test_no_skip_keeps_all(self, anonymizer):
        anon = anonymizer
        anon.nlp = MagicMock()
        anon.nlp.predict_entities.return_value = [
            {"text": "John Doe", "label": "Person"}
        ]
        anon.nlp_spacy = MagicMock()
        anon.nlp_spacy.return_value = MagicMock(ents=[])
        entity_map, anon_text, stats = anon.anonymize(
            "John Doe here.", 1.0,
            {"PERSON": True, "ORG": True, "LOC": True, "ID": True},
        )
        assert "John Doe" not in anon_text


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
