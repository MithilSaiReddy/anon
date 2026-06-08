from unittest.mock import patch, MagicMock

import pytest

from backend.restorer import Restorer, create_restorer


@pytest.fixture
def restorer():
    return Restorer()


class TestRestoreText:
    def test_restore_entities(self, restorer):
        text = "Hello PERSON_1, welcome to ORG_1."
        key_data = {
            "entities": {"PERSON_1": "Alice", "ORG_1": "Wonderland Inc"},
            "number_mappings": {},
            "multiplier": 1.0,
        }
        result, counts = restorer.restore_text(text, key_data)
        assert "Alice" in result
        assert "Wonderland Inc" in result
        assert "PERSON_1" not in result
        assert counts["entities"] == 2

    def test_restore_numbers_from_mappings(self, restorer):
        text = "Total cost is 450000.0 dollars."
        key_data = {
            "entities": {},
            "number_mappings": {"150000": 450000.0},
            "multiplier": 3.0,
        }
        result, counts = restorer.restore_text(text, key_data)
        assert "150000" in result
        assert counts["numbers"] == 1

    def test_restore_via_division_when_no_mappings(self, restorer):
        text = "Total cost is 3000 dollars."
        key_data = {
            "entities": {},
            "number_mappings": {},
            "multiplier": 3.0,
        }
        result, counts = restorer.restore_text(text, key_data)
        assert "1000" in result

    def test_no_multiplier_does_not_change_numbers(self, restorer):
        text = "Total cost is 1000 dollars."
        key_data = {
            "entities": {},
            "number_mappings": {},
            "multiplier": 1.0,
        }
        result, counts = restorer.restore_text(text, key_data)
        assert "1000" in result

    def test_restore_no_replacements_needed(self, restorer):
        text = "This has no placeholders."
        key_data = {
            "entities": {"PERSON_1": "Alice"},
            "number_mappings": {},
            "multiplier": 1.0,
        }
        result, counts = restorer.restore_text(text, key_data)
        assert result == text
        assert counts["entities"] == 0

    def test_restore_partial(self, restorer):
        text = "Hello PERSON_1, this is normal text."
        key_data = {
            "entities": {"PERSON_1": "Alice", "PERSON_2": "Bob"},
            "number_mappings": {},
            "multiplier": 1.0,
        }
        result, counts = restorer.restore_text(text, key_data)
        assert "Alice" in result
        assert counts["entities"] == 1


class TestRestoreRawText:
    def test_delegates_to_restore_text(self, restorer):
        text = "Hello PERSON_1."
        key_data = {"entities": {"PERSON_1": "Alice"}, "number_mappings": {}, "multiplier": 1.0}
        result1, counts1 = restorer.restore_text(text, key_data)
        result2, counts2 = restorer.restore_raw_text(text, key_data)
        assert result1 == result2
        assert counts1 == counts2


class TestCreateRestorer:
    def test_create_restorer(self):
        r = create_restorer()
        assert isinstance(r, Restorer)
